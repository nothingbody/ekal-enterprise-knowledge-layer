import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def _validate_email_format(email: str) -> str:
    if not _EMAIL_RE.match(email):
        raise ValueError("邮箱格式无效")
    return email


def _validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("密码长度不能少于 8 位")
    if not re.search(r'[A-Za-z]', password):
        raise ValueError("密码必须包含至少一个字母")
    if not re.search(r'\d', password):
        raise ValueError("密码必须包含至少一个数字")
    return password


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: str = Field(min_length=5, max_length=100)
    password: str = Field(min_length=8, max_length=100)
    invite_code: str | None = None

    @field_validator('email')
    @classmethod
    def email_format(cls, v: str) -> str:
        return _validate_email_format(v)

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserLogin(BaseModel):
    username: str
    password: str
    device_id: str | None = None
    device_name: str | None = None
    os_info: str | None = None
    app_version: str | None = None


class UserResponse(BaseModel):
    id: int
    cloud_user_id: int | None = None
    username: str
    email: str
    role: str
    is_active: bool = True
    must_change_password: bool = False
    totp_enabled: bool = False
    last_login_ip: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserResponse
    requires_2fa: bool = False
    temp_token: str | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=100)

    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserUpdate(BaseModel):
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None


class UserResetPassword(BaseModel):
    new_password: str = Field(min_length=8, max_length=100)

    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ProfileUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=100)

    @field_validator('email')
    @classmethod
    def email_format(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_email_format(v)
        return v
