from functools import lru_cache
from typing import Literal
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "production"
    secret_key: str = "development-only-change-me"
    database_url: str = "sqlite:///./onpay.db"
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str = ""
    session_ttl_hours: int = 168
    session_cookie_samesite: Literal["lax", "strict", "none"] | None = None
    otp_ttl_minutes: int = 5
    otp_resend_seconds: int = 30
    otp_max_attempts: int = 5
    dev_otp_mode: bool = False
    email_provider: Literal["mailjet", "resend", "brevo", "smtp"] = "mailjet"
    mailjet_api_key: str = ""
    mailjet_secret_key: str = ""
    resend_api_key: str = ""
    brevo_api_key: str = ""
    email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    pro_plan_price_inr: int | None = Field(default=None, ge=0)
    pro_plan_billing_period: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_verify_service_sid: str = ""
    youpi_webhook_secret: str = ""
    reconciliation_token: str = ""
    reverse_geocoder_url: str = "https://nominatim.openstreetmap.org/reverse"
    reverse_geocoder_user_agent: str = ""
    reverse_geocoder_attribution: str = "© OpenStreetMap contributors"
    match_request_ttl_minutes: int = 30
    listing_expiry_hours: int = 24
    completion_points_award: int = 10

    # Storage & Persistence (Supabase / Persistent Disk)
    uploads_dir: str = Field(
        default="",
        validation_alias=AliasChoices("uploads_dir", "upload_dir", "UPLOADS_DIR", "UPLOAD_DIR"),
    )
    upload_storage_provider: Literal["supabase", "local"] = Field(
        default="local",
        validation_alias=AliasChoices("upload_storage_provider", "UPLOAD_STORAGE_PROVIDER"),
    )
    supabase_url: str = Field(
        default="",
        validation_alias=AliasChoices("supabase_url", "SUPABASE_URL"),
    )
    supabase_service_role_key: str = Field(
        default="",
        validation_alias=AliasChoices("supabase_service_role_key", "SUPABASE_SERVICE_ROLE_KEY"),
    )
    supabase_subscription_bucket: str = Field(
        default="subscription-proofs",
        validation_alias=AliasChoices("supabase_subscription_bucket", "SUPABASE_SUBSCRIPTION_BUCKET"),
    )
    supabase_qr_bucket: str = Field(
        default="admin-qr-codes",
        validation_alias=AliasChoices("supabase_qr_bucket", "SUPABASE_QR_BUCKET"),
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def get_uploads_dir(self):
        from pathlib import Path
        if self.uploads_dir and self.uploads_dir.strip():
            p = Path(self.uploads_dir.strip()).resolve()
            p.mkdir(parents=True, exist_ok=True)
            return p
        default_p = Path(__file__).resolve().parent.parent / "uploads"
        default_p.mkdir(parents=True, exist_ok=True)
        return default_p

    def get_cors_origins(self) -> list[str]:
        origins = [
            item.strip().rstrip("/")
            for item in self.frontend_origins.split(",")
            if item.strip() and item.strip() != "*"
        ]
        legacy_origin = self.frontend_origin.strip().rstrip("/")
        local_origins = {
            "http://localhost:5173", "http://127.0.0.1:5173",
            "http://localhost:5174", "http://127.0.0.1:5174",
        }
        if legacy_origin and legacy_origin != "*" and (self.app_env.lower() == "development" or legacy_origin not in local_origins):
            origins.append(legacy_origin)
        if self.app_env.lower() == "development":
            origins.extend(sorted(local_origins))
        return list(dict.fromkeys(origins))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
