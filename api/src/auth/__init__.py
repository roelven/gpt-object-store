"""Authentication module for GPT Object Store API.

This module provides authentication and authorization functionality including:
- API key management with secure hashing
- Bearer token authentication middleware  
- FastAPI dependencies for authentication
- OAuth-ready design for future expansion
"""

from .api_key import (
    generate_api_key,
    hash_api_key,
    verify_api_key,
    create_api_key,
    validate_api_key,
    revoke_api_key,
    list_api_keys_for_gpt
)

from .middleware import (
    AuthenticationMiddleware,
    extract_bearer_token,
    bearer_scheme
)

from .dependencies import (
    get_bearer_token,
    get_current_gpt_id,
    get_current_gpt_id_from_state,
    require_gpt_access,
    authenticate_and_get_gpt_id,
    create_gpt_path_validator,
    CurrentGPTId,
    BearerToken,
    AuthenticatedGPTId,
    ValidatedGPTId,
    security
)

__all__ = [
    # API key management
    "generate_api_key",
    "hash_api_key", 
    "verify_api_key",
    "create_api_key",
    "validate_api_key",
    "revoke_api_key",
    "list_api_keys_for_gpt",
    
    # Middleware
    "AuthenticationMiddleware",
    "extract_bearer_token",
    "bearer_scheme",
    
    # Dependencies
    "get_bearer_token",
    "get_current_gpt_id",
    "get_current_gpt_id_from_state", 
    "require_gpt_access",
    "authenticate_and_get_gpt_id",
    "create_gpt_path_validator",
    "CurrentGPTId",
    "BearerToken", 
    "AuthenticatedGPTId",
    "ValidatedGPTId",
    "security"
]