"""ONPay V2 Storage Service.

Supports both Supabase Private Storage Buckets and Configurable Local Persistent Disks.
Maintains backward compatibility with existing local file records while providing
signed URLs for private Supabase Storage.
"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

from fastapi import HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse, Response

from .config import settings

logger = logging.getLogger("onpay.storage")

# Constants
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_SIGNED_URL_TTL = 300  # 5 minutes


def validate_image_file(data: bytes, max_bytes: int = MAX_FILE_SIZE_BYTES) -> Tuple[str, str]:
    """Validate file size and magic bytes. Returns (mime_type, file_extension)."""
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image file exceeds maximum allowed size ({max_bytes // (1024 * 1024)} MB)",
        )

    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    elif data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, or WEBP images are allowed",
        )


class StorageService:
    def __init__(self):
        self._supabase_client = None

    def get_supabase_client(self):
        """Lazy-initialize Supabase client using server-side service role key."""
        if self._supabase_client is not None:
            return self._supabase_client

        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError(
                "Supabase Storage credentials missing. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
            )

        try:
            from supabase import create_client
            self._supabase_client = create_client(
                settings.supabase_url.strip(),
                settings.supabase_service_role_key.strip(),
            )
            return self._supabase_client
        except Exception as e:
            logger.error("Failed to initialize Supabase client: %s", str(e))
            raise RuntimeError(f"Could not connect to Supabase: {e}")

    def is_supabase_enabled(self) -> bool:
        """Return True if Supabase is selected and has configured credentials."""
        provider = (settings.upload_storage_provider or "").lower().strip()
        has_creds = bool(settings.supabase_url and settings.supabase_service_role_key)
        return provider == "supabase" and has_creds

    # -------------------------------------------------------------------------
    # Local Storage Directory Helpers
    # -------------------------------------------------------------------------
    def get_local_proofs_dir(self) -> Path:
        base = settings.get_uploads_dir()
        d = base / "subscription_proofs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_local_qr_dir(self) -> Path:
        base = settings.get_uploads_dir()
        d = base / "qr_codes"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -------------------------------------------------------------------------
    # Upload Handlers
    # -------------------------------------------------------------------------
    def upload_subscription_proof(self, file_bytes: bytes, original_filename: str = "") -> Tuple[str, str, int]:
        """Validate and upload subscription proof image.
        Returns: (storage_path_or_uri, mime_type, file_size)
        """
        mime_type, ext = validate_image_file(file_bytes)
        file_size = len(file_bytes)
        unique_token = secrets.token_hex(16)
        filename = f"proof_{unique_token}.{ext}"

        if self.is_supabase_enabled():
            bucket = settings.supabase_subscription_bucket
            object_path = f"proofs/{filename}"
            client = self.get_supabase_client()
            logger.info("Uploading subscription proof to Supabase bucket '%s' path '%s'", bucket, object_path)
            client.storage.from_(bucket).upload(
                path=object_path,
                file=file_bytes,
                file_options={"content-type": mime_type, "upsert": "false"},
            )
            uri = f"supabase://{bucket}/{object_path}"
            return uri, mime_type, file_size
        else:
            local_dir = self.get_local_proofs_dir()
            dest = local_dir / filename
            with open(dest, "wb") as f:
                f.write(file_bytes)
            logger.info("Saved subscription proof locally to %s", dest)
            return str(dest), mime_type, file_size

    def upload_admin_qr(self, file_bytes: bytes, original_filename: str = "") -> Tuple[str, str, int]:
        """Validate and upload admin receiving QR code.
        Returns: (storage_path_or_uri, mime_type, file_size)
        """
        mime_type, ext = validate_image_file(file_bytes)
        file_size = len(file_bytes)
        unique_token = secrets.token_hex(16)
        filename = f"qr_{unique_token}.{ext}"

        if self.is_supabase_enabled():
            bucket = settings.supabase_qr_bucket
            object_path = f"qr/{filename}"
            client = self.get_supabase_client()
            logger.info("Uploading admin QR code to Supabase bucket '%s' path '%s'", bucket, object_path)
            client.storage.from_(bucket).upload(
                path=object_path,
                file=file_bytes,
                file_options={"content-type": mime_type, "upsert": "false"},
            )
            uri = f"supabase://{bucket}/{object_path}"
            return uri, mime_type, file_size
        else:
            local_dir = self.get_local_qr_dir()
            dest = local_dir / filename
            with open(dest, "wb") as f:
                f.write(file_bytes)
            logger.info("Saved admin QR code locally to %s", dest)
            return str(dest), mime_type, file_size

    # -------------------------------------------------------------------------
    # Retrieval and Signed URLs
    # -------------------------------------------------------------------------
    def parse_storage_path(self, storage_path_or_uri: str, default_bucket: str) -> Tuple[str, str, bool]:
        """Parse whether path is Supabase or local.
        Returns: (bucket, object_path, is_supabase)
        """
        if storage_path_or_uri.startswith("supabase://"):
            parsed = urlparse(storage_path_or_uri)
            bucket = parsed.netloc or default_bucket
            object_path = parsed.path.lstrip("/")
            return bucket, object_path, True

        # Check explicit Supabase object prefixes
        if storage_path_or_uri.startswith(("proofs/", "qr/")):
            return default_bucket, storage_path_or_uri, True

        return default_bucket, storage_path_or_uri, False

    def get_signed_url(self, storage_path_or_uri: str, default_bucket: str, expires_in: int = DEFAULT_SIGNED_URL_TTL) -> str:
        """Generate temporary signed URL for private Supabase Storage object."""
        bucket, object_path, is_supabase = self.parse_storage_path(storage_path_or_uri, default_bucket)
        if not is_supabase:
            raise ValueError("Cannot generate signed URL for local filesystem path")

        client = self.get_supabase_client()
        res = client.storage.from_(bucket).create_signed_url(object_path, expires_in)
        signed_url = None
        if isinstance(res, dict):
            signed_url = res.get("signedURL") or res.get("signedUrl")
        elif hasattr(res, "signed_url"):
            signed_url = res.signed_url
        elif hasattr(res, "signedURL"):
            signed_url = res.signedURL

        if not signed_url:
            raise RuntimeError(f"Failed to generate signed URL for {object_path}")
        return signed_url

    def get_file_response(
        self,
        storage_path_or_uri: str,
        default_bucket: str,
        mime_type: str,
        expires_in: int = DEFAULT_SIGNED_URL_TTL,
    ) -> Response:
        """Return either a local FileResponse or a 307 RedirectResponse to a Supabase signed URL."""
        bucket, object_path, is_supabase = self.parse_storage_path(storage_path_or_uri, default_bucket)

        if is_supabase:
            signed_url = self.get_signed_url(storage_path_or_uri, default_bucket, expires_in)
            return RedirectResponse(url=signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

        # Local file compatibility check
        local_path = Path(storage_path_or_uri)
        if not local_path.exists():
            # Check if relative to configured uploads directory
            candidate = settings.get_uploads_dir() / storage_path_or_uri
            if candidate.exists():
                local_path = candidate
            else:
                logger.error("Local file not found at %s", storage_path_or_uri)
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        return FileResponse(str(local_path), media_type=mime_type)

    def download_bytes(self, storage_path_or_uri: str, default_bucket: str) -> bytes:
        """Download raw bytes from either local file or Supabase."""
        bucket, object_path, is_supabase = self.parse_storage_path(storage_path_or_uri, default_bucket)
        if is_supabase:
            client = self.get_supabase_client()
            return client.storage.from_(bucket).download(object_path)

        local_path = Path(storage_path_or_uri)
        if not local_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        with open(local_path, "rb") as f:
            return f.read()


# Global Singleton Storage Service
storage_service = StorageService()
