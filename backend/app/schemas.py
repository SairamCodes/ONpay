from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_validator


class OTPRequest(BaseModel):
    channel: Literal["mobile", "email"]
    contact: str = Field(min_length=5, max_length=254)
    intent: Literal["signup", "login"]
    full_name: str | None = Field(default=None, max_length=100)
    college: str | None = Field(default=None, max_length=140)

    @field_validator("contact")
    @classmethod
    def normalize_contact(cls, value: str) -> str:
        return value.strip().lower()


class OTPVerify(BaseModel):
    challenge_id: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ListingCreate(BaseModel):
    kind: Literal["need", "have"]
    amount_min: int = Field(gt=0, le=250000)
    amount_max: int = Field(gt=0, le=250000)
    location: str = Field(min_length=2, max_length=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    availability: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=500)

    @field_validator("location", "availability", "note")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("longitude")
    @classmethod
    def coordinates_are_paired(cls, value: float | None, info):
        latitude = info.data.get("latitude")
        if (latitude is None) != (value is None):
            raise ValueError("Latitude and longitude must be supplied together")
        return value


class ListingUpdate(BaseModel):
    status: Literal["active", "paused", "cancelled"]


class AcceptListing(BaseModel):
    amount: int = Field(gt=0, le=250000)


class ArrivalUpdate(BaseModel):
    arrived: bool


class CashConfirmation(BaseModel):
    handed_over: bool


class PaymentCreate(BaseModel):
    exchange_id: str
    payee_upi: str = Field(min_length=3, max_length=100)


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def trim_body(cls, value: str) -> str:
        return value.strip()


class ReportCreate(BaseModel):
    user_id: str
    exchange_id: str | None = None
    category: str = Field(min_length=2, max_length=60)
    details: str = Field(default="", max_length=2000)


class ReconciliationRequest(BaseModel):
    payment_id: str
    utr: str = Field(min_length=8, max_length=32, pattern=r"^[A-Za-z0-9-]+$")
    verified_from_bank_record: bool


class BlockCreate(BaseModel):
    user_id: str


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    college: str | None = Field(default=None, max_length=140)


class NotificationOut(BaseModel):
    id: str
    title: str
    body: str
    kind: str
    read_at: datetime | None
    created_at: datetime
