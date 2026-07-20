"""Data models for authentication requests and responses."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Request body for user registration."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1, description="Password meeting Cognito policy")
    display_name: str = Field(..., min_length=1, description="Display name (2-50 characters)")


class RegisterResponse(BaseModel):
    """Response body for successful registration."""

    message: str = Field(default="Verification code sent to email")
    email: str = Field(..., description="Email address the verification was sent to")


class VerifyRequest(BaseModel):
    """Request body for email verification."""

    email: EmailStr = Field(..., description="Email address to verify")
    code: str = Field(..., min_length=1, description="Verification code from email")


class VerifyResponse(BaseModel):
    """Response body for successful verification."""

    message: str = Field(default="Account verified successfully")


class SignInRequest(BaseModel):
    """Request body for sign-in."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1, description="User password")


class SignInResponse(BaseModel):
    """Response body for successful sign-in."""

    access_token: str = Field(..., description="JWT access token")
    expires_in: int = Field(default=3600, description="Token lifetime in seconds")
    token_type: str = Field(default="Bearer", description="Token type")


class AuthErrorResponse(BaseModel):
    """Error response for authentication failures."""

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    retry_after_seconds: int | None = Field(default=None, description="Seconds until retry is allowed (for lockout)")
