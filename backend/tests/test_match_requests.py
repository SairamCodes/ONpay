import unittest
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Exchange, Listing, LoginSession, MatchRequest, Notification, PointLedger, User, now_utc
from app.schemas import AcceptListing, ArrivalUpdate, CashConfirmation, ListingCreate, MatchRequestCreate, PaymentCreate
from app.main import (
    accept_match_request, cancel_match_request, confirm_cash_received, confirm_upi_received,
    create_listing, create_match_request, create_payment, get_match_request, get_upi_qr,
    list_match_requests, monthly_usage, payment_returned, reject_match_request, update_arrival,
)


class MatchRequestTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        self.seeker = User(
            id="seeker-1", full_name="User A (Seeker)", email="seeker@campus.edu",
            phone="+919876543210", college="Tech Campus", plan="free",
        )
        self.provider = User(
            id="provider-1", full_name="User B (Provider)", email="provider@campus.edu",
            phone="+919876543211", college="Tech Campus", plan="free", upi_id="provider@okaxis",
        )
        self.provider2 = User(
            id="provider-2", full_name="User C (Provider 2)", email="provider2@campus.edu",
            phone="+919876543212", college="Tech Campus", plan="free", upi_id="provider2@okaxis",
        )
        self.db.add_all([self.seeker, self.provider, self.provider2])
        self.db.commit()

        # Seeker needs ₹1,000 (100000 paise)
        self.seeker_listing = create_listing(
            ListingCreate(
                kind="need", amount_min=100000, amount_max=100000, location="Library",
                availability="Today 2 PM", note="Need cash for books", search_radius_km=10,
            ),
            self.seeker, self.db,
        )["listing"]

        # Provider 1 has ₹1,000 cash
        self.provider_listing = create_listing(
            ListingCreate(
                kind="have", amount_min=50000, amount_max=150000, location="Library",
                availability="Today 2 PM", note="Can give cash", search_radius_km=10,
            ),
            self.provider, self.db,
        )["listing"]

        # Provider 2 also has cash
        self.provider2_listing = create_listing(
            ListingCreate(
                kind="have", amount_min=100000, amount_max=100000, location="Cafeteria",
                availability="Today 3 PM", note="Cash available", search_radius_km=10,
            ),
            self.provider2, self.db,
        )["listing"]

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_create_and_list_match_request(self):
        result = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000, note="Let's meet"),
            self.seeker, self.db,
        )
        self.assertFalse(result["duplicate"])
        req_id = result["match_request"]["id"]
        self.assertEqual(result["match_request"]["status"], "pending")
        self.assertEqual(result["match_request"]["amount"], 100000)

        # Provider views incoming match requests
        incoming = list_match_requests(self.provider, self.db)
        self.assertEqual(len(incoming["incoming"]), 1)
        self.assertEqual(incoming["incoming"][0]["id"], req_id)

        # Seeker views outgoing match requests
        outgoing = list_match_requests(self.seeker, self.db)
        self.assertEqual(len(outgoing["outgoing"]), 1)
        self.assertEqual(outgoing["outgoing"][0]["id"], req_id)

    def test_duplicate_match_request_returns_existing(self):
        create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000),
            self.seeker, self.db,
        )
        second = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000),
            self.seeker, self.db,
        )
        self.assertTrue(second["duplicate"])

    def test_multiple_match_requests_and_acceptance_rejects_others(self):
        # Seeker sends request to provider 1
        req1 = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000),
            self.seeker, self.db,
        )["match_request"]

        # Seeker sends request to provider 2 simultaneously
        req2 = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider2_listing["id"], amount=100000),
            self.seeker, self.db,
        )["match_request"]

        # Provider 1 accepts
        accept_result = accept_match_request(req1["id"], self.provider, self.db)
        self.assertEqual(accept_result["match_request"]["status"], "accepted")
        self.assertIsNotNone(accept_result["exchange"])

        # Verify provider 2's request was auto-rejected because seeker listing got matched
        req2_updated = get_match_request(req2["id"], self.seeker, self.db)["match_request"]
        self.assertEqual(req2_updated["status"], "rejected")

        # Verify listings are marked matched
        self.assertEqual(self.db.get(Listing, self.seeker_listing["id"]).status, "matched")
        self.assertEqual(self.db.get(Listing, self.provider_listing["id"]).status, "matched")

    def test_reject_and_cancel_match_request(self):
        req = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000),
            self.seeker, self.db,
        )["match_request"]

        # Provider rejects
        rejected = reject_match_request(req["id"], self.provider, self.db)
        self.assertEqual(rejected["match_request"]["status"], "rejected")

        # New request can be created and cancelled by seeker
        req2 = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider2_listing["id"], amount=100000),
            self.seeker, self.db,
        )["match_request"]
        cancelled = cancel_match_request(req2["id"], self.seeker, self.db)
        self.assertEqual(cancelled["match_request"]["status"], "cancelled")

    def test_dual_transaction_confirmation_workflow(self):
        req = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000),
            self.seeker, self.db,
        )["match_request"]
        accept_result = accept_match_request(req["id"], self.provider, self.db)
        exchange_id = accept_result["exchange"]["id"]

        # Unauthorized confirmations should be rejected
        with self.assertRaises(HTTPException) as ctx:
            confirm_cash_received(exchange_id, self.provider, self.db)  # Provider cannot confirm cash received
        self.assertEqual(ctx.exception.status_code, 403)

        with self.assertRaises(HTTPException) as ctx:
            confirm_upi_received(exchange_id, self.seeker, self.db)  # Seeker cannot confirm UPI received
        self.assertEqual(ctx.exception.status_code, 403)

        # 1. Seeker confirms physical cash received
        seeker_conf = confirm_cash_received(exchange_id, self.seeker, self.db)
        self.assertTrue(seeker_conf["exchange"]["seeker_cash_received"])
        self.assertFalse(seeker_conf["exchange"]["provider_upi_received"])
        self.assertNotEqual(seeker_conf["exchange"]["status"], "COMPLETED")

        # 2. Provider confirms UPI received
        provider_conf = confirm_upi_received(exchange_id, self.provider, self.db)
        self.assertTrue(provider_conf["exchange"]["seeker_cash_received"])
        self.assertTrue(provider_conf["exchange"]["provider_upi_received"])
        # Now BOTH confirmations are True -> Exchange must be COMPLETED!
        self.assertEqual(provider_conf["exchange"]["status"], "COMPLETED")
        self.assertIsNotNone(provider_conf["exchange"]["completed_at"])

        # Idempotent re-confirmations
        re_seeker = confirm_cash_received(exchange_id, self.seeker, self.db)
        self.assertEqual(re_seeker["exchange"]["status"], "COMPLETED")

    def test_full_two_user_exchange_flow(self):
        # 1. Seeker posts need for ₹1,000
        # 2. Provider posts have for ₹1,000 with upi_id = "provider@okaxis"
        # 3. Seeker sends match request
        req = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000, note="Meet near Library"),
            self.seeker, self.db,
        )["match_request"]
        self.assertEqual(req["status"], "pending")

        # 4. Provider accepts match request
        accept_res = accept_match_request(req["id"], self.provider, self.db)
        exchange = accept_res["exchange"]
        exchange_id = exchange["id"]
        self.assertEqual(exchange["status"], "MATCH_ACCEPTED")

        # 5. Seeker confirms arrival
        arr1 = update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.seeker, self.db)
        self.assertTrue(arr1["exchange"]["requester_arrived"])
        self.assertFalse(arr1["exchange"]["provider_arrived"])
        self.assertEqual(arr1["exchange"]["status"], "MATCH_ACCEPTED")

        # 6. Provider confirms arrival -> status becomes meetup_confirmed
        arr2 = update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.provider, self.db)
        self.assertTrue(arr2["exchange"]["requester_arrived"])
        self.assertTrue(arr2["exchange"]["provider_arrived"])
        self.assertEqual(arr2["exchange"]["status"], "meetup_confirmed")

        # 7. Seeker initiates UPI payment using provider's registered upi_id
        pay_res = create_payment(
            PaymentCreate(exchange_id=exchange_id, payee_upi=self.provider.upi_id),
            self.seeker, self.db,
        )
        self.assertIn("upi://pay", pay_res["payment"]["upi_uri"])
        self.assertEqual(pay_res["payment"]["amount"], 100000)

        # 8. Seeker receives cash and clicks "RECEIVED CASH"
        conf_cash = confirm_cash_received(exchange_id, self.seeker, self.db)
        self.assertTrue(conf_cash["exchange"]["seeker_cash_received"])
        self.assertFalse(conf_cash["exchange"]["provider_upi_received"])
        # Status MUST NOT be COMPLETED until provider also confirms UPI
        self.assertNotEqual(conf_cash["exchange"]["status"], "COMPLETED")

        # 9. Provider checks bank/UPI app and clicks "RECEIVED AMOUNT VIA UPI"
        conf_upi = confirm_upi_received(exchange_id, self.provider, self.db)
        self.assertTrue(conf_upi["exchange"]["seeker_cash_received"])
        self.assertTrue(conf_upi["exchange"]["provider_upi_received"])

        # 10. BOTH confirmations are true -> Exchange status is strictly COMPLETED!
        self.assertEqual(conf_upi["exchange"]["status"], "COMPLETED")
        self.assertIsNotNone(conf_upi["exchange"]["completed_at"])

    def test_quota_debited_exactly_once(self):
        # Initial usage is 0 completed, 0 reserved
        comp, res = monthly_usage(self.db, self.seeker.id)
        self.assertEqual(comp, 0)
        self.assertEqual(res, 0)

        # Create match and accept
        req = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000),
            self.seeker, self.db,
        )["match_request"]
        accept_res = accept_match_request(req["id"], self.provider, self.db)
        exchange_id = accept_res["exchange"]["id"]

        # In-progress exchange counts as 1 reserved
        comp, res = monthly_usage(self.db, self.seeker.id)
        self.assertEqual(comp, 0)
        self.assertEqual(res, 1)

        # Complete exchange
        confirm_cash_received(exchange_id, self.seeker, self.db)
        confirm_upi_received(exchange_id, self.provider, self.db)

        # Exactly 1 completed, 0 reserved
        comp, res = monthly_usage(self.db, self.seeker.id)
        self.assertEqual(comp, 1)
        self.assertEqual(res, 0)

        # Re-confirmations (idempotency/duplicates) DO NOT debit extra quota
        confirm_cash_received(exchange_id, self.seeker, self.db)
        confirm_upi_received(exchange_id, self.provider, self.db)
        comp2, res2 = monthly_usage(self.db, self.seeker.id)
        self.assertEqual(comp2, 1)
        self.assertEqual(res2, 0)

    def test_returning_from_upi_app_does_not_complete_payment(self):
        req = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000),
            self.seeker, self.db,
        )["match_request"]
        accept_res = accept_match_request(req["id"], self.provider, self.db)
        exchange_id = accept_res["exchange"]["id"]
        update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.seeker, self.db)
        update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.provider, self.db)

        pay_res = create_payment(
            PaymentCreate(exchange_id=exchange_id, payee_upi=self.provider.upi_id),
            self.seeker, self.db,
        )
        pay_id = pay_res["payment"]["id"]
        self.assertEqual(pay_res["payment"]["status"], "payment_initiated")

        # Simulate user returning from UPI app
        ret = payment_returned(pay_id, self.seeker, self.db)
        self.assertEqual(ret["payment"]["status"], "verification_pending")
        self.assertNotEqual(ret["payment"]["status"], "COMPLETED")
        self.assertNotEqual(ret["payment"]["status"], "success")

        # Exchange also remains verification_pending, NOT COMPLETED
        ex = self.db.get(Exchange, exchange_id)
        self.assertEqual(ex.status, "verification_pending")
        self.assertFalse(ex.seeker_cash_received)
        self.assertFalse(ex.provider_upi_received)

    def test_upi_qr_payload_format_and_vpa(self):
        qr_info = get_upi_qr(self.provider)
        self.assertEqual(qr_info["upi_id"], "provider@okaxis")
        self.assertTrue(qr_info["upi_uri"].startswith("upi://pay?"))
        self.assertIn("pa=provider%40okaxis", qr_info["upi_uri"])
        self.assertIn("cu=INR", qr_info["upi_uri"])

        # User without upi_id raises 404
        with self.assertRaises(HTTPException) as ctx:
            get_upi_qr(self.seeker)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_match_request_expiry(self):
        req = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000),
            self.seeker, self.db,
        )["match_request"]
        mr = self.db.get(MatchRequest, req["id"])
        # Move expiry into past
        mr.expires_at = now_utc() - timedelta(minutes=5)
        self.db.commit()

        # get_match_request updates it to expired
        fetch = get_match_request(mr.id, self.seeker, self.db)
        self.assertEqual(fetch["match_request"]["status"], "expired")

        # Provider accepting an expired request raises 409
        with self.assertRaises(HTTPException) as ctx:
            accept_match_request(mr.id, self.provider, self.db)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_transaction_completion_awards_points_exactly_once(self):
        # 1. Create and accept match request
        req = create_match_request(
            MatchRequestCreate(provider_listing_id=self.provider_listing["id"], amount=100000),
            self.seeker, self.db,
        )["match_request"]
        exchange_id = accept_match_request(req["id"], self.provider, self.db)["exchange"]["id"]

        # Prior to completion, 0 points exist
        self.assertEqual(self.db.query(PointLedger).count(), 0)

        # 2. Both arrive
        update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.seeker, self.db)
        update_arrival(exchange_id, ArrivalUpdate(arrived=True), self.provider, self.db)

        # 3. Seeker confirms cash received
        confirm_cash_received(exchange_id, self.seeker, self.db)
        # Not completed yet -> no points
        self.assertEqual(self.db.query(PointLedger).count(), 0)

        # 4. Provider confirms UPI received -> triggers COMPLETED!
        conf_upi = confirm_upi_received(exchange_id, self.provider, self.db)
        self.assertEqual(conf_upi["exchange"]["status"], "COMPLETED")

        # 5. Exactly 2 PointLedger records awarded (10 points each to seeker and provider)
        ledger_entries = self.db.query(PointLedger).all()
        self.assertEqual(len(ledger_entries), 2)
        seeker_pt = self.db.query(PointLedger).filter_by(user_id=self.seeker.id).one()
        provider_pt = self.db.query(PointLedger).filter_by(user_id=self.provider.id).one()
        self.assertEqual(seeker_pt.amount, 10)
        self.assertEqual(seeker_pt.reason, "completed_exchange")
        self.assertEqual(provider_pt.amount, 10)
        self.assertEqual(provider_pt.reason, "completed_exchange")

        # 6. Duplicate confirmations (idempotency check) do NOT award extra points
        confirm_cash_received(exchange_id, self.seeker, self.db)
        confirm_upi_received(exchange_id, self.provider, self.db)
        self.assertEqual(self.db.query(PointLedger).count(), 2)


if __name__ == "__main__":
    unittest.main()
