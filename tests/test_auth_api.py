"""Unit tests for the authentication API endpoints."""

import os
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from moto import mock_aws

from backend.api.auth import router

# Set up test environment variables before importing the module
os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_testpool"
os.environ["COGNITO_CLIENT_ID"] = "test-client-id"
os.environ["AWS_REGION"] = "us-east-1"


@pytest.fixture
def app():
    """Create a test FastAPI application."""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def cognito_setup():
    """Set up mocked Cognito user pool and client."""
    with mock_aws():
        client = boto3.client("cognito-idp", region_name="us-east-1")

        # Create user pool
        pool_response = client.create_user_pool(
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
                {
                    "Name": "email",
                    "AttributeDataType": "String",
                    "Required": True,
                },
                {
                    "Name": "display_name",
                    "AttributeDataType": "String",
                    "Mutable": True,
                },
            ],
            AutoVerifiedAttributes=["email"],
        )
        pool_id = pool_response["UserPool"]["Id"]

        # Create user pool client
        client_response = client.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName="test-client",
            ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
        )
        client_id = client_response["UserPoolClient"]["ClientId"]

        # Patch the environment variables and client
        with patch.dict(
            os.environ,
            {
                "COGNITO_USER_POOL_ID": pool_id,
                "COGNITO_CLIENT_ID": client_id,
            },
        ):
            # Also patch the module-level constants
            with patch("backend.api.auth.COGNITO_USER_POOL_ID", pool_id):
                with patch("backend.api.auth.COGNITO_CLIENT_ID", client_id):
                    yield {
                        "pool_id": pool_id,
                        "client_id": client_id,
                        "cognito_client": client,
                    }


class TestRegisterEndpoint:
    """Tests for POST /api/auth/register."""

    def test_successful_registration(self, client, cognito_setup):
        """Test successful user registration with valid inputs."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "ValidPass1!",
                "display_name": "Test User",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["message"] == "Verification code sent to email"

    def test_invalid_email_format(self, client, cognito_setup):
        """Test registration with invalid email format returns 422 (Pydantic validation)."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "ValidPass1!",
                "display_name": "Test User",
            },
        )
        # Pydantic EmailStr catches this before our validator
        assert response.status_code == 422

    def test_password_too_short(self, client, cognito_setup):
        """Test registration with password shorter than 8 characters."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "Abc1!",
                "display_name": "Test User",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "invalid_password"
        assert "8 characters" in data["detail"]["message"]

    def test_password_no_uppercase(self, client, cognito_setup):
        """Test registration with password missing uppercase letter."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "lowercase1!",
                "display_name": "Test User",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "invalid_password"
        assert "uppercase" in data["detail"]["message"]

    def test_password_no_lowercase(self, client, cognito_setup):
        """Test registration with password missing lowercase letter."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "UPPERCASE1!",
                "display_name": "Test User",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "invalid_password"
        assert "lowercase" in data["detail"]["message"]

    def test_password_no_number(self, client, cognito_setup):
        """Test registration with password missing number."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "NoNumber!!",
                "display_name": "Test User",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "invalid_password"
        assert "number" in data["detail"]["message"]

    def test_password_no_special_character(self, client, cognito_setup):
        """Test registration with password missing special character."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "NoSpecial1",
                "display_name": "Test User",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "invalid_password"
        assert "special character" in data["detail"]["message"]

    def test_display_name_too_short(self, client, cognito_setup):
        """Test registration with display name shorter than 2 characters."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "ValidPass1!",
                "display_name": "A",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "invalid_display_name"
        assert "2 characters" in data["detail"]["message"]

    def test_display_name_too_long(self, client, cognito_setup):
        """Test registration with display name longer than 50 characters."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "ValidPass1!",
                "display_name": "A" * 51,
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "invalid_display_name"
        assert "50 characters" in data["detail"]["message"]

    def test_duplicate_email(self, client, cognito_setup):
        """Test registration with an email that's already registered."""
        # First registration
        client.post(
            "/api/auth/register",
            json={
                "email": "duplicate@example.com",
                "password": "ValidPass1!",
                "display_name": "First User",
            },
        )
        # Second registration with same email
        response = client.post(
            "/api/auth/register",
            json={
                "email": "duplicate@example.com",
                "password": "ValidPass1!",
                "display_name": "Second User",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "duplicate_email"
        assert "already exists" in data["detail"]["message"]

    def test_display_name_boundary_min(self, client, cognito_setup):
        """Test registration with minimum valid display name (2 chars)."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "ValidPass1!",
                "display_name": "AB",
            },
        )
        assert response.status_code == 200

    def test_display_name_boundary_max(self, client, cognito_setup):
        """Test registration with maximum valid display name (50 chars)."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test2@example.com",
                "password": "ValidPass1!",
                "display_name": "A" * 50,
            },
        )
        assert response.status_code == 200


