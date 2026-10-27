import json
import os
import unittest
from datetime import timedelta
from unittest.mock import Mock, patch

import httpx

os.environ["APP_ENV"] = "development"
os.environ["DEV_OTP_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-only-secret-key-with-more-than-32-characters"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["FRONTEND_ORIGINS"] = "https://onpay.example.test,https://preview.onpay.example.test"

from fastapi import HTTPException, Response
from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware

from app.config import Settings, settings
from app.database import Base, SessionLocal, engine
from app.main import (
    app, check_quota, cors_options, create_listing, current_month_bounds, fastapi_app,
    get_listings, haversine_km, health,
    location_reverse, location_settings, logout, monthly_usage, request_otp, reverse_geocode, set_location, startup, subscriptions,
    verify_otp,
)
from app.models import Exchange, Listing, OTPChallenge, Subscription, User, now_utc
from app.security import create_session, hash_otp
from app.schemas import ListingCreate, OTPRequest, OTPVerify


class CriticalFixTests(unittest.TestCase):
    def setUp(self):
        settings.app_env = "development"
        settings.dev_otp_mode = True
        settings.email_provider = "resend"
        settings.resend_api_key = ""
        settings.brevo_api_key = ""
        settings.email_from = ""
        settings.twilio_account_sid = ""
        settings.twilio_auth_token = ""
        settings.twilio_verify_service_sid = ""
        settings.session_cookie_samesite = "lax"
        settings.reverse_geocoder_user_agent = ""
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.requester = User(id="requester", full_name="Riya Student", email="riya@example.edu", phone=None,
                              college="Aditya University", verified_email=True, plan="free")
        self.provider = User(id="provider", full_name="Aman Student", email="aman@example.edu", phone=None,
                             college="Aditya University", verified_email=True, plan="free")
        self.db.add_all((self.requester, self.provider))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _configure_resend(self):
        settings.email_provider = "resend"
        settings.resend_api_key = "test_resend_key_not_real"
        settings.email_from = "ONPay <verify@example.test>"

    def _configure_brevo(self):
        settings.email_provider = "brevo"
        settings.brevo_api_key = "test_brevo_key_not_real"
        settings.email_from = "ONPay <verify@example.test>"

    @staticmethod
    def _resend_response(status_code=200, payload=None):
        request = httpx.Request("POST", "https://api.resend.com/emails")
        return httpx.Response(status_code, json=payload, request=request)

    @staticmethod
    def _brevo_response(status_code=201, payload=None):
        request = httpx.Request("POST", "https://api.brevo.com/v3/smtp/email")
        return httpx.Response(status_code, json=payload, request=request)

    def test_resend_configuration_uses_expected_environment_variable_names(self):
        with patch.dict(os.environ, {
            "EMAIL_PROVIDER": "resend",
            "RESEND_API_KEY": "test_resend_key_not_real",
            "EMAIL_FROM": "ONPay <verify@example.test>",
        }):
            configured = Settings(_env_file=None)
        self.assertEqual(configured.email_provider, "resend")
        self.assertEqual(configured.resend_api_key, "test_resend_key_not_real")
        self.assertEqual(configured.email_from, "ONPay <verify@example.test>")

    def test_brevo_configuration_uses_expected_environment_variable_names(self):
        with patch.dict(os.environ, {
            "EMAIL_PROVIDER": "brevo",
            "BREVO_API_KEY": "test_brevo_key_not_real",
            "EMAIL_FROM": "ONPay <verify@example.test>",
        }, clear=False):
            configured = Settings(_env_file=None)
        self.assertEqual(configured.email_provider, "brevo")
        self.assertEqual(configured.brevo_api_key, "test_brevo_key_not_real")
        self.assertEqual(configured.email_from, "ONPay <verify@example.test>")

    def test_production_email_uses_resend_and_never_returns_code(self):
        settings.app_env = "production"
        settings.dev_otp_mode = True  # Production must ignore the development mock flag.
        self._configure_resend()
        with patch("app.main.secrets.randbelow", return_value=123456), patch(
            "app.main.httpx.post", return_value=self._resend_response(payload={"id": "email-test-id"}),
        ) as send:
            response = request_otp(OTPRequest(channel="email", contact="new@example.edu", intent="signup", full_name="New Student"), self.db)
            self.assertNotIn("development_code", response)
            send.assert_called_once()
        url, = send.call_args.args
        options = send.call_args.kwargs
        self.assertEqual(url, "https://api.resend.com/emails")
        self.assertEqual(options["headers"]["Authorization"], "Bearer test_resend_key_not_real")
        self.assertEqual(options["headers"]["Content-Type"], "application/json")
        self.assertEqual(options["json"]["from"], "ONPay <verify@example.test>")
        self.assertEqual(options["json"]["to"], ["new@example.edu"])
        self.assertEqual(options["json"]["subject"], "Your ONPay sign-in code")
        self.assertIn("123456", options["json"]["text"])
        self.assertEqual(options["timeout"], 10.0)
        challenge = self.db.get(OTPChallenge, response["challenge_id"])
        self.assertEqual(challenge.delivery_status, "sent")
        self.assertEqual(challenge.provider_ref, "email-test-id")
        self.assertEqual(verify_otp(OTPVerify(challenge_id=challenge.id, code="123456"), Response(), self.db)["user"]["email"], "new@example.edu")
        with self.assertRaises(HTTPException):
            verify_otp(OTPVerify(challenge_id=challenge.id, code="123456"), Response(), self.db)

    def test_production_email_uses_brevo_and_never_returns_code(self):
        settings.app_env = "production"
        settings.dev_otp_mode = False
        self._configure_brevo()
        with patch("app.main.secrets.randbelow", return_value=123456), patch(
            "app.main.httpx.post", return_value=self._brevo_response(payload={"messageId": "brevo-message-id"}),
        ) as send:
            result = request_otp(OTPRequest(
                channel="email", contact="brevo-user@example.edu", intent="signup", full_name="Brevo Student",
            ), self.db)
        self.assertNotIn("development_code", result)
        url, = send.call_args.args
        options = send.call_args.kwargs
        self.assertEqual(url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(options["headers"]["api-key"], "test_brevo_key_not_real")
        self.assertNotIn("Authorization", options["headers"])
        self.assertEqual(options["headers"]["Content-Type"], "application/json")
        self.assertEqual(options["json"]["sender"], {"name": "ONPay", "email": "verify@example.test"})
        self.assertEqual(options["json"]["to"], [{"email": "brevo-user@example.edu"}])
        self.assertEqual(options["json"]["subject"], "Your ONPay sign-in code")
        self.assertIn("123456", options["json"]["textContent"])
        self.assertEqual(options["timeout"], 10.0)
        challenge = self.db.get(OTPChallenge, result["challenge_id"])
        self.assertEqual(challenge.delivery_status, "sent")
        self.assertEqual(challenge.provider_ref, "brevo-message-id")

    def test_brevo_api_error_fails_challenge_without_sensitive_logs(self):
        settings.app_env = "production"
        settings.dev_otp_mode = False
        self._configure_brevo()
        contact = "brevo-rejected@example.edu"
        with patch("app.main.secrets.randbelow", return_value=123456), patch(
            "app.main.httpx.post", return_value=self._brevo_response(401, {"message": "invalid api key"}),
        ), self.assertLogs("onpay.auth", level="WARNING") as logs, self.assertRaises(HTTPException) as failure:
            request_otp(OTPRequest(channel="email", contact=contact, intent="signup", full_name="Rejected Student"), self.db)
        self.assertEqual(failure.exception.status_code, 502)
        challenge = self.db.query(OTPChallenge).filter_by(contact=contact).one()
        self.assertEqual(challenge.delivery_status, "failed")
        self.assertIsNone(challenge.code_hash)
        self.assertIsNone(challenge.provider_ref)
        log_message = "\n".join(logs.output)
        self.assertIn("provider=brevo", log_message)
        self.assertIn("provider_status=401", log_message)
        for sensitive_value in (contact, "123456", "test_brevo_key_not_real", "invalid api key"):
            self.assertNotIn(sensitive_value, log_message)

    def test_brevo_timeout_fails_challenge_safely(self):
        settings.app_env = "production"
        settings.dev_otp_mode = False
        self._configure_brevo()
        contact = "brevo-timeout@example.edu"
        with patch("app.main.httpx.post", side_effect=httpx.TimeoutException("timeout")), self.assertRaises(HTTPException) as failure:
            request_otp(OTPRequest(channel="email", contact=contact, intent="signup", full_name="Timeout Student"), self.db)
        self.assertEqual(failure.exception.status_code, 502)
        challenge = self.db.query(OTPChallenge).filter_by(contact=contact).one()
        self.assertEqual(challenge.delivery_status, "failed")
        self.assertIsNone(challenge.code_hash)

    def test_production_brevo_requires_api_key_and_sender(self):
        settings.app_env = "production"
        settings.dev_otp_mode = False
        configurations = (
            ("brevo-missing-key@example.edu", "", "ONPay <verify@example.test>"),
            ("brevo-missing-sender@example.edu", "test_brevo_key_not_real", ""),
        )
        for contact, api_key, email_from in configurations:
            settings.email_provider = "brevo"
            settings.brevo_api_key = api_key
            settings.email_from = email_from
            with self.subTest(contact=contact), patch("app.main.httpx.post") as send, self.assertRaises(HTTPException) as failure:
                request_otp(OTPRequest(channel="email", contact=contact, intent="signup", full_name="Missing Config"), self.db)
            self.assertEqual(failure.exception.status_code, 503)
            send.assert_not_called()
            challenge = self.db.query(OTPChallenge).filter_by(contact=contact).one()
            self.assertEqual(challenge.delivery_status, "failed")
            self.assertIsNone(challenge.code_hash)

    def test_resend_provider_rejection_marks_challenge_failed_without_sensitive_logs(self):
        settings.app_env = "production"
        settings.dev_otp_mode = True
        self._configure_resend()
        contact = "rejected@example.edu"
        with patch("app.main.secrets.randbelow", return_value=123456), patch(
            "app.main.httpx.post", return_value=self._resend_response(403, {"message": "rejected"}),
        ), self.assertLogs("onpay.auth", level="WARNING") as logs, self.assertRaises(HTTPException) as failure:
            request_otp(OTPRequest(channel="email", contact=contact, intent="signup", full_name="Rejected Student"), self.db)
        self.assertEqual(failure.exception.status_code, 502)
        challenge = self.db.query(OTPChallenge).filter_by(contact=contact).one()
        self.assertEqual(challenge.delivery_status, "failed")
        self.assertIsNone(challenge.code_hash)
        log_message = "\n".join(logs.output)
        self.assertIn("provider=resend", log_message)
        self.assertIn("provider_status=403", log_message)
        for sensitive_value in (contact, "123456", "test_resend_key_not_real", "rejected"):
            self.assertNotIn(sensitive_value, log_message)

    def test_resend_timeout_and_connection_failures_mark_challenge_failed(self):
        settings.app_env = "production"
        self._configure_resend()
        failures = (
            ("timeout@example.edu", httpx.TimeoutException("timeout")),
            ("connection@example.edu", httpx.ConnectError(
                "connection failed", request=httpx.Request("POST", "https://api.resend.com/emails"),
            )),
        )
        for contact, failure in failures:
            with self.subTest(failure_type=type(failure).__name__), patch(
                "app.main.httpx.post", side_effect=failure,
            ), self.assertRaises(HTTPException) as response:
                request_otp(OTPRequest(channel="email", contact=contact, intent="signup", full_name="Network Failure"), self.db)
            self.assertEqual(response.exception.status_code, 502)
            challenge = self.db.query(OTPChallenge).filter_by(contact=contact).one()
            self.assertEqual(challenge.delivery_status, "failed")
            self.assertIsNone(challenge.code_hash)
            self.assertIsNone(challenge.provider_ref)

    def test_malformed_resend_acceptance_response_is_a_delivery_failure(self):
        settings.app_env = "production"
        self._configure_resend()
        malformed_responses = (
            self._resend_response(payload={"message": "no id"}),
            httpx.Response(
                200, content=b"not-json", headers={"Content-Type": "application/json"},
                request=httpx.Request("POST", "https://api.resend.com/emails"),
            ),
        )
        for index, malformed_response in enumerate(malformed_responses):
            contact = f"malformed-{index}@example.edu"
            with self.subTest(index=index), patch(
                "app.main.httpx.post", return_value=malformed_response,
            ), self.assertRaises(HTTPException) as failure:
                request_otp(OTPRequest(channel="email", contact=contact, intent="signup", full_name="Malformed Response"), self.db)
            self.assertEqual(failure.exception.status_code, 502)
            challenge = self.db.query(OTPChallenge).filter_by(contact=contact).one()
            self.assertEqual(challenge.delivery_status, "failed")
            self.assertIsNone(challenge.code_hash)

    def test_production_never_falls_back_to_smtp(self):
        settings.app_env = "production"
        self._configure_resend()
        settings.email_provider = "smtp"
        with patch("app.main.httpx.post") as send, self.assertRaises(HTTPException) as failure:
            request_otp(OTPRequest(channel="email", contact="no-fallback@example.edu", intent="signup", full_name="No Fallback"), self.db)
        self.assertEqual(failure.exception.status_code, 503)
        send.assert_not_called()
        challenge = self.db.query(OTPChallenge).filter_by(contact="no-fallback@example.edu").one()
        self.assertEqual(challenge.delivery_status, "failed")
        self.assertIsNone(challenge.code_hash)

    def test_production_resend_requires_api_key_and_sender(self):
        settings.app_env = "production"
        settings.dev_otp_mode = True  # Production must ignore the development mock flag.
        configurations = (
            ("missing-key@example.edu", "", "ONPay <verify@example.test>"),
            ("missing-sender@example.edu", "test_resend_key_not_real", ""),
        )
        for contact, api_key, email_from in configurations:
            settings.email_provider = "resend"
            settings.resend_api_key = api_key
            settings.email_from = email_from
            with self.subTest(contact=contact), patch("app.main.httpx.post") as send, self.assertRaises(HTTPException) as failure:
                request_otp(OTPRequest(channel="email", contact=contact, intent="signup", full_name="Missing Config"), self.db)
            self.assertEqual(failure.exception.status_code, 503)
            send.assert_not_called()
            challenge = self.db.query(OTPChallenge).filter_by(contact=contact).one()
            self.assertEqual(challenge.delivery_status, "failed")
            self.assertIsNone(challenge.code_hash)

    def test_challenge_is_hashed_and_committed_before_delivery(self):
        settings.app_env = "production"
        settings.dev_otp_mode = False

        def verify_persisted_challenge(channel, contact, code):
            challenge = self.db.query(OTPChallenge).filter_by(contact=contact).one()
            self.assertEqual(challenge.delivery_status, "pending")
            self.assertEqual(challenge.code_hash, hash_otp(code))
            self.assertNotEqual(challenge.code_hash, code)
            return "provider-reference"

        with patch("app.main.secrets.randbelow", return_value=123456) as generate_code, patch(
            "app.main.deliver_otp", side_effect=verify_persisted_challenge,
        ):
            result = request_otp(OTPRequest(
                channel="email", contact="persisted@example.edu", intent="signup", full_name="Persisted Student",
            ), self.db)

        generate_code.assert_called_once_with(1_000_000)
        self.assertTrue(result["accepted"])
        self.assertNotIn("development_code", result)
        challenge = self.db.get(OTPChallenge, result["challenge_id"])
        self.assertEqual(challenge.delivery_status, "sent")
        self.assertEqual(challenge.provider_ref, "provider-reference")

    def test_production_mobile_otp_without_twilio_settings_fails_safely(self):
        settings.app_env = "production"
        settings.dev_otp_mode = True  # Production must ignore the development mock flag.
        with self.assertRaises(HTTPException) as failure:
            request_otp(OTPRequest(channel="mobile", contact="+14155552671", intent="signup", full_name="SMS Student"), self.db)
        self.assertEqual(failure.exception.status_code, 503)
        self.assertIn("Mobile verification is not configured", failure.exception.detail)
        challenge = self.db.query(OTPChallenge).filter_by(contact="+14155552671").one()
        self.assertEqual(challenge.delivery_status, "failed")
        self.assertIsNone(challenge.code_hash)

    def test_cross_site_session_cookie_and_logout_share_secure_cookie_policy(self):
        settings.session_cookie_samesite = "none"
        response = Response()
        create_session(response, self.db, self.requester)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=none", cookie)
        cookie_pair = response.headers["set-cookie"].split(";", 1)[0]
        from starlette.requests import Request
        request = Request({
            "type": "http", "method": "POST", "scheme": "https", "path": "/api/auth/logout",
            "query_string": b"", "headers": [(b"cookie", cookie_pair.encode())],
        })
        logout_response = Response()
        self.assertEqual(logout(request, logout_response, self.db), {"ok": True})
        cleared_cookie = logout_response.headers["set-cookie"].lower()
        self.assertIn("secure", cleared_cookie)
        self.assertIn("samesite=none", cleared_cookie)

    def test_production_email_requires_resend_configuration(self):
        settings.app_env = "production"
        settings.dev_otp_mode = False
        with patch("app.main.httpx.post") as send, self.assertRaises(HTTPException) as failure:
            request_otp(OTPRequest(channel="email", contact="missing-creds@example.edu", intent="signup", full_name="New Student"), self.db)
        self.assertEqual(failure.exception.status_code, 503)
        send.assert_not_called()
        challenge = self.db.query(OTPChallenge).filter_by(contact="missing-creds@example.edu").one()
        self.assertEqual(challenge.delivery_status, "failed")
        self.assertIsNone(challenge.code_hash)

    def test_health_route_and_cors_preflight_configuration(self):
        origin = "http://localhost:5173"
        self.assertEqual(health()["status"], "ok")
        self.assertIn("/api/auth/otp/request", fastapi_app.openapi()["paths"])
        self.assertIn(origin, settings.get_cors_origins())
        self.assertIn("https://onpay.example.test", settings.get_cors_origins())
        self.assertNotIn("*", settings.get_cors_origins())

        self.assertIsInstance(app, CORSMiddleware)
        self.assertIs(app.app, fastapi_app)
        self.assertEqual(cors_options["allow_origins"], settings.get_cors_origins())
        self.assertNotIn("*", cors_options["allow_origins"])
        middleware = app

        def preflight(request_origin):
            scope = {
                "type": "http", "method": "OPTIONS", "scheme": "https", "path": "/api/auth/otp/request",
                "query_string": b"", "headers": [
                    (b"origin", request_origin.encode()),
                    (b"access-control-request-method", b"POST"),
                    (b"access-control-request-headers", b"content-type"),
                ],
            }
            return middleware.preflight_response(Headers(raw=scope["headers"]))

        allowed = preflight(origin)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers["access-control-allow-origin"], origin)
        self.assertEqual(allowed.headers["access-control-allow-credentials"], "true")
        self.assertIn("POST", allowed.headers["access-control-allow-methods"])
        self.assertIn("content-type", allowed.headers["access-control-allow-headers"].lower())

        rejected = preflight("https://untrusted.example.test")
        self.assertEqual(rejected.status_code, 400)
        self.assertNotIn("access-control-allow-origin", rejected.headers)

    def test_startup_rejects_development_otp_mode_outside_development(self):
        settings.app_env = "production"
        settings.dev_otp_mode = True
        with patch("app.main.Base.metadata.create_all") as create_all:
            with self.assertRaisesRegex(RuntimeError, "DEV_OTP_MODE"):
                startup()
        create_all.assert_not_called()

    def test_development_mock_must_be_explicit_and_resend_has_cooldown(self):
        settings.dev_otp_mode = False
        with self.assertRaises(HTTPException):
            request_otp(OTPRequest(channel="email", contact="no-mock@example.edu", intent="signup", full_name="New Student"), self.db)
        self._configure_resend()
        with patch("app.main.httpx.post", return_value=self._resend_response(payload={"id": "development-disabled-mock"})) as send:
            challenge = request_otp(OTPRequest(channel="email", contact="real-smtp@example.edu", intent="signup", full_name="New Student"), self.db)
        send.assert_called_once()
        self.assertNotIn("development_code", challenge)

        settings.dev_otp_mode = True
        settings.email_provider = "brevo"
        settings.brevo_api_key = ""
        with patch("app.main.httpx.post") as send:
            mocked = request_otp(OTPRequest(channel="email", contact="mock@example.edu", intent="signup", full_name="Mock Student"), self.db)
        send.assert_not_called()
        self.assertIn("development_code", mocked)
        with self.assertRaises(HTTPException) as limited:
            request_otp(OTPRequest(channel="email", contact="mock@example.edu", intent="signup", full_name="Mock Student"), self.db)
        self.assertEqual(limited.exception.status_code, 429)

    def test_auth_request_hides_account_existence_and_expired_codes_are_rejected(self):
        existing_signup = request_otp(OTPRequest(channel="email", contact="riya@example.edu", intent="signup", full_name="Duplicate"), self.db)
        absent_login = request_otp(OTPRequest(channel="email", contact="absent@example.edu", intent="login"), self.db)
        self.assertEqual(set(existing_signup), set(absent_login))
        self.assertNotIn("development_code", existing_signup)

        settings.dev_otp_mode = True
        challenge = request_otp(OTPRequest(channel="email", contact="expired@example.edu", intent="signup", full_name="New Student"), self.db)
        row = self.db.get(OTPChallenge, challenge["challenge_id"])
        row.expires_at = now_utc() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException):
            verify_otp(OTPVerify(challenge_id=row.id, code=challenge["development_code"]), Response(), self.db)

    def test_otp_verification_attempt_limit_is_enforced(self):
        with patch("app.main.secrets.randbelow", return_value=123456):
            challenge = request_otp(OTPRequest(channel="email", contact="attempts@example.edu", intent="signup", full_name="Attempt Student"), self.db)
        for _ in range(settings.otp_max_attempts):
            with self.assertRaises(HTTPException) as invalid:
                verify_otp(OTPVerify(challenge_id=challenge["challenge_id"], code="000000"), Response(), self.db)
            self.assertEqual(invalid.exception.status_code, 400)
        with self.assertRaises(HTTPException) as locked:
            verify_otp(OTPVerify(challenge_id=challenge["challenge_id"], code=challenge["development_code"]), Response(), self.db)
        self.assertEqual(locked.exception.status_code, 429)

    def test_production_mobile_otp_uses_twilio_verify_end_to_end(self):
        settings.app_env = "production"
        settings.dev_otp_mode = True  # Production must use Twilio despite the development flag.
        settings.twilio_account_sid = "AC-test-account"
        settings.twilio_auth_token = "test-token"
        settings.twilio_verify_service_sid = "VA-test-service"

        def provider_response(payload):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = json.dumps(payload).encode()
            return response

        with patch("app.main.urllib.request.urlopen", side_effect=[
            provider_response({"sid": "VE-test-verification", "status": "pending"}),
            provider_response({"sid": "VE-test-verification", "status": "approved"}),
        ]) as urlopen:
            sent = request_otp(OTPRequest(channel="mobile", contact="+14155552671", intent="signup", full_name="SMS Student"), self.db)
            self.assertNotIn("development_code", sent)
            challenge = self.db.get(OTPChallenge, sent["challenge_id"])
            self.assertEqual(challenge.delivery_status, "sent")
            self.assertEqual(challenge.provider_ref, "VE-test-verification")
            self.assertIsNone(challenge.code_hash)
            result = verify_otp(OTPVerify(challenge_id=challenge.id, code="123456"), Response(), self.db)

        self.assertEqual(result["user"]["phone"], "+14155552671")
        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("/Verifications", urlopen.call_args_list[0].args[0].full_url)
        self.assertIn("/VerificationCheck", urlopen.call_args_list[1].args[0].full_url)
        self.assertIn("Code=123456", urlopen.call_args_list[1].args[0].data.decode())

    def test_location_is_rounded_and_nearby_filter_uses_coordinates_without_returning_them(self):
        listing = create_listing(ListingCreate(
            kind="have", amount_min=50000, amount_max=50000, location="Campus library",
            latitude=37.774912, longitude=-122.419412, availability="Today after 2 PM", note="",
        ), self.provider, self.db)["listing"]
        stored = self.db.get(Listing, listing["id"])
        self.assertEqual(stored.latitude, 37.775)
        self.assertEqual(stored.longitude, -122.419)
        nearby = get_listings("all", None, None, "", "", 37.775, -122.419, 2, self.requester, self.db)
        self.assertEqual(len(nearby["listings"]), 1)
        self.assertLessEqual(nearby["listings"][0]["distance_km"], 0.1)
        self.assertNotIn("latitude", nearby["listings"][0])
        self.assertNotIn("longitude", nearby["listings"][0])
        far = get_listings("all", None, None, "", "", 40.7128, -74.0060, 2, self.requester, self.db)
        self.assertEqual(far["listings"], [])
        self.assertGreater(haversine_km(37.775, -122.419, 40.713, -74.006), 4000)

    def test_reverse_geocoder_caches_provider_locality_and_prioritizes_campus(self):
        settings.reverse_geocoder_user_agent = "ONPay tests"
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({
            "address": {"campus": "Test Campus", "city": "Test City", "state": "Test State"},
        }).encode()
        with patch("app.main.urllib.request.urlopen", return_value=response) as urlopen:
            first = reverse_geocode(12.12341, 77.12341)
            second = reverse_geocode(12.12342, 77.12342)
            endpoint_result = location_reverse(12.12341, 77.12341, self.requester)
        self.assertEqual(first, "Test Campus, Test State")
        self.assertEqual(first, second)
        self.assertEqual(endpoint_result["status"], "resolved")
        self.assertEqual(endpoint_result["label"], "Test Campus, Test State")
        self.assertTrue(endpoint_result["attribution"])
        urlopen.assert_called_once()
        self.assertEqual(urlopen.call_args.args[0].get_header("User-agent"), "ONPay tests")

    def test_reverse_geocoder_reports_missing_user_agent_without_returning_a_fake_place(self):
        settings.reverse_geocoder_user_agent = ""
        with self.assertLogs("onpay.auth", level="WARNING") as logs:
            result = location_reverse(89.111, 12.333, self.requester)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["label"])
        self.assertEqual(result["reason"], "missing_user_agent")
        self.assertIn("reason=missing_user_agent", "\n".join(logs.output))

    def test_reverse_geocoder_logs_provider_failure_without_coordinates(self):
        settings.reverse_geocoder_user_agent = "ONPay tests"
        with patch("app.main.urllib.request.urlopen", side_effect=OSError("provider unavailable")), \
                self.assertLogs("onpay.auth", level="WARNING") as logs:
            result = location_reverse(-79.123, 123.456, self.requester)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["label"])
        self.assertEqual(result["reason"], "provider_unavailable")
        log_message = "\n".join(logs.output)
        self.assertIn("reason=provider_error", log_message)
        self.assertNotIn("-79.123", log_message)
        self.assertNotIn("123.456", log_message)

    def test_manual_location_can_be_saved_and_loaded_for_current_user(self):
        saved = set_location({"label": "  Aditya University  "}, self.requester, self.db)
        self.assertEqual(saved["stored_location"], "Aditya University")
        settings_response = location_settings(self.requester)
        self.assertEqual(settings_response["stored_location"], "Aditya University")
        self.assertIn("not stored in your profile", settings_response["privacy"])

        cleared = set_location({"label": " "}, self.requester, self.db)
        self.assertIsNone(cleared["stored_location"])
        self.assertIsNone(location_settings(self.requester)["stored_location"])

    def _exchange(self, suffix: int, status: str, completed_at=None):
        request_listing = Listing(id=f"request-{suffix}", owner_id=self.requester.id, kind="need", amount_min=100,
                                  amount_max=100, location="Campus", availability="Any time", status="matched")
        offer_listing = Listing(id=f"offer-{suffix}", owner_id=self.provider.id, kind="have", amount_min=100,
                                amount_max=100, location="Campus", availability="Any time", status="matched")
        exchange = Exchange(id=f"exchange-{suffix}", listing_id=request_listing.id, matched_listing_id=offer_listing.id,
                            requester_id=self.requester.id, provider_id=self.provider.id, amount=100,
                            location="Campus", meetup_at="Any time", status=status, completed_at=completed_at)
        self.db.add_all((request_listing, offer_listing))
        self.db.flush()
        self.db.add(exchange)

    def test_calendar_month_usage_counts_only_completed_and_reserves_active_slots(self):
        now = now_utc()
        for suffix in range(4):
            self._exchange(suffix, "success", now)
        self._exchange(4, "awaiting_meetup")
        self._exchange(5, "failed")
        self._exchange(6, "cancelled")
        self.db.commit()
        self.assertEqual(monthly_usage(self.db, self.requester.id), (4, 1))
        usage = subscriptions(self.requester, self.db)
        self.assertEqual(usage["usage"], 4)
        self.assertEqual(usage["reserved"], 1)
        self.assertEqual(usage["remaining"], 0)
        with self.assertRaises(HTTPException):
            check_quota(self.db, self.requester)

    def test_plan_prices_plus_quota_premium_unlimited_and_expiration(self):
        data = subscriptions(self.requester, self.db)
        plans = {plan["id"]: plan for plan in data["plans"]}
        self.assertEqual((plans["plus"]["price_inr"], plans["plus"]["limit"]), (199, 20))
        self.assertEqual((plans["premium"]["name"], plans["premium"]["price_inr"], plans["premium"]["limit"]), ("Premium", 499, None))
        premium = Subscription(id="premium-sub", user_id=self.requester.id, plan="premium", status="active",
                               starts_at=now_utc(), expires_at=None)
        self.requester.plan = "premium"
        self.db.add(premium)
        self.db.commit()
        self.assertIsNone(subscriptions(self.requester, self.db)["remaining"])
        premium.expires_at = now_utc() - timedelta(days=1)
        self.db.commit()
        expired = subscriptions(self.requester, self.db)
        self.assertEqual(expired["current_plan"], "free")
        self.assertEqual(self.db.get(Subscription, premium.id).status, "expired")

    def test_calendar_month_uses_india_midnight_boundaries(self):
        start, end = current_month_bounds(now_utc().replace(year=2026, month=10, day=31, hour=20, minute=0))
        self.assertEqual(start.isoformat(), "2026-10-31T18:30:00")
        self.assertEqual(end.isoformat(), "2026-11-30T18:30:00")


if __name__ == "__main__":
    unittest.main()
