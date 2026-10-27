import re
from datetime import date, datetime, timezone
from enum import Enum
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_validator, model_validator

US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
_NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$", re.UNICODE)
_MEMBER_RE = re.compile(r"^[A-Za-z0-9]+$")
_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")


class Sex(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE = "Decline to Answer"


def normalize_us_phone(value: str) -> str:
    if not re.fullmatch(r"[+0-9().\-\s]+", value) or value.count("+") > 1 or ("+" in value and not re.match(r"^\s*\+1", value)):
        raise ValueError("must be a valid U.S. 10-digit phone number")
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        raise ValueError("must be a valid U.S. 10-digit phone number")
    return digits


class PatientFields(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    date_of_birth: date
    sex: Sex
    phone_number: str
    email: EmailStr | None = None
    address_line_1: str = Field(min_length=1, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=2)
    zip_code: str
    insurance_provider: str | None = Field(default=None, max_length=100)
    insurance_member_id: str | None = Field(default=None, max_length=100)
    preferred_language: str = Field(default="English", min_length=1, max_length=50)
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_names(cls, value: str) -> str:
        value = value.strip()
        if not _NAME_RE.fullmatch(value):
            raise ValueError("must contain alphabetic characters, spaces, hyphens, or apostrophes")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, value: date) -> date:
        if value > datetime.now(timezone.utc).date():
            raise ValueError("date of birth cannot be in the future")
        return value

    @field_validator("phone_number", "emergency_contact_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return normalize_us_phone(value) if value is not None else None

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in US_STATES:
            raise ValueError("must be a valid two-letter U.S. state abbreviation")
        return value

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, value: str) -> str:
        if not _ZIP_RE.fullmatch(value.strip()):
            raise ValueError("must be a 5-digit or ZIP+4 U.S. ZIP code")
        return value.strip()

    @field_validator("insurance_member_id")
    @classmethod
    def validate_member_id(cls, value: str | None) -> str | None:
        if value is not None and not _MEMBER_RE.fullmatch(value):
            raise ValueError("must be alphanumeric")
        return value

    @field_validator("address_line_1", "address_line_2", "city", "insurance_provider", "preferred_language", "emergency_contact_name")
    @classmethod
    def strip_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            if info.field_name in {"address_line_2", "insurance_provider", "emergency_contact_name"}:
                return None
            raise ValueError("must not be blank")
        return value


class PatientCreate(PatientFields):
    pass


class PatientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)
    date_of_birth: date | None = None
    sex: Sex | None = None
    phone_number: str | None = None
    email: EmailStr | None = None
    address_line_1: str | None = Field(default=None, min_length=1, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    zip_code: str | None = None
    insurance_provider: str | None = Field(default=None, max_length=100)
    insurance_member_id: str | None = Field(default=None, max_length=100)
    preferred_language: str | None = Field(default=None, min_length=1, max_length=50)
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = None

    @model_validator(mode="after")
    def require_some_update(self):
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        nullable = {"email", "address_line_2", "insurance_provider", "insurance_member_id", "emergency_contact_name", "emergency_contact_phone"}
        invalid_nulls = [key for key in self.model_fields_set if getattr(self, key) is None and key not in nullable]
        if invalid_nulls:
            raise ValueError(f"these fields cannot be null: {', '.join(invalid_nulls)}")
        return self

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_names(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not _NAME_RE.fullmatch(value):
            raise ValueError("must contain alphabetic characters, spaces, hyphens, or apostrophes")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, value: date | None) -> date | None:
        if value is not None and value > datetime.now(timezone.utc).date():
            raise ValueError("date of birth cannot be in the future")
        return value

    @field_validator("phone_number", "emergency_contact_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return normalize_us_phone(value) if value is not None else None

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().upper()
        if value not in US_STATES:
            raise ValueError("must be a valid two-letter U.S. state abbreviation")
        return value

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, value: str | None) -> str | None:
        if value is not None and not _ZIP_RE.fullmatch(value.strip()):
            raise ValueError("must be a 5-digit or ZIP+4 U.S. ZIP code")
        return value.strip() if value is not None else None

    @field_validator("insurance_member_id")
    @classmethod
    def validate_member_id(cls, value: str | None) -> str | None:
        if value is not None and not _MEMBER_RE.fullmatch(value):
            raise ValueError("must be alphanumeric")
        return value

    @field_validator("address_line_1", "address_line_2", "city", "insurance_provider", "preferred_language", "emergency_contact_name")
    @classmethod
    def strip_update_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            if info.field_name in {"address_line_2", "insurance_provider", "emergency_contact_name"}:
                return None
            raise ValueError("must not be blank")
        return value


class PatientIdentityCheck(BaseModel):
    patient_id: UUID
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    date_of_birth: date

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_identity_name(cls, value: str) -> str:
        return value.strip()


class PatientRead(PatientFields):
    model_config = ConfigDict(from_attributes=True)
    patient_id: UUID
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


T = TypeVar("T")


class ApiError(BaseModel):
    message: str
    details: list[dict[str, object]] | None = None


class ResponseEnvelope(BaseModel, Generic[T]):
    data: T | None = None
    error: ApiError | None = None


class DeleteResult(BaseModel):
    patient_id: UUID
    deleted: bool


class HealthResult(BaseModel):
    status: str