class TestVerifyEndpoint:
    """Tests for POST /api/auth/verify."""

    def test_successful_verification(self, client, cognito_setup):
        """Test successful email verification with valid code."""
        cognito_client = cognito_setup["cognito_client"]
        pool_id = cognito_setup["pool_id"]

        # First register a user
        client.post(
            "/api/auth/register",
            json={
                "email": "verify@example.com",
                "password": "ValidPass1!",
                "display_name": "Verify User",
            },
        )

        # In moto, we can confirm the user directly to simulate code verification
        # Moto's confirm_sign_up accepts any code
        response = client.post(
            "/api/auth/verify",
            json={
                "email": "verify@example.com",
                "code": "123456",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Account verified successfully"

    def test_invalid_verification_code(self, client, cognito_setup):
        """Test verification with invalid code for non-existent user."""
        response = client.post(
            "/api/auth/verify",
            json={
                "email": "nonexistent@example.com",
                "code": "000000",
            },
        )
        assert response.status_code == 400

    def test_invalid_email_format_verify(self, client, cognito_setup):
        """Test verification with invalid email format returns 422."""
        response = client.post(
            "/api/auth/verify",
            json={
                "email": "invalid-email",
                "code": "123456",
            },
        )
        assert response.status_code == 422


class TestSignInEndpoint:
    """Tests for POST /api/auth/signin."""

    def test_successful_signin(self, client, cognito_setup):
        """Test successful sign-in with valid credentials."""
        cognito_client = cognito_setup["cognito_client"]
        pool_id = cognito_setup["pool_id"]

        # Register and confirm a user
        client.post(
            "/api/auth/register",
            json={
                "email": "signin@example.com",
                "password": "ValidPass1!",
                "display_name": "Sign In User",
            },
        )
        # Confirm the user in Cognito (moto accepts any code)
        cognito_client.admin_confirm_sign_up(
            UserPoolId=pool_id,
            Username="signin@example.com",
        )

        response = client.post(
            "/api/auth/signin",
            json={
                "email": "signin@example.com",
                "password": "ValidPass1!",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 3600

    def test_signin_invalid_password(self, client, cognito_setup):
        """Test sign-in with wrong password returns generic error."""
        cognito_client = cognito_setup["cognito_client"]
        pool_id = cognito_setup["pool_id"]

        # Register and confirm a user
        client.post(
            "/api/auth/register",
            json={
                "email": "wrongpw@example.com",
                "password": "ValidPass1!",
                "display_name": "Wrong PW User",
            },
        )
        cognito_client.admin_confirm_sign_up(
            UserPoolId=pool_id,
            Username="wrongpw@example.com",
        )

        response = client.post(
            "/api/auth/signin",
            json={
                "email": "wrongpw@example.com",
                "password": "WrongPass1!",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "invalid_credentials"
        # Verify generic error message — doesn't reveal which field is wrong
        assert "email or password" in data["detail"]["message"]

    def test_signin_nonexistent_user(self, client, cognito_setup):
        """Test sign-in with non-existent email returns generic error."""
        response = client.post(
            "/api/auth/signin",
            json={
                "email": "nouser@example.com",
                "password": "ValidPass1!",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "invalid_credentials"
        # Same generic message — doesn't reveal user doesn't exist
        assert "email or password" in data["detail"]["message"]

    def test_signin_account_lockout(self, client, cognito_setup):
        """Test account lockout after 5 failed attempts."""
        from backend.api.auth import _failed_attempts

        # Clear any existing state
        _failed_attempts.clear()

        cognito_client = cognito_setup["cognito_client"]
        pool_id = cognito_setup["pool_id"]

        # Register and confirm a user
        client.post(
            "/api/auth/register",
            json={
                "email": "lockout@example.com",
                "password": "ValidPass1!",
                "display_name": "Lockout User",
            },
        )
        cognito_client.admin_confirm_sign_up(
            UserPoolId=pool_id,
            Username="lockout@example.com",
        )

        # Make 5 failed attempts
        for _ in range(5):
            client.post(
                "/api/auth/signin",
                json={
                    "email": "lockout@example.com",
                    "password": "WrongPass1!",
                },
            )

        # 6th attempt should be locked out
        response = client.post(
            "/api/auth/signin",
            json={
                "email": "lockout@example.com",
                "password": "ValidPass1!",
            },
        )
        assert response.status_code == 429
        data = response.json()
        assert data["detail"]["error"] == "account_locked"
        assert "retry_after_seconds" in data["detail"]
        assert data["detail"]["retry_after_seconds"] > 0

    def test_signin_lockout_clears_on_success(self, client, cognito_setup):
        """Test that successful sign-in clears failed attempt counter."""
        from backend.api.auth import _failed_attempts

        # Clear any existing state
        _failed_attempts.clear()

        cognito_client = cognito_setup["cognito_client"]
        pool_id = cognito_setup["pool_id"]

        # Register and confirm a user
        client.post(
            "/api/auth/register",
            json={
                "email": "clearlock@example.com",
                "password": "ValidPass1!",
                "display_name": "Clear Lock User",
            },
        )
        cognito_client.admin_confirm_sign_up(
            UserPoolId=pool_id,
            Username="clearlock@example.com",
        )

        # Make 3 failed attempts (below lockout threshold)
        for _ in range(3):
            client.post(
                "/api/auth/signin",
                json={
                    "email": "clearlock@example.com",
                    "password": "WrongPass1!",
                },
            )

        # Successful sign-in should clear attempts
        response = client.post(
            "/api/auth/signin",
            json={
                "email": "clearlock@example.com",
                "password": "ValidPass1!",
            },
        )
        assert response.status_code == 200

        # Verify attempts were cleared
        assert "clearlock@example.com" not in _failed_attempts

    def test_signin_cognito_unavailable(self, client, cognito_setup):
        """Test sign-in returns 503 when Cognito is unavailable."""
        from unittest.mock import patch as mock_patch

        from backend.api.auth import _failed_attempts

        _failed_attempts.clear()

        with mock_patch("backend.api.auth._get_cognito_client") as mock_client:
            mock_client.return_value.initiate_auth.side_effect = ClientError(
                {"Error": {"Code": "InternalErrorException", "Message": "Service error"}},
                "InitiateAuth",
            )
            response = client.post(
                "/api/auth/signin",
                json={
                    "email": "test@example.com",
                    "password": "ValidPass1!",
                },
            )
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["error"] == "service_unavailable"

    def test_signin_invalid_email_format(self, client, cognito_setup):
        """Test sign-in with invalid email format returns 422."""
        response = client.post(
            "/api/auth/signin",
            json={
                "email": "not-an-email",
                "password": "ValidPass1!",
            },
        )
        assert response.status_code == 422


class TestSignOutEndpoint:
    """Tests for POST /api/auth/signout."""

    def test_signout_no_token(self, client, cognito_setup):
        """Test sign-out without token returns 401."""
        response = client.post("/api/auth/signout")
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error"] == "unauthorized"

    def test_signout_with_valid_token(self, client, cognito_setup):
        """Test sign-out with a valid token (sign in first to get token)."""
        cognito_client = cognito_setup["cognito_client"]
        pool_id = cognito_setup["pool_id"]

        # Register, confirm, and sign in
        client.post(
            "/api/auth/register",
            json={
                "email": "signout@example.com",
                "password": "ValidPass1!",
                "display_name": "Sign Out User",
            },
        )
        cognito_client.admin_confirm_sign_up(
            UserPoolId=pool_id,
            Username="signout@example.com",
        )
        signin_response = client.post(
            "/api/auth/signin",
            json={
                "email": "signout@example.com",
                "password": "ValidPass1!",
            },
        )
        token = signin_response.json()["access_token"]

        # Sign out
        response = client.post(
            "/api/auth/signout",
            params={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Successfully signed out"

    def test_signout_cognito_unavailable(self, client, cognito_setup):
        """Test sign-out returns 503 when Cognito is unavailable."""
        from unittest.mock import patch as mock_patch

        with mock_patch("backend.api.auth._get_cognito_client") as mock_client:
            mock_client.return_value.global_sign_out.side_effect = ClientError(
                {"Error": {"Code": "InternalErrorException", "Message": "Service error"}},
                "GlobalSignOut",
            )
            response = client.post(
                "/api/auth/signout",
                params={"access_token": "some-token"},
            )
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["error"] == "service_unavailable"
