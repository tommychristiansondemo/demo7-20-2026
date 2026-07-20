"""Property-based tests for expired token rejection.

Feature: bedrock-agentcore-demo, Property 2: Expired token rejection

For any HTTP request with an expired session token, system redirects to
sign-in page rather than processing it as an authenticated request.

Validates: Requirements 2.6
"""

import os
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.middleware.auth import get_current_user, CurrentUser

os.environ["AWS_REGION"] = "us-east-1"


def make_test_app():
    """Create a FastAPI test app with a protected endpoint using the auth middleware."""
    app = FastAPI()

    @app.get("/api/protected")
    async def protected_endpoint(user: CurrentUser = Depends(get_current_user)):
        return {"user_id": user.user_id, "email": user.email}

    return app


# ASCII-safe alphabet for HTTP header values
_TOKEN_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/=-_."


# Strategy for generating expired/invalid token strings
def expired_token_strategy():
    """Generate various token strings that represent expired or invalid tokens.

    All generated tokens use ASCII-safe characters suitable for HTTP headers.
    These tokens will always be rejected by Cognito's get_user API because
    they are not real valid access tokens.
    """
    return st.one_of(
        # Random alphanumeric strings (like corrupted tokens)
        st.text(
            alphabet=_TOKEN_ALPHABET,
            min_size=10,
            max_size=200,
        ),
        # JWT-like structures with three dot-separated parts (but invalid)
        st.builds(
            lambda header, payload, sig: f"{header}.{payload}.{sig}",
            st.text(alphabet=_TOKEN_ALPHABET, min_size=10, max_size=50),
            st.text(alphabet=_TOKEN_ALPHABET, min_size=10, max_size=80),
            st.text(alphabet=_TOKEN_ALPHABET, min_size=10, max_size=50),
        ),
        # Short tokens (clearly invalid)
        st.text(
            alphabet=_TOKEN_ALPHABET,
            min_size=1,
            max_size=9,
        ),
        # Tokens with dashes and underscores (common in real tokens)
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
            min_size=20,
            max_size=150,
        ),
        # UUID-like strings (wrong format for Cognito tokens)
        st.builds(
            lambda a, b, c, d, e: f"{a}-{b}-{c}-{d}-{e}",
            st.text(alphabet="0123456789abcdef", min_size=8, max_size=8),
            st.text(alphabet="0123456789abcdef", min_size=4, max_size=4),
            st.text(alphabet="0123456789abcdef", min_size=4, max_size=4),
            st.text(alphabet="0123456789abcdef", min_size=4, max_size=4),
            st.text(alphabet="0123456789abcdef", min_size=12, max_size=12),
        ),
    )


class TestExpiredTokenRejectionProperty:
    """Feature: bedrock-agentcore-demo, Property 2: Expired token rejection"""

    @given(token=expired_token_strategy())
    @settings(max_examples=100, deadline=None)
    def test_expired_token_redirects_to_signin(self, token):
        """Feature: bedrock-agentcore-demo, Property 2: Expired token rejection

        For any HTTP request with an expired session token, system redirects
        to sign-in page rather than processing it as an authenticated request.

        Validates: Requirements 2.6
        """
        # Ensure we have a non-empty token
        assume(len(token.strip()) > 0)

        # Mock Cognito to raise NotAuthorizedException (expired token behavior)
        mock_cognito = MagicMock()
        mock_cognito.get_user.side_effect = ClientError(
            {
                "Error": {
                    "Code": "NotAuthorizedException",
                    "Message": "Access Token has expired",
                }
            },
            "GetUser",
        )

        with patch("backend.middleware.auth._get_cognito_client", return_value=mock_cognito):
            app = make_test_app()
            client = TestClient(app)

            response = client.get(
                "/api/protected",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Must always get 401 for expired tokens
            assert response.status_code == 401, (
                f"Expected 401 for expired token, got {response.status_code}"
            )

            data = response.json()
            detail = data["detail"]

            # Must include redirect to sign-in page
            assert "redirect" in detail, (
                f"Expected redirect field in response, got: {detail}"
            )
            assert detail["redirect"] == "/signin", (
                f"Expected redirect to /signin, got: {detail['redirect']}"
            )

            # Must indicate token is expired or unauthorized
            assert detail["error"] in ("token_expired", "unauthorized"), (
                f"Expected error type token_expired or unauthorized, got: {detail['error']}"
            )

    @given(token=expired_token_strategy())
    @settings(max_examples=100, deadline=None)
    def test_invalid_token_user_not_found_redirects(self, token):
        """Feature: bedrock-agentcore-demo, Property 2: Expired token rejection

        For any HTTP request with a token for a non-existent user, system
        redirects to sign-in page.

        Validates: Requirements 2.6
        """
        assume(len(token.strip()) > 0)

        # Mock Cognito to raise UserNotFoundException
        mock_cognito = MagicMock()
        mock_cognito.get_user.side_effect = ClientError(
            {
                "Error": {
                    "Code": "UserNotFoundException",
                    "Message": "User does not exist.",
                }
            },
            "GetUser",
        )

        with patch("backend.middleware.auth._get_cognito_client", return_value=mock_cognito):
            app = make_test_app()
            client = TestClient(app)

            response = client.get(
                "/api/protected",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Must always get 401
            assert response.status_code == 401, (
                f"Expected 401 for invalid token, got {response.status_code}"
            )

            data = response.json()
            detail = data["detail"]

            # Must include redirect to sign-in page
            assert "redirect" in detail
            assert detail["redirect"] == "/signin"
            assert detail["error"] in ("token_expired", "unauthorized")

    @given(token=expired_token_strategy())
    @settings(max_examples=100, deadline=None)
    def test_cognito_service_error_redirects(self, token):
        """Feature: bedrock-agentcore-demo, Property 2: Expired token rejection

        For any HTTP request where Cognito is unavailable during token
        validation, system redirects to sign-in page (fails closed).

        Validates: Requirements 2.6
        """
        assume(len(token.strip()) > 0)

        # Mock Cognito to raise a generic service error
        mock_cognito = MagicMock()
        mock_cognito.get_user.side_effect = ClientError(
            {
                "Error": {
                    "Code": "InternalErrorException",
                    "Message": "Internal server error",
                }
            },
            "GetUser",
        )

        with patch("backend.middleware.auth._get_cognito_client", return_value=mock_cognito):
            app = make_test_app()
            client = TestClient(app)

            response = client.get(
                "/api/protected",
                headers={"Authorization": f"Bearer {token}"},
            )

            # System fails closed — rejects the request
            assert response.status_code == 401, (
                f"Expected 401 for service error, got {response.status_code}"
            )

            data = response.json()
            detail = data["detail"]

            # Must include redirect to sign-in page
            assert "redirect" in detail
            assert detail["redirect"] == "/signin"
