import hashlib
import hmac
import json
import os
import unittest
from fastapi import HTTPException, Response
from starlette.requests import Request

os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-only-secret-key-with-more-than-32-characters"
os.environ["DATABASE_URL"] = "sqlite://"

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.main import (
    accept_listing, confirm_cash, confirm_payment_received, create_listing, create_payment, get_exchange, get_exchange_for_user,
    payment_returned, reconcile_payment, request_otp, update_arrival, verify_otp,
)
from app.main import subscription_checkout, youpi_webhook
from app.models import Exchange, Friendship, Listing, PaymentAttempt, PointLedger, StatusEvent, Subscription, User
from app.security import COOKIE_NAME, current_user
from app.schemas import (
    AcceptListing, ArrivalUpdate, CashConfirmation, ListingCreate, OTPRequest,
    OTPVerify, PaymentCreate, ReconciliationRequest,
)


class DomainFlowTests(unittest.TestCase):
    def setUp(self):
        settings.app_env = "development"
        settings.dev_otp_mode = True
        settings.reconciliation_token = ""
        settings.youpi_webhook_secret = ""
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.requester = User(
            id="requester", full_name="Riya Student", email="riya@example.edu", phone=None,
            college="Aditya University", verified_email=True, verified_phone=False, plan="free",
        )
        self.provider = User(
            id="provider", full_name="Aman Student", email="aman@example.edu", phone=None,
            college="Aditya University", verified_email=True, verified_phone=False, plan="free",
        )
        self.db.add_all([self.requester, self.provider])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_signup_creates_account_only_after_matching_dev_code(self):
        challenge = request_otp(OTPRequest(
            channel="email", contact="new.student@example.edu", intent="signup",
            full_name="New Student", college="Aditya University",
        ), self.db)
        response = Response()
        result = verify_otp(OTPVerify(challenge_id=challenge["challenge_id"], code=challenge["development_code"]), response, self.db)
        self.assertEqual(result["user"]["full_name"], "New Student")
        self.assertTrue(result["user"]["verified_email"])
        self.assertIsNotNone(response.headers.get("set-cookie"))

    def test_wrong_code_does_not_create_account(self):
        challenge = request_otp(OTPRequest(
            channel="email", contact="wrong.code@example.edu", intent="signup", full_name="New Student",
        ), self.db)
        wrong_code = "000000" if challenge["development_code"] != "000000" else "000001"
        with self.assertRaises(HTTPException):
            verify_otp(OTPVerify(challenge_id=challenge["challenge_id"], code=wrong_code), Response(), self.db)
        self.assertIsNone(self.db.query(User).filter_by(email="wrong.code@example.edu").first())

    def test_existing_verified_account_can_login_and_use_protected_session(self):
        challenge = request_otp(OTPRequest(
            channel="email", contact="riya@example.edu", intent="login",
        ), self.db)
        wrong_code = "000000" if challenge["development_code"] != "000000" else "000001"
        with self.assertRaises(HTTPException):
            verify_otp(OTPVerify(challenge_id=challenge["challenge_id"], code=wrong_code), Response(), self.db)
        self.assertEqual(self.db.query(User).count(), 2)

        response = Response()
        result = verify_otp(
            OTPVerify(challenge_id=challenge["challenge_id"], code=challenge["development_code"]),
            response, self.db,
        )
        self.assertEqual(result["user"]["id"], self.requester.id)
        self.assertEqual(self.db.query(User).count(), 2)
        set_cookie = response.headers["set-cookie"]
        self.assertIn("httponly", set_cookie.lower())
        cookie_pair = set_cookie.split(";", 1)[0]
        request = Request({
            "type": "http", "method": "GET", "scheme": "http", "path": "/api/auth/me",
            "query_string": b"", "headers": [(b"cookie", cookie_pair.encode())],
        })
        authenticated_user = current_user(request, self.db)
        self.assertEqual(authenticated_user.id, self.requester.id)
        self.assertEqual(COOKIE_NAME, "onpay_session")

    def test_match_meetup_payment_pending_and_reconciled_completion(self):
        request = create_listing(ListingCreate(
            kind="need", amount_min=50000, amount_max=50000, location="University library",
            availability="Today after 2 PM", note="Need cash for lunch",
        ), self.requester, self.db)["listing"]
        create_listing(ListingCreate(
            kind="have", amount_min=30000, amount_max=70000, location="University library",
            availability="Today after 2 PM", note="Can meet near the entrance",
        ), self.provider, self.db)

        exchange_data = accept_listing(request["id"], AcceptListing(amount=50000), self.provider, self.db)["exchange"]
        exchange_id = exchange_data["id"]
        with self.assertRaises(HTTPException) as denied:
            get_exchange_for_user(self.db, exchange_id, "someone-else")
        self.assertEqual(denied.exception.status_code, 404)

        update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.requester, self.db)
        meetup = update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.provider, self.db)["exchange"]
        self.assertEqual(meetup["status"], "meetup_confirmed")

        confirm_cash(exchange_id, CashConfirmation(handed_over=True), self.requester, self.db)
        confirm_cash(exchange_id, CashConfirmation(handed_over=True), self.provider, self.db)
        payment = create_payment(PaymentCreate(exchange_id=exchange_id, payee_upi="aman.student@okaxis"), self.requester, self.db)["payment"]
        duplicate_attempt = create_payment(PaymentCreate(exchange_id=exchange_id, payee_upi="aman.student@okaxis"), self.requester, self.db)["payment"]
        self.assertEqual(duplicate_attempt["id"], payment["id"])
        self.assertTrue(payment["upi_uri"].startswith("upi://pay?"))
        pending = payment_returned(payment["id"], self.requester, self.db)["payment"]
        self.assertEqual(pending["status"], "verification_pending")
        self.assertEqual(self.db.get(Exchange, exchange_id).status, "verification_pending")

        settings.reconciliation_token = "test-reconciliation-token"
        result = reconcile_payment(
            ReconciliationRequest(payment_id=payment["id"], utr="123456789012", verified_from_bank_record=True),
            "test-reconciliation-token", self.db,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.db.get(Exchange, exchange_id).status, "success")
        self.assertEqual(self.db.query(Friendship).count(), 1)
        self.assertEqual(self.db.query(PointLedger).count(), 2)
        duplicate_reconciliation = reconcile_payment(
            ReconciliationRequest(payment_id=payment["id"], utr="123456789012", verified_from_bank_record=True),
            "test-reconciliation-token", self.db,
        )
        self.assertTrue(duplicate_reconciliation["duplicate"])
        self.assertEqual(self.db.query(PointLedger).count(), 2)

    def _pending_payment(self, both_cash_confirmed=True):
        request = create_listing(ListingCreate(
            kind="need", amount_min=50000, amount_max=50000, location="University library",
            availability="Today after 2 PM", note="Need cash",
        ), self.requester, self.db)["listing"]
        create_listing(ListingCreate(
            kind="have", amount_min=30000, amount_max=70000, location="University library",
            availability="Today after 2 PM", note="Can meet",
        ), self.provider, self.db)
        exchange_id = accept_listing(request["id"], AcceptListing(amount=50000), self.provider, self.db)["exchange"]["id"]
        update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.requester, self.db)
        update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.provider, self.db)
        confirm_cash(exchange_id, CashConfirmation(handed_over=True), self.requester, self.db)
        if both_cash_confirmed:
            confirm_cash(exchange_id, CashConfirmation(handed_over=True), self.provider, self.db)
        payment = create_payment(PaymentCreate(exchange_id=exchange_id, payee_upi="aman.student@okaxis"), self.requester, self.db)["payment"]
        payment_returned(payment["id"], self.requester, self.db)
        return exchange_id, payment["id"]

    def test_recipient_can_confirm_receipt_and_audit_is_recorded(self):
        exchange_id, payment_id = self._pending_payment()
        provider_payment = get_exchange(exchange_id, self.provider, self.db)["payments"][0]
        payer_payment = get_exchange(exchange_id, self.requester, self.db)["payments"][0]
        self.assertTrue(provider_payment["can_confirm_receipt"])
        self.assertFalse(payer_payment["can_confirm_receipt"])
        result = confirm_payment_received(payment_id, self.provider, self.db)
        payment = self.db.get(PaymentAttempt, payment_id)
        exchange = self.db.get(Exchange, exchange_id)
        self.assertEqual(result["payment"]["status"], "receiver_confirmed")
        self.assertEqual(payment.receiver_confirmed_by, self.provider.id)
        self.assertIsNotNone(payment.receiver_confirmed_at)
        self.assertEqual(exchange.status, "receiver_confirmed")
        self.assertIsNotNone(exchange.completed_at)
        receipt_event = self.db.query(StatusEvent).filter_by(exchange_id=exchange_id, status="receipt_confirmed").one()
        self.assertEqual(receipt_event.actor_id, self.provider.id)
        self.assertIn("not independently bank-verified", receipt_event.details)
        self.assertEqual(self.db.query(PointLedger).count(), 0)
        self.assertEqual(self.db.query(Friendship).count(), 0)

    def test_payer_cannot_confirm_receipt(self):
        _exchange_id, payment_id = self._pending_payment()
        with self.assertRaises(HTTPException) as denied:
            confirm_payment_received(payment_id, self.requester, self.db)
        self.assertEqual(denied.exception.status_code, 403)
        self.assertEqual(self.db.get(PaymentAttempt, payment_id).status, "verification_pending")

    def test_recipient_confirmation_is_idempotent(self):
        exchange_id, payment_id = self._pending_payment()
        first = confirm_payment_received(payment_id, self.provider, self.db)
        confirmed_at = first["payment"]["receiver_confirmed_at"]
        second = confirm_payment_received(payment_id, self.provider, self.db)
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["payment"]["receiver_confirmed_at"], confirmed_at)
        self.assertEqual(self.db.query(StatusEvent).filter_by(exchange_id=exchange_id, status="receipt_confirmed").count(), 1)

    def test_receiver_confirmation_rejects_wrong_state_and_wrong_amount(self):
        _exchange_id, payment_id = self._pending_payment()
        attempt = self.db.get(PaymentAttempt, payment_id)
        attempt.status = "failed"
        self.db.commit()
        with self.assertRaises(HTTPException) as wrong_state:
            confirm_payment_received(payment_id, self.provider, self.db)
        self.assertEqual(wrong_state.exception.status_code, 409)

        attempt.status = "verification_pending"
        attempt.amount -= 1
        self.db.commit()
        with self.assertRaises(HTTPException) as wrong_amount:
            confirm_payment_received(payment_id, self.provider, self.db)
        self.assertEqual(wrong_amount.exception.status_code, 409)

    def test_payment_remains_pending_until_receipt_and_cash_handover(self):
        exchange_id, payment_id = self._pending_payment(both_cash_confirmed=False)
        before = self.db.get(Exchange, exchange_id)
        self.assertEqual(before.status, "verification_pending")
        self.assertIsNone(before.completed_at)
        confirm_payment_received(payment_id, self.provider, self.db)
        still_open = self.db.get(Exchange, exchange_id)
        self.assertEqual(still_open.status, "verification_pending")
        self.assertIsNone(still_open.completed_at)
        confirm_cash(exchange_id, CashConfirmation(handed_over=True), self.provider, self.db)
        completed = self.db.get(Exchange, exchange_id)
        self.assertEqual(completed.status, "receiver_confirmed")
        self.assertIsNotNone(completed.completed_at)

    def test_experimental_provider_event_does_not_erase_receiver_confirmation(self):
        exchange_id, payment_id = self._pending_payment()
        confirm_payment_received(payment_id, self.provider, self.db)
        payment = self.db.get(PaymentAttempt, payment_id)
        settings.youpi_webhook_secret = "test-webhook-secret"
        body = json.dumps({"event": "SUCCESS", "orderId": payment.reference, "amountPaise": payment.amount}).encode()
        signature = "sha256=" + hmac.new(settings.youpi_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        async def receive_request():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request({
            "type": "http", "method": "POST", "scheme": "https", "path": "/api/webhooks/youpi",
            "query_string": b"", "headers": [(b"x-gateway-signature", signature.encode()),
                                                   (b"x-gateway-delivery-id", b"event-after-receipt")],
        }, receive=receive_request)
        operation = youpi_webhook(request, self.db)
        try:
            operation.send(None)
        except StopIteration as completed:
            result = completed.value
        else:
            self.fail("Webhook handler unexpectedly suspended during local request-body processing")
        self.assertEqual(result["status"], "receiver_confirmed")
        self.assertEqual(self.db.get(PaymentAttempt, payment_id).status, "receiver_confirmed")
        self.assertEqual(self.db.get(Exchange, exchange_id).status, "receiver_confirmed")

    def test_unauthenticated_user_cannot_start_subscription_checkout(self):
        anonymous_request = Request({
            "type": "http", "method": "POST", "scheme": "http", "path": "/api/subscriptions/pro/checkout",
            "query_string": b"", "headers": [],
        })
        with self.assertRaises(HTTPException) as unauthorized:
            current_user(anonymous_request, self.db)
        self.assertEqual(unauthorized.exception.status_code, 401)
        with self.assertRaises(HTTPException) as unavailable:
            subscription_checkout("pro", self.requester)
        self.assertEqual(unavailable.exception.status_code, 503)
        self.assertEqual(self.requester.plan, "free")
        self.assertEqual(self.db.query(Subscription).count(), 0)


if __name__ == "__main__":
    unittest.main()
