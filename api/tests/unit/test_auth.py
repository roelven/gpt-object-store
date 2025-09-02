"""Comprehensive unit tests for authentication functionality."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Request, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from src.auth.api_key import (
    generate_api_key, hash_api_key, verify_api_key, create_api_key,
    validate_api_key, revoke_api_key, list_api_keys_for_gpt
)
from src.auth.middleware import AuthenticationMiddleware, extract_bearer_token
from src.auth.dependencies import (
    get_bearer_token, get_current_gpt_id, get_current_gpt_id_from_state,
    require_gpt_access, authenticate_and_get_gpt_id, create_gpt_path_validator
)
from src.errors.problem_details import UnauthorizedError, ForbiddenError


def setup_db_pool_mock():
    """Helper function to set up database pool mocking consistently."""
    mock_conn = AsyncMock()
    
    # Create a proper async context manager mock
    mock_acquire = MagicMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=None)
    
    # Set up the pool mock
    mock_pool_instance = MagicMock()
    mock_pool_instance.acquire.return_value = mock_acquire
    
    return mock_pool_instance, mock_conn


class TestAPIKeyManagement:
    """Test cases for API key management functions."""
    
    def test_generate_api_key(self):
        """Test API key generation produces unique values."""
        key1 = generate_api_key()
        key2 = generate_api_key()
        
        assert isinstance(key1, str)
        assert isinstance(key2, str)
        assert len(key1) > 0
        assert len(key2) > 0
        assert key1 != key2  # Should be unique
    
    def test_hash_api_key(self):
        """Test API key hashing produces deterministic hashes."""
        api_key = "test-api-key-123"
        
        hash1 = hash_api_key(api_key)
        hash2 = hash_api_key(api_key)
        
        assert isinstance(hash1, bytes)
        assert isinstance(hash2, bytes)
        assert len(hash1) > 0
        assert len(hash2) > 0
        # Bcrypt produces different hashes each time due to salt
        assert hash1 != hash2
    
    def test_verify_api_key_valid(self):
        """Test API key verification with valid key."""
        api_key = "test-api-key-123"
        hashed = hash_api_key(api_key)
        
        assert verify_api_key(api_key, hashed) is True
    
    def test_verify_api_key_invalid(self):
        """Test API key verification with invalid key."""
        api_key = "test-api-key-123"
        wrong_key = "wrong-api-key-456"
        hashed = hash_api_key(api_key)
        
        assert verify_api_key(wrong_key, hashed) is False
    
    def test_verify_api_key_corrupted_hash(self):
        """Test API key verification with corrupted hash."""
        api_key = "test-api-key-123"
        corrupted_hash = b"corrupted-hash-data"
        
        assert verify_api_key(api_key, corrupted_hash) is False
    
    @pytest.mark.asyncio
    async def test_create_api_key(self):
        """Test creating API key in database."""
        gpt_id = "test-gpt-123"
        
        with patch('api.src.auth.api_key.get_db_pool', new_callable=AsyncMock) as mock_get_pool:
            mock_pool_instance, mock_conn = setup_db_pool_mock()
            # get_db_pool is async, so we need to make it return an awaitable
            mock_get_pool.return_value = mock_pool_instance
            
            api_key = await create_api_key(gpt_id)
            
            assert isinstance(api_key, str)
            assert len(api_key) > 0
            mock_conn.execute.assert_called_once()
            
            # Verify the call was made with correct parameters
            call_args = mock_conn.execute.call_args
            assert call_args[0][0] == "INSERT INTO api_keys (token_hash, gpt_id) VALUES ($1, $2)"
            assert call_args[0][2] == gpt_id  # gpt_id parameter
            assert isinstance(call_args[0][1], bytes)  # token_hash parameter
    
    @pytest.mark.asyncio
    async def test_create_api_key_with_specific_key(self):
        """Test creating API key with specific key value."""
        gpt_id = "test-gpt-123"
        specific_key = "my-specific-key-789"
        
        with patch('api.src.auth.api_key.get_db_pool', new_callable=AsyncMock) as mock_get_pool:
            mock_pool_instance, mock_conn = setup_db_pool_mock()
            mock_get_pool.return_value = mock_pool_instance
            
            returned_key = await create_api_key(gpt_id, specific_key)
            
            assert returned_key == specific_key
            mock_conn.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_api_key_valid(self):
        """Test validating a valid API key."""
        api_key = "test-key-123"
        gpt_id = "gpt-456"
        hashed = hash_api_key(api_key)
        
        with patch('api.src.auth.api_key.get_db_pool', new_callable=AsyncMock) as mock_get_pool:
            mock_pool_instance, mock_conn = setup_db_pool_mock()
            mock_get_pool.return_value = mock_pool_instance
            
            # Mock database response
            mock_conn.fetch.return_value = [
                {'token_hash': hashed, 'gpt_id': gpt_id}
            ]
            
            result = await validate_api_key(api_key)
            
            assert result == gpt_id
            mock_conn.execute.assert_called_once()  # For updating last_used
    
    @pytest.mark.asyncio
    async def test_validate_api_key_invalid(self):
        """Test validating an invalid API key."""
        api_key = "invalid-key-123"
        
        with patch('api.src.auth.api_key.get_db_pool', new_callable=AsyncMock) as mock_get_pool:
            mock_pool_instance, mock_conn = setup_db_pool_mock()
            mock_get_pool.return_value = mock_pool_instance
            
            # Mock empty database response
            mock_conn.fetch.return_value = []
            
            result = await validate_api_key(api_key)
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_validate_api_key_no_match(self):
        """Test validating API key when no hash matches."""
        api_key = "test-key-123"
        different_key = "different-key-456"
        gpt_id = "gpt-789"
        hashed = hash_api_key(different_key)  # Hash of different key
        
        with patch('api.src.auth.api_key.get_db_pool', new_callable=AsyncMock) as mock_get_pool:
            mock_pool_instance, mock_conn = setup_db_pool_mock()
            mock_get_pool.return_value = mock_pool_instance
            
            # Mock database response with non-matching hash
            mock_conn.fetch.return_value = [
                {'token_hash': hashed, 'gpt_id': gpt_id}
            ]
            
            result = await validate_api_key(api_key)
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_revoke_api_key_success(self):
        """Test successfully revoking an API key."""
        api_key = "test-key-123"
        hashed = hash_api_key(api_key)
        
        with patch('api.src.auth.api_key.get_db_pool', new_callable=AsyncMock) as mock_get_pool:
            mock_pool_instance, mock_conn = setup_db_pool_mock()
            mock_get_pool.return_value = mock_pool_instance
            
            # Mock database response
            mock_conn.fetch.return_value = [
                {'token_hash': hashed}
            ]
            
            result = await revoke_api_key(api_key)
            
            assert result is True
            # Should call DELETE
            delete_call = [call for call in mock_conn.execute.call_args_list 
                          if 'DELETE' in str(call)]
            assert len(delete_call) == 1
    
    @pytest.mark.asyncio
    async def test_revoke_api_key_not_found(self):
        """Test revoking a non-existent API key."""
        api_key = "non-existent-key"
        
        with patch('api.src.auth.api_key.get_db_pool', new_callable=AsyncMock) as mock_get_pool:
            mock_pool_instance, mock_conn = setup_db_pool_mock()
            mock_get_pool.return_value = mock_pool_instance
            
            # Mock empty database response
            mock_conn.fetch.return_value = []
            
            result = await revoke_api_key(api_key)
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_list_api_keys_for_gpt(self):
        """Test listing API keys for a GPT."""
        gpt_id = "test-gpt-123"
        created_time = datetime.utcnow()
        last_used_time = datetime.utcnow()
        
        with patch('api.src.auth.api_key.get_db_pool', new_callable=AsyncMock) as mock_get_pool:
            mock_pool_instance, mock_conn = setup_db_pool_mock()
            mock_get_pool.return_value = mock_pool_instance
            
            # Mock database response
            mock_conn.fetch.return_value = [
                {'created_at': created_time, 'last_used': last_used_time},
                {'created_at': created_time, 'last_used': None}
            ]
            
            result = await list_api_keys_for_gpt(gpt_id)
            
            assert len(result) == 2
            assert result[0]['created_at'] == created_time
            assert result[0]['last_used'] == last_used_time
            assert result[1]['created_at'] == created_time
            assert result[1]['last_used'] is None


class TestAuthenticationMiddleware:
    """Test cases for authentication middleware."""
    
    def test_extract_bearer_token_valid(self):
        """Test extracting valid bearer token."""
        auth_header = "Bearer abc123token"
        token = extract_bearer_token(auth_header)
        assert token == "abc123token"
    
    def test_extract_bearer_token_invalid_format(self):
        """Test extracting bearer token with invalid format."""
        auth_header = "Basic abc123token"
        
        with pytest.raises(UnauthorizedError) as exc_info:
            extract_bearer_token(auth_header)
        
        assert "Invalid Authorization header format" in str(exc_info.value)
    
    def test_extract_bearer_token_empty(self):
        """Test extracting empty bearer token."""
        auth_header = "Bearer "
        
        with pytest.raises(UnauthorizedError) as exc_info:
            extract_bearer_token(auth_header)
        
        assert "Empty bearer token" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_middleware_skip_paths(self):
        """Test middleware skips authentication for configured paths."""
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)
        
        # Mock request for health endpoint
        request = MagicMock()
        request.url.path = "/health"
        
        # Mock call_next
        call_next = AsyncMock()
        call_next.return_value = "response"
        
        result = await middleware.dispatch(request, call_next)
        
        assert result == "response"
        call_next.assert_called_once_with(request)
        # For skipped paths, middleware should not attempt to set auth state
        # We don't need to check the state since middleware returns early
    
    @pytest.mark.asyncio
    async def test_middleware_missing_auth_header(self):
        """Test middleware handles missing Authorization header."""
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)
        
        # Mock request without Authorization header
        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = None
        
        call_next = AsyncMock()
        
        response = await middleware.dispatch(request, call_next)
        
        # Should return 401 error response
        assert hasattr(response, 'status_code')
        call_next.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_middleware_invalid_token_format(self):
        """Test middleware handles invalid token format."""
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)
        
        # Mock request with invalid Authorization header
        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = "Basic abc123"
        
        call_next = AsyncMock()
        
        response = await middleware.dispatch(request, call_next)
        
        # Should return 401 error response
        assert hasattr(response, 'status_code')
        call_next.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_middleware_valid_authentication(self):
        """Test middleware handles valid authentication."""
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)
        
        # Mock request with valid Authorization header
        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = "Bearer valid-token-123"
        request.state = MagicMock()
        
        call_next = AsyncMock()
        call_next.return_value = "success_response"
        
        with patch('api.src.auth.middleware.validate_api_key') as mock_validate:
            mock_validate.return_value = "gpt-123"
            
            response = await middleware.dispatch(request, call_next)
            
            assert response == "success_response"
            call_next.assert_called_once_with(request)
            
            # Should set auth state
            assert request.state.gpt_id == "gpt-123"
            assert request.state.authenticated is True


class TestAuthenticationDependencies:
    """Test cases for authentication dependencies."""
    
    @pytest.mark.asyncio
    async def test_get_bearer_token_valid(self):
        """Test getting bearer token from credentials."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test-token-123"
        )
        
        token = await get_bearer_token(credentials)
        assert token == "test-token-123"
    
    @pytest.mark.asyncio
    async def test_get_bearer_token_empty(self):
        """Test getting empty bearer token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=""
        )
        
        with pytest.raises(UnauthorizedError) as exc_info:
            await get_bearer_token(credentials)
        
        assert "Missing or empty bearer token" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_bearer_token_none(self):
        """Test getting bearer token when credentials is None."""
        with pytest.raises(UnauthorizedError) as exc_info:
            await get_bearer_token(None)
        
        assert "Missing or empty bearer token" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_current_gpt_id_valid(self):
        """Test getting current GPT ID with valid token."""
        token = "valid-token-123"
        
        with patch('api.src.auth.dependencies.validate_api_key') as mock_validate:
            mock_validate.return_value = "gpt-456"
            
            gpt_id = await get_current_gpt_id(token)
            
            assert gpt_id == "gpt-456"
            mock_validate.assert_called_once_with(token)
    
    @pytest.mark.asyncio
    async def test_get_current_gpt_id_invalid(self):
        """Test getting current GPT ID with invalid token."""
        token = "invalid-token-123"
        
        with patch('api.src.auth.dependencies.validate_api_key') as mock_validate:
            mock_validate.return_value = None
            
            with pytest.raises(UnauthorizedError) as exc_info:
                await get_current_gpt_id(token)
            
            assert "Invalid or expired bearer token" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_current_gpt_id_from_state_valid(self):
        """Test getting GPT ID from request state."""
        request = MagicMock()
        request.state.gpt_id = "gpt-789"
        request.state.authenticated = True
        
        gpt_id = await get_current_gpt_id_from_state(request)
        assert gpt_id == "gpt-789"
    
    @pytest.mark.asyncio
    async def test_get_current_gpt_id_from_state_missing(self):
        """Test getting GPT ID from request state when missing."""
        request = MagicMock()
        del request.state.gpt_id  # Simulate missing gpt_id
        
        with pytest.raises(UnauthorizedError) as exc_info:
            await get_current_gpt_id_from_state(request)
        
        assert "No authenticated GPT ID found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_current_gpt_id_from_state_not_authenticated(self):
        """Test getting GPT ID from request state when not authenticated."""
        request = MagicMock()
        request.state.gpt_id = "gpt-789"
        request.state.authenticated = False
        
        with pytest.raises(UnauthorizedError) as exc_info:
            await get_current_gpt_id_from_state(request)
        
        assert "Request is not authenticated" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_require_gpt_access_allowed(self):
        """Test GPT access requirement when access is allowed."""
        required_gpt_id = "gpt-123"
        current_gpt_id = "gpt-123"
        
        access_checker = require_gpt_access(required_gpt_id)
        result = await access_checker(current_gpt_id)
        
        assert result == required_gpt_id
    
    @pytest.mark.asyncio
    async def test_require_gpt_access_denied(self):
        """Test GPT access requirement when access is denied."""
        required_gpt_id = "gpt-123"
        current_gpt_id = "gpt-456"  # Different GPT
        
        access_checker = require_gpt_access(required_gpt_id)
        
        with pytest.raises(ForbiddenError) as exc_info:
            await access_checker(current_gpt_id)
        
        assert "Access denied" in str(exc_info.value)
        assert required_gpt_id in str(exc_info.value)
        assert current_gpt_id in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_gpt_path_validator_valid(self):
        """Test GPT path validator with matching IDs."""
        gpt_id = "gpt-123"
        current_gpt_id = "gpt-123"
        
        validator = create_gpt_path_validator()
        result = await validator(gpt_id, current_gpt_id)
        
        assert result == gpt_id
    
    @pytest.mark.asyncio
    async def test_create_gpt_path_validator_mismatch(self):
        """Test GPT path validator with mismatched IDs."""
        gpt_id = "gpt-123"
        current_gpt_id = "gpt-456"
        
        validator = create_gpt_path_validator()
        
        with pytest.raises(ForbiddenError) as exc_info:
            await validator(gpt_id, current_gpt_id)
        
        assert "does not match authenticated GPT ID" in str(exc_info.value)
        assert gpt_id in str(exc_info.value)
        assert current_gpt_id in str(exc_info.value)


class TestIntegrationScenarios:
    """Integration test scenarios for authentication flow."""
    
    @pytest.mark.asyncio
    async def test_full_authentication_flow(self):
        """Test complete authentication flow from API key creation to validation."""
        gpt_id = "integration-test-gpt"
        
        with patch('api.src.auth.api_key.get_db_pool', new_callable=AsyncMock) as mock_get_pool:
            mock_pool_instance, mock_conn = setup_db_pool_mock()
            mock_get_pool.return_value = mock_pool_instance
            
            # Step 1: Create API key
            api_key = await create_api_key(gpt_id)
            assert isinstance(api_key, str)
            
            # Extract the hash that was stored
            create_call = mock_conn.execute.call_args
            stored_hash = create_call[0][1]
            
            # Step 2: Mock validation to return the same data
            mock_conn.fetch.return_value = [
                {'token_hash': stored_hash, 'gpt_id': gpt_id}
            ]
            
            # Step 3: Validate the API key
            validated_gpt_id = await validate_api_key(api_key)
            assert validated_gpt_id == gpt_id
    
    @pytest.mark.asyncio
    async def test_authentication_error_handling(self):
        """Test error handling in authentication flow."""
        # Test various error scenarios
        
        # Invalid bearer token format
        with pytest.raises(UnauthorizedError):
            extract_bearer_token("Invalid format")
        
        # Empty token
        with pytest.raises(UnauthorizedError):
            extract_bearer_token("Bearer ")
        
        # Invalid API key
        with patch('api.src.auth.dependencies.validate_api_key') as mock_validate:
            mock_validate.return_value = None
            
            with pytest.raises(UnauthorizedError):
                await get_current_gpt_id("invalid-key")
        
        # Missing authentication state
        request = MagicMock()
        del request.state.gpt_id
        
        with pytest.raises(UnauthorizedError):
            await get_current_gpt_id_from_state(request)