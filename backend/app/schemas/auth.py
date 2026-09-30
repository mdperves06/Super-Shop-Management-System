from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import Num, ORMModel, UTCDateTime

PASSWORD_MIN = 8


def _check_password(v: str) -> str:
    if len(v) < PASSWORD_MIN:
        raise ValueError(f"Password must be at least {PASSWORD_MIN} characters")
    if v.isalpha() or v.isdigit():
        raise ValueError("Password must contain letters and numbers")
    return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    otp: str | None = Field(default=None, max_length=10)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str | None = None  # browsers send the HttpOnly cookie instead


class RoleOut(ORMModel):
    id: int
    name: str
    description: str
    is_system: bool


class RoleDetail(RoleOut):
    permissions: list[str]


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    language: str
    totp_enabled: bool
    must_change_password: bool
    last_login_at: UTCDateTime | None
    max_discount_percent: Num | None
    role_names: list[str]


class MeOut(UserOut):
    permissions: list[str]
    landing_path: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    password: str
    role_ids: list[int] = Field(min_length=1)
    max_discount_percent: float | None = Field(default=None, ge=0, le=100)
    must_change_password: bool = False

    _pw = field_validator("password")(_check_password)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = None
    is_active: bool | None = None
    role_ids: list[int] | None = None
    max_discount_percent: float | None = Field(default=None, ge=0, le=100)
    password: str | None = None

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str | None) -> str | None:
        return _check_password(v) if v else v


class ChangePassword(BaseModel):
    current_password: str
    new_password: str

    _pw = field_validator("new_password")(_check_password)


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str
    new_password: str

    _pw = field_validator("new_password")(_check_password)


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = None
    language: str | None = Field(default=None, pattern="^(en|bn)$")


class TotpSetup(BaseModel):
    secret: str
    otpauth_uri: str


class TotpCode(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = ""
    permissions: list[str]


class RoleUpdate(BaseModel):
    description: str | None = None
    permissions: list[str] | None = None


class PermissionOut(ORMModel):
    code: str
    module: str
    description: str
