"""JWT validation middleware for FastAPI.

Provides a dependency that validates Cognito access tokens and extracts
the authenticated user's identity for downstream use.
"""

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# Cognito configuration from environment variables
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# HTTPBearer scheme extracts the token from Authorization: Bearer <token>
_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    """Represents the authenticated user extracted from a valid JWT token."""

    user_id: str
    """Cognito sub (unique user identifier)."""

    email: str
    """User's email address."""


def _get_cognito_client():
    """Create a Cognito Identity Provider client."""
    return boto3.client("cognito-idp", region_name=AWS_REGION)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """FastAPI dependency that validates the JWT access token from Cognito.

    Extracts the Bearer token from the Authorization header, validates it
    by calling Cognito's GetUser API, and returns the authenticated user's
    identity (user_id and email).

    Raises:
        HTTPException(401): If no token is provided, the token is expired,
            or the token is otherwise invalid. The response includes a
            redirect hint to the sign-in page.
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "Authentication required",
                "redirect": "/signin",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = credentials.credentials

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "Authentication required",
                "redirect": "/signin",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate token by calling Cognito's GetUser API
    client = _get_cognito_client()
    try:
        response = client.get_user(AccessToken=access_token)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("NotAuthorizedException", "UserNotFoundException"):
            # Token is expired or invalid
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "token_expired",
                    "message": "Session has expired. Please sign in again.",
                    "redirect": "/signin",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "unauthorized",
                    "message": "Authentication failed. Please sign in again.",
                    "redirect": "/signin",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
    except (BotoCoreError, Exception):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "Authentication service unavailable. Please try again.",
                "redirect": "/signin",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user attributes from Cognito response
    username = response.get("Username", "")
    user_attributes = {
        attr["Name"]: attr["Value"] for attr in response.get("UserAttributes", [])
    }

    user_id = user_attributes.get("sub", username)
    email = user_attributes.get("email", "")

    return CurrentUser(user_id=user_id, email=email)
