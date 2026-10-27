from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "production"
    secret_key: str = "development-only-change-me"
    database_url: str = "sqlite:///./onpay.db"
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str = ""
    session_ttl_hours: int = 168
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    otp_ttl_minutes: int = 5
    otp_resend_seconds: int = 30
    otp_max_attempts: int = 5
    dev_otp_mode: bool = False
    email_provider: Literal["resend"] = "resend"
    resend_api_key: str = ""
    email_from: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_verify_service_sid: str = ""
    youpi_webhook_secret: str = ""
    reconciliation_token: str = ""
    reverse_geocoder_url: str = "https://nominatim.openstreetmap.org/reverse"
    reverse_geocoder_user_agent: str = ""
    reverse_geocoder_attribution: str = "© OpenStreetMap contributors"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def get_cors_origins(self) -> list[str]:
        origins = [item.strip().rstrip("/") for item in self.frontend_origins.split(",") if item.strip()]
        legacy_origin = self.frontend_origin.strip().rstrip("/")
        local_origins = {"http://localhost:5173", "http://127.0.0.1:5173"}
        if legacy_origin and (self.app_env.lower() == "development" or legacy_origin not in local_origins):
            origins.append(legacy_origin)
        if self.app_env.lower() == "development":
            origins.extend(sorted(local_origins))
        return list(dict.fromkeys(origins))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
