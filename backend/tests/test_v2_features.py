"""Unit tests for ONPay V2 Features: Points, Friend Requests, Admin Security & Subscriptions."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from fastapi import HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    AdminAuditLog, AdminQRCode, AdminSession, AdminUser, Exchange, FriendRequest,
    Friendship, Listing, PointLedger, Subscription, SubscriptionRequest, User,
    UserLoginEvent, now_utc,
)
from app.main import (
    accept_friend_request, cancel_friend_request, friend_status, get_my_subscription_request,
    get_subscription_qr_image, reject_friend_request, send_friend_request,
    submit_subscription_payment, subscriptions,
)
from app.admin_security import hash_password, verify_password
from app.admin import (
    AdminLoginRequest, PointsAdjustRequest, SubscriptionRejectRequest,
    activate_qr_code, adjust_user_points, admin_login, admin_logout,
    admin_me, approve_subscription, dashboard_analytics,
    user_detail, list_qr_codes, list_audit_logs, points_ledger,
    list_subscription_requests, list_transactions, list_users,
    reject_subscription, upload_qr_code, _login_failures,
)


class DummyClient:
    host = "127.0.0.1"


class DummyRequest:
    client = DummyClient()
    headers = {}
    cookies = {}


class V2FeatureTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        # Clear login failures rate limit map for tests
        _login_failures.clear()

        self.user_a = User(
            id="user-a", full_name="Alice Smith", email="alice@campus.edu",
            phone="+919876543201", college="Tech Campus", plan="free",
        )
        self.user_b = User(
            id="user-b", full_name="Bob Jones", email="bob@campus.edu",
            phone="+919876543202", college="Tech Campus", plan="free",
        )
        self.user_c = User(
            id="user-c", full_name="Charlie Brown", email="charlie@campus.edu",
            phone="+919876543203", college="Tech Campus", plan="free",
        )
        self.admin = AdminUser(
            id="admin-1", email="superadmin@onpay.com", full_name="Super Admin",
            hashed_password=hash_password("MasterAdmin123"), role="superadmin", is_active=True,
        )
        self.db.add_all([self.user_a, self.user_b, self.user_c, self.admin])
        self.db.add(PointLedger(
            id="pt-initial-a", user_id="user-a", amount=50, reason="initial_bonus", created_at=now_utc(),
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_password_hashing_and_verification(self):
        pwd = "SecretPassword123"
        hashed = hash_password(pwd)
        self.assertTrue(hashed.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password(pwd, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_friend_request_lifecycle(self):
        st = friend_status(self.user_b.id, self.user_a, self.db)
        self.assertEqual(st["status"], "none")

        req_res = send_friend_request(self.user_b.id, None, self.user_a, self.db)
        self.assertEqual(req_res["status"], "request_sent")
        req_id = req_res["request_id"]

        st_a = friend_status(self.user_b.id, self.user_a, self.db)
        self.assertEqual(st_a["status"], "request_sent")
        self.assertEqual(st_a["request_id"], req_id)

        st_b = friend_status(self.user_a.id, self.user_b, self.db)
        self.assertEqual(st_b["status"], "request_received")
        self.assertEqual(st_b["request_id"], req_id)

        # Bi-directional duplicate prevention
        with self.assertRaises(HTTPException) as ctx1:
            send_friend_request(self.user_b.id, None, self.user_a, self.db)
        self.assertEqual(ctx1.exception.status_code, 409)

        with self.assertRaises(HTTPException) as ctx2:
            send_friend_request(self.user_a.id, None, self.user_b, self.db)
        self.assertEqual(ctx2.exception.status_code, 409)
        self.assertIn("Accept their request instead", ctx2.exception.detail)

        # User B accepts request
        acc_res = accept_friend_request(req_id, self.user_b, self.db)
        self.assertEqual(acc_res["status"], "friends")

        self.assertEqual(friend_status(self.user_b.id, self.user_a, self.db)["status"], "friends")
        self.assertEqual(friend_status(self.user_a.id, self.user_b, self.db)["status"], "friends")
        self.assertEqual(self.db.query(Friendship).count(), 1)

        # Cannot generate new requests once already friends
        with self.assertRaises(HTTPException) as ctx3:
            send_friend_request(self.user_b.id, None, self.user_a, self.db)
        self.assertEqual(ctx3.exception.status_code, 409)

    def test_friend_request_rejection(self):
        req_id = send_friend_request(self.user_c.id, None, self.user_a, self.db)["request_id"]
        rej_res = reject_friend_request(req_id, self.user_c, self.db)
        self.assertEqual(rej_res["status"], "none")
        self.assertEqual(friend_status(self.user_c.id, self.user_a, self.db)["status"], "none")
        self.assertEqual(self.db.query(Friendship).count(), 0)

    def test_friend_request_cancellation(self):
        req_id = send_friend_request(self.user_c.id, None, self.user_b, self.db)["request_id"]
        cancel_res = cancel_friend_request(req_id, self.user_b, self.db)
        self.assertEqual(cancel_res["status"], "none")
        self.assertEqual(friend_status(self.user_c.id, self.user_b, self.db)["status"], "none")

    def test_admin_authentication_and_rate_limiting(self):
        req = DummyRequest()
        res = Response()

        # 1. Invalid password
        bad_payload = AdminLoginRequest(email="superadmin@onpay.com", password="WrongPassword")
        with self.assertRaises(HTTPException) as ctx:
            admin_login(bad_payload, req, res, self.db)
        self.assertEqual(ctx.exception.status_code, 401)

        # 2. Rate limit after 5 failed attempts
        for _ in range(4):
            try:
                admin_login(bad_payload, req, res, self.db)
            except HTTPException:
                pass

        with self.assertRaises(HTTPException) as ctx_limit:
            admin_login(bad_payload, req, res, self.db)
        self.assertEqual(ctx_limit.exception.status_code, 429)

        # Clear rate limit map for subsequent tests
        _login_failures.clear()

        # 3. Successful login
        good_payload = AdminLoginRequest(email="superadmin@onpay.com", password="MasterAdmin123")
        login_res = admin_login(good_payload, req, res, self.db)
        self.assertIn("session_token", login_res)
        self.assertEqual(login_res["admin"]["email"], "superadmin@onpay.com")
        self.assertEqual(self.db.query(AdminSession).count(), 1)

        # 4. Auth me
        me_res = admin_me(self.admin)
        self.assertEqual(me_res["id"], self.admin.id)

        # 5. Logout
        req.headers["Authorization"] = f"Bearer {login_res['token']}"
        logout_res = admin_logout(req, res, self.admin, self.db)
        self.assertTrue(logout_res.get("ok"))
        self.assertEqual(self.db.query(AdminSession).count(), 0)

    def test_admin_analytics_aggregation(self):
        now = now_utc()
        # Add user login events
        self.db.add(UserLoginEvent(id="evt-1", user_id=self.user_a.id, ip_address="127.0.0.1", login_at=now))
        self.db.add(UserLoginEvent(id="evt-2", user_id=self.user_b.id, ip_address="127.0.0.1", login_at=now))
        # Add a completed exchange
        ex = Exchange(
            id="ex-test-1", listing_id="lst-1", matched_listing_id="lst-2",
            requester_id=self.user_a.id, provider_id=self.user_b.id,
            amount=500, location="Library", meetup_at="Today 2pm",
            status="COMPLETED", seeker_cash_received=True, provider_upi_received=True,
            completed_at=now,
        )
        self.db.add(ex)
        # Add point ledger
        self.db.add(PointLedger(
            id="pt-1", user_id=self.user_a.id, amount=10,
            reason="exchange_completion", exchange_id="ex-test-1", created_at=now,
        ))
        self.db.commit()

        res = dashboard_analytics(self.admin, self.db)
        self.assertEqual(res["total_users"], 3)
        self.assertEqual(res["total_successful_daily_logins"], 2)
        self.assertEqual(res["unique_daily_active_users"], 2)
        self.assertEqual(res["completed_transactions"], 1)
        self.assertEqual(res["completed_transaction_volume"], 500)
        self.assertEqual(res["total_points_awarded"], 60)
        self.assertEqual(len(res["trend_14d"]), 14)

    def test_admin_qr_code_lifecycle(self):
        req = DummyRequest()
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        qr_file = UploadFile(filename="test_qr.png", file=BytesIO(png_bytes))

        # 1. Upload QR 1
        res1 = asyncio.run(upload_qr_code("QR 1", "onpay1@okhdfcbank", qr_file, req, self.admin, self.db))
        self.assertEqual(res1["upi_id"], "onpay1@okhdfcbank")
        qr1_id = res1["id"]
        self.assertTrue(res1["is_active"])

        # Check in checkout endpoint
        sub_info = subscriptions(self.user_a, self.db)
        self.assertTrue(sub_info["billing_configured"])
        self.assertEqual(sub_info["qr_code"]["upi_id"], "onpay1@okhdfcbank")

        # 2. Upload QR 2
        qr_file2 = UploadFile(filename="test_qr2.png", file=BytesIO(png_bytes))
        res2 = asyncio.run(upload_qr_code("QR 2", "onpay2@okhdfcbank", qr_file2, req, self.admin, self.db))
        qr2_id = res2["id"]

        # Activate QR 2
        activate_qr_code(qr2_id, req, self.admin, self.db)
        self.assertFalse(self.db.get(AdminQRCode, qr1_id).is_active)
        self.assertTrue(self.db.get(AdminQRCode, qr2_id).is_active)

        # 3. Reactivate QR 1
        activate_qr_code(qr1_id, req, self.admin, self.db)
        self.assertTrue(self.db.get(AdminQRCode, qr1_id).is_active)
        self.assertFalse(self.db.get(AdminQRCode, qr2_id).is_active)

    def test_subscription_payment_submission_and_admin_approval(self):
        req = DummyRequest()
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

        # 1. Active QR exists
        qr = AdminQRCode(
            id="qr-active", title="Active QR", upi_id="onpay@okhdfcbank", image_path="fake/path.png",
            mime_type="image/png", is_active=True, uploaded_by=self.admin.id,
        )
        self.db.add(qr)
        self.db.commit()

        # 2. Student submits payment request
        proof = UploadFile(filename="payment_proof.png", file=BytesIO(png_bytes))
        sub_res = asyncio.run(submit_subscription_payment("plus", "412345678901", proof, self.user_a, self.db))
        self.assertEqual(sub_res["status"], "pending_review")
        self.assertEqual(sub_res["target_review_minutes"], 20)
        req_id = sub_res["request_id"]

        # Duplicate UTR rejected
        proof_dup = UploadFile(filename="payment_proof.png", file=BytesIO(png_bytes))
        with self.assertRaises(HTTPException) as ctx_dup:
            asyncio.run(submit_subscription_payment("plus", "412345678901", proof_dup, self.user_b, self.db))
        self.assertEqual(ctx_dup.exception.status_code, 409)

        # 3. Admin lists pending subscription requests
        admin_subs = list_subscription_requests(status_filter="PENDING", status=None, limit=50, offset=0, admin=self.admin, db=self.db)
        self.assertEqual(admin_subs["total"], 1)
        req_item = admin_subs["requests"][0]
        self.assertEqual(req_item["upi_ref"], "412345678901")
        self.assertEqual(req_item["user_name"], "Alice Smith")
        self.assertEqual(req_item["target_review_minutes"], 20)

        # 4. Admin approves subscription
        app_res = approve_subscription(req_id, req, self.admin, self.db)
        self.assertTrue(app_res.get("ok"))

        # Verify user plan updated to 'plus'
        user_refreshed = self.db.get(User, self.user_a.id)
        self.assertEqual(user_refreshed.plan, "plus")

        # Verify active Subscription record created
        sub_record = self.db.query(Subscription).filter_by(user_id=self.user_a.id, status="active").first()
        self.assertIsNotNone(sub_record)
        self.assertEqual(sub_record.plan, "plus")

        # Verify audit log recorded
        audit = self.db.query(AdminAuditLog).filter_by(action="approve_subscription").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.target_id, req_id)

    def test_subscription_rejection(self):
        req = DummyRequest()
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        qr = AdminQRCode(
            id="qr-active-2", title="Active QR 2", upi_id="onpay@okhdfcbank", image_path="fake/path.png",
            mime_type="image/png", is_active=True, uploaded_by=self.admin.id,
        )
        self.db.add(qr)
        self.db.commit()

        proof = UploadFile(filename="proof_b.png", file=BytesIO(png_bytes))
        sub_res = asyncio.run(submit_subscription_payment("plus", "999888777666", proof, self.user_b, self.db))
        req_id = sub_res["request_id"]

        reject_payload = SubscriptionRejectRequest(reason="UTR not found on bank statement")
        rej_res = reject_subscription(req_id, reject_payload, req, self.admin, self.db)
        self.assertTrue(rej_res.get("ok"))

        # Verify plan remained 'free'
        user_refreshed = self.db.get(User, self.user_b.id)
        self.assertEqual(user_refreshed.plan, "free")

        # Verify SubscriptionRequest record
        db_req = self.db.get(SubscriptionRequest, req_id)
        self.assertEqual(db_req.status, "rejected")
        self.assertEqual(db_req.rejection_reason, "UTR not found on bank statement")

    def test_admin_points_adjustment(self):
        req = DummyRequest()
        payload = PointsAdjustRequest(amount=25, reason="Campus ambassador bonus")
        res = adjust_user_points(self.user_a.id, payload, req, self.admin, self.db)
        self.assertEqual(res["new_balance"], 75)

        # Verify points ledger entry
        ledger_entry = self.db.query(PointLedger).filter_by(user_id=self.user_a.id).order_by(PointLedger.created_at.desc()).first()
        self.assertIsNotNone(ledger_entry)
        self.assertEqual(ledger_entry.amount, 25)
        self.assertIn("Campus ambassador bonus", ledger_entry.reason)

        # Verify audit log
        audit = self.db.query(AdminAuditLog).filter_by(action="adjust_points").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.target_id, self.user_a.id)


if __name__ == "__main__":
    unittest.main()
