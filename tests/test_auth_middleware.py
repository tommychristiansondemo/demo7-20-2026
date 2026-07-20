"""Unit tests for the JWT validation middleware."""

import os
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from moto import mock_aws

from backend.middleware.auth import CurrentUser, get_current_user

# Set up test environment variables
os.environ["AWS_REGION"] = "us-east-1"
os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_testpool"
os.environ["COGNITO_CLIENT_ID"] = "test-client-id"


@pytest.fixture
def app():
    """Create a test FastAPI application with a protected endpoint."""
    from fastapi import Depends

    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected_route(user: CurrentUser = Depends(get_current_user)):
        return {"user_id": user.user_id, "email": user.email}

    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def cognito_setup():
    """Set up mocked Cognito user pool and client for token generation."""
    with mock_aws():
        cognito_client = boto3.client("cognito-idp", region_name="us-east-1")

        # Create user pool
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
                {
                    "Name": "email",
                    "AttributeDataType": "String",
                    "Required": True,
                },
            ],
            AutoVerifiedAttributes=["email"],
        )
        pool_id = pool_response["UserPool"]["Id"]

        # Create user pool client with explicit auth flows
        client_response = cognito_client.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName="test-client",
            ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
        )
        client_id = client_response["UserPoolClient"]["ClientId"]

        # Create and confirm a test user
        cognito_client.sign_up(
            ClientId=client_id,
            Username="testuser@example.com",
            Password="ValidPass1!",
            UserAttributes=[
                {"Name": "email", "Value": "testuser@example.com"},
            ],
        )
        cognito_client.admin_confirm_sign_up(
            UserPoolId=pool_id,
            Username="testuser@example.com",
        )

        # Sign in to get a valid access token
        auth_response = cognito_client.initiate_auth(
            ClientId=client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": "testuser@example.com",
                "PASSWORD": "ValidPass1!",
            },
        )
        access_token = auth_response["AuthenticationResult"]["AccessToken"]

        yield {
            "pool_id": pool_id,
            "client_id": client_id,
            "cognito_client": cognito_client,
            "access_token": access_token,
        }


class TestGetCurrentUser:
    """Tests for the get_current_user dependency."""

    def test_valid_token_returns_user(self, client, cognito_setup):
        """Test that a valid token returns the user_id and email."""
        token = cognito_setup["access_token"]
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert data["email"] == "testuser@example.com"
        # user_id should be a non-empty string (Cognito sub)
        assert len(data["user_id"]) > 0

    def test_missing_authorization_header(self, client, cognito_setup):
        """Test that a missing Authorization header returns 401 with redirect."""
        response = client.get("/protected")
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error"] == "unauthorized"
        assert data["detail"]["redirect"] == "/signin"

    def test_invalid_token(self, client, cognito_setup):
        """Test that an invalid token returns 401 with redirect to sign-in."""
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer invalid-token-value"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["redirect"] == "/signin"

    def test_expired_token_returns_401_with_redirect(self, client, cognito_setup):
        """Test that an expired/revoked token returns 401 with redirect."""
        # Revoke the token to simulate expiration
        cognito_client = cognito_setup["cognito_client"]
        token = cognito_setup["access_token"]
        cognito_client.global_sign_out(AccessToken=token)

        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["redirect"] == "/signin"
        assert "sign in" in data["detail"]["message"].lower()

    def test_empty_bearer_token(self, client, cognito_setup):
        """Test that an empty bearer token returns 401."""
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer "},
        )
        # FastAPI's HTTPBearer returns None for empty credentials
        assert response.status_code == 401

    def test_cognito_service_error(self, client, cognito_setup):
        """Test that a Cognito service error returns 401 with redirect."""
        with patch("backend.middleware.auth._get_cognito_client") as mock_client:
            mock_client.return_value.get_user.side_effect = BotoCoreError()
            response = client.get(
                "/protected",
                headers={"Authorization": "Bearer some-token"},
            )
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["redirect"] == "/signin"

    def test_www_authenticate_header_present(self, client, cognito_setup):
        """Test that 401 responses include WWW-Authenticate header."""
        response = client.get("/protected")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers


class TestCurrentUserModel:
    """Tests for the CurrentUser Pydantic model."""

    def test_current_user_creation(self):
        """Test creating a CurrentUser with valid data."""
        user = CurrentUser(user_id="abc-123-def", email="user@example.com")
        assert user.user_id == "abc-123-def"
        assert user.email == "user@example.com"

    def test_current_user_serialization(self):
        """Test that CurrentUser serializes to dict correctly."""
        user = CurrentUser(user_id="sub-456", email="test@test.com")
        data = user.model_dump()
        assert data == {"user_id": "sub-456", "email": "test@test.com"}
