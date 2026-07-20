"""Authentication API endpoints for registration, verification, sign-in, and sign-out."""

import os
import re
import time
from collections import defaultdict

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException

from backend.models.auth import (
    AuthErrorResponse,
    RegisterRequest,
    RegisterResponse,
    SignInRequest,
    SignInResponse,
    VerifyRequest,
    VerifyResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Cognito configuration from environment variables
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Account lockout configuration
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 minutes

# In-memory tracking of failed login attempts: email -> list of failure timestamps
_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _check_account_lockout(email: str) -> int | None:
    """Check if an account is locked out due to too many failed attempts.

    Returns the number of seconds remaining in the lockout period,
    or None if the account is not locked.
    """
    now = time.time()
    attempts = _failed_attempts.get(email, [])

    # Remove attempts older than the lockout window
    recent_attempts = [t for t in attempts if now - t < LOCKOUT_DURATION_SECONDS]
    _failed_attempts[email] = recent_attempts

    if len(recent_attempts) >= MAX_FAILED_ATTEMPTS:
        # Account is locked — calculate remaining time from the most recent attempt
        oldest_relevant = recent_attempts[0]
        unlock_time = oldest_relevant + LOCKOUT_DURATION_SECONDS
        remaining = int(unlock_time - now)
        if remaining > 0:
            return remaining

    return None


def _record_failed_attempt(email: str) -> None:
    """Record a failed sign-in attempt for the given email."""
    _failed_attempts[email].append(time.time())


def _clear_failed_attempts(email: str) -> None:
    """Clear failed attempts on successful sign-in."""
    _failed_attempts.pop(email, None)


def _get_cognito_client():
    """Create a Cognito Identity Provider client."""
    return boto3.client("cognito-idp", region_name=AWS_REGION)


def _validate_password(password: str) -> str | None:
    """Validate password meets Cognito default policy.

    Returns an error message if invalid, None if valid.
    Requirements: minimum 8 chars, uppercase, lowercase, number, special character.
    """
    if len(password) < 8:
        return "Password must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r"[0-9]", password):
        return "Password must contain at least one number"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must contain at least one special character"
    return None


def _validate_display_name(display_name: str) -> str | None:
    """Validate display name is 2-50 characters.

    Returns an error message if invalid, None if valid.
    """
    if len(display_name) < 2:
        return "Display name must be at least 2 characters"
    if len(display_name) > 50:
        return "Display name must be at most 50 characters"
    return None


def _validate_email_format(email: str) -> str | None:
    """Validate email format.

    Returns an error message if invalid, None if valid.
    Pydantic's EmailStr handles most validation, but we double-check here.
    """
    email_pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    if not email_pattern.match(email):
        return "Email format is invalid"
    return None


@router.post(
    "/register",
    response_model=RegisterResponse,
    responses={400: {"model": AuthErrorResponse}},
)
async def register(request: RegisterRequest) -> RegisterResponse:
    """Register a new user account.

    Validates email format, password policy, and display name length.
    Creates the user in Cognito and triggers a verification email.
    """
    # Validate email format
    email_error = _validate_email_format(request.email)
    if email_error:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_email", "message": email_error},
        )

    # Validate password policy
    password_error = _validate_password(request.password)
    if password_error:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_password", "message": password_error},
        )

    # Validate display name
    display_name_error = _validate_display_name(request.display_name)
    if display_name_error:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_display_name", "message": display_name_error},
        )

    # Create user in Cognito
    client = _get_cognito_client()
    try:
        client.sign_up(
            ClientId=COGNITO_CLIENT_ID,
            Username=request.email,
            Password=request.password,
            UserAttributes=[
                {"Name": "email", "Value": request.email},
                {"Name": "custom:display_name", "Value": request.display_name},
            ],
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "UsernameExistsException":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "duplicate_email",
                    "message": "An account with this email already exists",
                },
            )
        elif error_code == "InvalidPasswordException":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_password",
                    "message": e.response["Error"]["Message"],
                },
            )
        elif error_code == "InvalidParameterException":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_parameter",
                    "message": e.response["Error"]["Message"],
                },
            )
        else:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Authentication service is temporarily unavailable",
                },
            )

    return RegisterResponse(email=request.email)


