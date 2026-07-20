"""Property-based tests for registration input validation.

Feature: bedrock-agentcore-demo, Property 1: Registration input validation

For any input with invalid email, non-compliant password, or display name
outside 2-50 chars, system rejects with specific error.

Validates: Requirements 1.5, 1.6, 1.8
"""

import os
from unittest.mock import patch

import boto3
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from moto import mock_aws

from backend.api.auth import router

os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_testpool"
os.environ["COGNITO_CLIENT_ID"] = "test-client-id"
os.environ["AWS_REGION"] = "us-east-1"


def setup_cognito():
    """Set up mocked Cognito user pool and return config."""
    cognito_client = boto3.client("cognito-idp", region_name="us-east-1")
    pool_response = cognito_client.create_user_pool(
        PoolName="test-pool",
        Policies={
            "PasswordPolicy": {
                "MinimumLength": 8,
                "RequireUppercase": True,
                "RequireLowercase": True,
                "RequireNumbers": True,
                "RequireSymbols": True,
            }
        },
        Schema=[
            {"Name": "email", "AttributeDataType": "String", "Required": True},
            {"Name": "display_name", "AttributeDataType": "String", "Mutable": True},
        ],
        AutoVerifiedAttributes=["email"],
    )
    pool_id = pool_response["UserPool"]["Id"]
    client_response = cognito_client.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName="test-client",
        ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
    )
    client_id = client_response["UserPoolClient"]["ClientId"]
    return pool_id, client_id


def make_test_client():
    """Create a FastAPI test client."""
    test_app = FastAPI()
    test_app.include_router(router)
    return TestClient(test_app)


# Strategy for generating invalid passwords (violates at least one policy rule)
def invalid_password_strategy():
    """Generate passwords that violate at least one Cognito password policy rule.

    Policy: min 8 chars, uppercase, lowercase, number, special character.
    """
    return st.one_of(
        # Too short (< 8 chars)
        st.text(
            alphabet=st.characters(categories=("L", "N", "P")),
            min_size=1,
            max_size=7,
        ),
        # No uppercase letter (has lowercase, digit, special)
        st.builds(
            lambda s: f"abc{s}1!xy",
            st.text(alphabet="abcdefghijklmnop", min_size=1, max_size=5),
        ),
        # No lowercase letter (has uppercase, digit, special)
        st.builds(
            lambda s: f"ABC{s}1!XY",
            st.text(alphabet="ABCDEFGHIJKLMNOP", min_size=1, max_size=5),
        ),
        # No number (has upper, lower, special)
        st.builds(
            lambda s: f"Abc{s}!xy",
            st.text(alphabet="abcdefghijklmnop", min_size=1, max_size=5),
        ),
        # No special character (has upper, lower, digit)
        st.builds(
            lambda s: f"Abc{s}1xy",
            st.text(alphabet="abcdefghijklmnop0123456789", min_size=1, max_size=5),
        ),
    )


# Strategy for generating invalid display names (outside 2-50 chars)
def invalid_display_name_strategy():
    """Generate display names that are too short (<2) or too long (>50).

    Note: empty string is caught by Pydantic min_length=1, giving 422.
    Single char is caught by our validator, giving 400.
    >50 chars is caught by our validator, giving 400.
    """
    return st.one_of(
        # Single character (too short - caught by our validator with 400)
        st.text(min_size=1, max_size=1, alphabet="abcdefghijklmnop"),
        # Too long: more than 50 characters
        st.text(min_size=51, max_size=80, alphabet="abcdefghijklmnopqrstuvwxyz "),
    )


# Strategy for generating invalid email formats
def invalid_email_strategy():
    """Generate strings that are not valid email format."""
    return st.one_of(
        # No @ symbol
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789.",
            min_size=3,
            max_size=30,
        ).filter(lambda s: "@" not in s),
        # Nothing before @
        st.builds(
            lambda domain: f"@{domain}.com",
            st.text(min_size=3, max_size=10, alphabet="abcdefghijklmnop"),
        ),
        # No dot in domain part
        st.builds(
            lambda local, domain: f"{local}@{domain}",
            st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop"),
            st.text(min_size=3, max_size=10, alphabet="abcdefghijklmnop"),
        ),
        # Multiple @ signs
        st.builds(
            lambda a, b, c: f"{a}@{b}@{c}.com",
            st.text(min_size=1, max_size=5, alphabet="abcdef"),
            st.text(min_size=1, max_size=5, alphabet="abcdef"),
            st.text(min_size=1, max_size=5, alphabet="abcdef"),
        ),
        # Just whitespace
        st.just("   "),
        # Plain word without domain structure
        st.text(min_size=3, max_size=15, alphabet="abcdefghijklmnop"),
    )


