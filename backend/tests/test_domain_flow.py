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
    accept_listing, confirm_cash, create_listing, create_payment, get_exchange_for_user,
    payment_returned, reconcile_payment, request_otp, update_arrival, verify_otp,
)
from app.models import Exchange, Friendship, Listing, PointLedger, User
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


if __name__ == "__main__":
    unittest.main()