@router.post(
    "/verify",
    response_model=VerifyResponse,
    responses={400: {"model": AuthErrorResponse}},
)
async def verify(request: VerifyRequest) -> VerifyResponse:
    """Verify a user's email with the confirmation code.

    Confirms the verification code sent during registration.
    On success, the user can proceed to sign in.
    """
    client = _get_cognito_client()
    try:
        client.confirm_sign_up(
            ClientId=COGNITO_CLIENT_ID,
            Username=request.email,
            ConfirmationCode=request.code,
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("CodeMismatchException", "ExpiredCodeException"):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_code",
                    "message": "The verification code is invalid or has expired",
                },
            )
        elif error_code == "UserNotFoundException":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_email",
                    "message": "No account found with this email address",
                },
            )
        elif error_code == "NotAuthorizedException":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "already_verified",
                    "message": "This account has already been verified",
                },
            )
        else:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Authentication service is temporarily unavailable",
                },
            )

    return VerifyResponse()


@router.post(
    "/signin",
    response_model=SignInResponse,
    responses={
        400: {"model": AuthErrorResponse},
        429: {"model": AuthErrorResponse},
        503: {"model": AuthErrorResponse},
    },
)
async def signin(request: SignInRequest) -> SignInResponse:
    """Sign in a user with email and password.

    Authenticates via Cognito using USER_PASSWORD_AUTH flow.
    Returns a JWT access token with 60-minute lifetime.
    Implements account lockout after 5 consecutive failed attempts.
    """
    email = request.email

    # Check for account lockout
    lockout_remaining = _check_account_lockout(email)
    if lockout_remaining is not None:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "account_locked",
                "message": "Account is temporarily locked due to too many failed sign-in attempts",
                "retry_after_seconds": lockout_remaining,
            },
        )

    # Attempt authentication via Cognito
    client = _get_cognito_client()
    try:
        response = client.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": email,
                "PASSWORD": request.password,
            },
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in (
            "NotAuthorizedException",
            "UserNotFoundException",
            "UserNotConfirmedException",
        ):
            # Record failed attempt and return generic error
            _record_failed_attempt(email)
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_credentials",
                    "message": "The email or password you entered is incorrect",
                },
            )
        else:
            # Cognito unavailable or unexpected error
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Authentication service is temporarily unavailable",
                },
            )
    except (BotoCoreError, Exception):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "service_unavailable",
                "message": "Authentication service is temporarily unavailable",
            },
        )

    # Successful authentication — clear failed attempts
    _clear_failed_attempts(email)

    auth_result = response.get("AuthenticationResult", {})
    access_token = auth_result.get("AccessToken", "")
    expires_in = auth_result.get("ExpiresIn", 3600)

    return SignInResponse(
        access_token=access_token,
        expires_in=expires_in,
        token_type="Bearer",
    )


@router.post(
    "/signout",
    responses={
        401: {"model": AuthErrorResponse},
        503: {"model": AuthErrorResponse},
    },
)
async def signout(access_token: str | None = None) -> dict:
    """Sign out a user by invalidating their session token.

    Calls Cognito's global_sign_out to invalidate all tokens for the user.
    The access token should be provided in the request body or extracted from
    the Authorization header (handled by middleware in production).
    """
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "No access token provided",
            },
        )

    client = _get_cognito_client()
    try:
        client.global_sign_out(AccessToken=access_token)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("NotAuthorizedException", "InvalidParameterException"):
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "unauthorized",
                    "message": "Invalid or expired access token",
                },
            )
        else:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Authentication service is temporarily unavailable",
                },
            )
    except (BotoCoreError, Exception):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "service_unavailable",
                "message": "Authentication service is temporarily unavailable",
            },
        )

    return {"message": "Successfully signed out"}
