"""Automated tests for Supabase Storage Integration and Local Persistence.

Tests file validation, mock Supabase upload/download/signed URLs,
backward compatibility with legacy local files, private access security,
and configurable persistent disk directories.
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from app.config import Settings, settings
from app.storage import (
    DEFAULT_SIGNED_URL_TTL,
    MAX_FILE_SIZE_BYTES,
    StorageService,
    validate_image_file,
)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.storage = StorageService()
        self.jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        self.png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        self.webp_bytes = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100

    # 1. Validation tests
    def test_valid_image_types(self):
        mime, ext = validate_image_file(self.jpeg_bytes)
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(ext, "jpg")

        mime, ext = validate_image_file(self.png_bytes)
        self.assertEqual(mime, "image/png")
        self.assertEqual(ext, "png")

        mime, ext = validate_image_file(self.webp_bytes)
        self.assertEqual(mime, "image/webp")
        self.assertEqual(ext, "webp")

    def test_oversized_file_rejection(self):
        oversized = b"\xff\xd8\xff" + b"\x00" * (MAX_FILE_SIZE_BYTES + 10)
        with self.assertRaises(HTTPException) as ctx:
            validate_image_file(oversized)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("exceeds maximum allowed size", ctx.exception.detail)

    def test_invalid_magic_bytes_rejection(self):
        bad_data = b"NOT_AN_IMAGE_FILE_DATA_HERE"
        with self.assertRaises(HTTPException) as ctx:
            validate_image_file(bad_data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Only JPEG, PNG, or WEBP", ctx.exception.detail)

    # 2. Local Persistent Storage Directory Configuration
    def test_configurable_uploads_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_settings = Settings(
                uploads_dir=tmp_dir,
                upload_storage_provider="local",
            )
            with patch("app.storage.settings", custom_settings):
                s = StorageService()
                proofs_dir = s.get_local_proofs_dir()
                self.assertTrue(str(proofs_dir).startswith(str(Path(tmp_dir).resolve())))
                self.assertTrue(proofs_dir.exists())

                uri, mime, size = s.upload_subscription_proof(self.png_bytes, "test.png")
                self.assertTrue(os.path.exists(uri))
                self.assertTrue(uri.startswith(str(proofs_dir)))

    # 3. Missing Supabase Credentials Rejection
    def test_missing_supabase_credentials(self):
        custom_settings = Settings(
            upload_storage_provider="supabase",
            supabase_url="",
            supabase_service_role_key="",
        )
        with patch("app.storage.settings", custom_settings):
            s = StorageService()
            self.assertFalse(s.is_supabase_enabled())
            with self.assertRaises(RuntimeError) as ctx:
                s.get_supabase_client()
            self.assertIn("credentials missing", str(ctx.exception).lower())

    # 4. Mocked Supabase Subscription Proof Upload
    def test_supabase_subscription_proof_upload(self):
        mock_client = MagicMock()
        mock_bucket_proxy = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket_proxy

        custom_settings = Settings(
            upload_storage_provider="supabase",
            supabase_url="https://xyzproject.supabase.co",
            supabase_service_role_key="secret-service-role-key-test",
            supabase_subscription_bucket="subscription-proofs",
        )
        with patch("app.storage.settings", custom_settings):
            s = StorageService()
            s._supabase_client = mock_client

            uri, mime, size = s.upload_subscription_proof(self.png_bytes, "receipt.png")
            self.assertTrue(uri.startswith("supabase://subscription-proofs/proofs/proof_"))
            self.assertTrue(uri.endswith(".png"))
            self.assertEqual(mime, "image/png")
            self.assertEqual(size, len(self.png_bytes))

            # Verify client was called with correct bucket and parameters
            mock_client.storage.from_.assert_called_with("subscription-proofs")
            mock_bucket_proxy.upload.assert_called_once()
            call_kwargs = mock_bucket_proxy.upload.call_args[1]
            self.assertEqual(call_kwargs["file"], self.png_bytes)
            self.assertEqual(call_kwargs["file_options"]["content-type"], "image/png")
            self.assertEqual(call_kwargs["file_options"]["upsert"], "false")

    # 5. Mocked Supabase Admin QR Upload
    def test_supabase_admin_qr_upload(self):
        mock_client = MagicMock()
        mock_bucket_proxy = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket_proxy

        custom_settings = Settings(
            upload_storage_provider="supabase",
            supabase_url="https://xyzproject.supabase.co",
            supabase_service_role_key="secret-service-role-key-test",
            supabase_qr_bucket="admin-qr-codes",
        )
        with patch("app.storage.settings", custom_settings):
            s = StorageService()
            s._supabase_client = mock_client

            uri, mime, size = s.upload_admin_qr(self.jpeg_bytes, "qr.jpg")
            self.assertTrue(uri.startswith("supabase://admin-qr-codes/qr/qr_"))
            self.assertTrue(uri.endswith(".jpg"))
            self.assertEqual(mime, "image/jpeg")

            mock_client.storage.from_.assert_called_with("admin-qr-codes")
            mock_bucket_proxy.upload.assert_called_once()

    # 6. Signed URL Generation
    def test_signed_url_generation(self):
        mock_client = MagicMock()
        mock_bucket_proxy = MagicMock()
        mock_bucket_proxy.create_signed_url.return_value = {
            "signedURL": "https://xyzproject.supabase.co/storage/v1/object/sign/subscription-proofs/proofs/test.png?token=mocktoken123"
        }
        mock_client.storage.from_.return_value = mock_bucket_proxy

        custom_settings = Settings(
            upload_storage_provider="supabase",
            supabase_url="https://xyzproject.supabase.co",
            supabase_service_role_key="secret-service-role-key-test",
            supabase_subscription_bucket="subscription-proofs",
        )
        with patch("app.storage.settings", custom_settings):
            s = StorageService()
            s._supabase_client = mock_client

            signed_url = s.get_signed_url("supabase://subscription-proofs/proofs/test.png", "subscription-proofs", 180)
            self.assertIn("mocktoken123", signed_url)
            mock_bucket_proxy.create_signed_url.assert_called_with("proofs/test.png", 180)

            # Response returns 307 RedirectResponse to the signed URL
            resp = s.get_file_response("supabase://subscription-proofs/proofs/test.png", "subscription-proofs", "image/png")
            self.assertIsInstance(resp, RedirectResponse)
            self.assertEqual(resp.status_code, 307)
            self.assertEqual(resp.headers["location"], signed_url)

    # 7. Backward Compatibility: Legacy Local File Retrieval
    def test_legacy_local_file_retrieval(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(self.png_bytes)
            local_path = f.name

        try:
            s = StorageService()
            resp = s.get_file_response(local_path, "subscription-proofs", "image/png")
            self.assertIsInstance(resp, FileResponse)
            self.assertEqual(resp.path, local_path)
            self.assertEqual(resp.media_type, "image/png")
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    # 8. Missing Local File Rejection
    def test_missing_local_file_404(self):
        s = StorageService()
        with self.assertRaises(HTTPException) as ctx:
            s.get_file_response("/non/existent/path/proof_999.png", "subscription-proofs", "image/png")
        self.assertEqual(ctx.exception.status_code, 404)

    # 9. CORS No Wildcard with Credentials
    def test_cors_filters_wildcards(self):
        custom = Settings(
            app_env="production",
            frontend_origins="https://onpay.domain.com, *, https://admin.onpay.com",
            frontend_origin="http://localhost:5173",
        )
        cors = custom.get_cors_origins()
        self.assertNotIn("*", cors)
        self.assertEqual(cors, ["https://onpay.domain.com", "https://admin.onpay.com"])


if __name__ == "__main__":
    unittest.main()
