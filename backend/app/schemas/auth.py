from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Language, UserRole


class SignupRequest(BaseModel):
    email: EmailStr
    # max_length=72: bcrypt (see auth/security.py) silently ignores bytes
    # past 72 — reject an over-long password with a clear message instead
    # of accepting it and quietly hashing only its first 72 bytes.
    password: str = Field(min_length=8, max_length=72)
    full_name: str
    role: UserRole  # "owner" or "service_provider" — admin accounts are never self-serve
    company_name: str | None = None  # required in practice when role == service provider
    # Stage 9.14: the interface language the visitor signed up in, so an
    # Arabic visitor's account (pages, notifications, emails) is Arabic from the start.
    language: Language = Language.en


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


class VerifyEmailRequest(BaseModel):
    token: str


class LanguageUpdate(BaseModel):
    language: Language


class EmailChangeRequestIn(BaseModel):
    new_email: EmailStr
    current_password: str


class EmailChangeConfirmIn(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