class TestRegistrationInputValidationProperty:
    """Feature: bedrock-agentcore-demo, Property 1: Registration input validation"""

    @given(password=invalid_password_strategy())
    @settings(max_examples=100, deadline=None)
    def test_invalid_password_rejected(self, password):
        """Feature: bedrock-agentcore-demo, Property 1: Registration input validation

        For any password that does not meet Cognito policy (min 8 chars, uppercase,
        lowercase, number, special character), the system rejects with specific error.

        Validates: Requirements 1.5
        """
        # Ensure the password actually violates at least one rule
        violates_policy = (
            len(password) < 8
            or not any(c.isupper() for c in password)
            or not any(c.islower() for c in password)
            or not any(c.isdigit() for c in password)
            or all(c.isalnum() for c in password)
        )
        assume(violates_policy)

        with mock_aws():
            pool_id, client_id = setup_cognito()
            with patch("backend.api.auth.COGNITO_USER_POOL_ID", pool_id):
                with patch("backend.api.auth.COGNITO_CLIENT_ID", client_id):
                    test_client = make_test_client()
                    response = test_client.post(
                        "/api/auth/register",
                        json={
                            "email": "valid@example.com",
                            "password": password,
                            "display_name": "Valid Name",
                        },
                    )
                    assert response.status_code == 400, (
                        f"Expected 400 for invalid password '{password}', "
                        f"got {response.status_code}"
                    )
                    data = response.json()
                    assert data["detail"]["error"] == "invalid_password"
                    assert isinstance(data["detail"]["message"], str)
                    assert len(data["detail"]["message"]) > 0

    @given(display_name=invalid_display_name_strategy())
    @settings(max_examples=100, deadline=None)
    def test_invalid_display_name_rejected(self, display_name):
        """Feature: bedrock-agentcore-demo, Property 1: Registration input validation

        For any display name outside 2-50 characters, the system rejects with
        specific error.

        Validates: Requirements 1.6
        """
        # Only test values that our custom validator should catch (1 char or >50 chars)
        # Empty string is caught by Pydantic min_length=1 (gives 422)
        assume(len(display_name) == 1 or len(display_name) > 50)

        with mock_aws():
            pool_id, client_id = setup_cognito()
            with patch("backend.api.auth.COGNITO_USER_POOL_ID", pool_id):
                with patch("backend.api.auth.COGNITO_CLIENT_ID", client_id):
                    test_client = make_test_client()
                    response = test_client.post(
                        "/api/auth/register",
                        json={
                            "email": "valid@example.com",
                            "password": "ValidPass1!",
                            "display_name": display_name,
                        },
                    )
                    assert response.status_code == 400, (
                        f"Expected 400 for display_name of length "
                        f"{len(display_name)}, got {response.status_code}"
                    )
                    data = response.json()
                    assert data["detail"]["error"] == "invalid_display_name"
                    assert isinstance(data["detail"]["message"], str)
                    assert len(data["detail"]["message"]) > 0

    @given(email=invalid_email_strategy())
    @settings(max_examples=100, deadline=None)
    def test_invalid_email_rejected(self, email):
        """Feature: bedrock-agentcore-demo, Property 1: Registration input validation

        For any email that is not in valid email format, the system rejects
        with an error (400 from custom validator or 422 from Pydantic EmailStr).

        Validates: Requirements 1.8
        """
        with mock_aws():
            pool_id, client_id = setup_cognito()
            with patch("backend.api.auth.COGNITO_USER_POOL_ID", pool_id):
                with patch("backend.api.auth.COGNITO_CLIENT_ID", client_id):
                    test_client = make_test_client()
                    response = test_client.post(
                        "/api/auth/register",
                        json={
                            "email": email,
                            "password": "ValidPass1!",
                            "display_name": "Valid Name",
                        },
                    )
                    # Pydantic EmailStr validation returns 422,
                    # Our custom email validator returns 400 with invalid_email error.
                    # Both are valid rejection behaviors for invalid email.
                    assert response.status_code in (400, 422), (
                        f"Expected 400 or 422 for invalid email '{email}', "
                        f"got {response.status_code}"
                    )
                    if response.status_code == 400:
                        data = response.json()
                        assert data["detail"]["error"] == "invalid_email"
                        assert isinstance(data["detail"]["message"], str)
                    elif response.status_code == 422:
                        # Pydantic validation error format
                        data = response.json()
                        assert "detail" in data
