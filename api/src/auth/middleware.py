"""Authentication middleware for Bearer token processing."""

import logging
from typing import Optional

from fastapi import Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from .api_key import validate_api_key
from ..errors.problem_details import UnauthorizedError


logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware to handle Bearer token authentication.
    
    This middleware:
    1. Extracts Bearer tokens from Authorization header
    2. Validates API keys against the database
    3. Injects gpt_id into request state for downstream use
    4. Handles OAuth tokens (future implementation)
    """
    
    def __init__(self, app, skip_paths: Optional[list[str]] = None):
        """Initialize authentication middleware.
        
        Args:
            app: The FastAPI application
            skip_paths: List of paths to skip authentication for
        """
        super().__init__(app)
        self.skip_paths = skip_paths or [
            "/health", "/ready", "/live", "/", "/docs", "/redoc", "/openapi.json"
        ]
    
    async def dispatch(self, request: Request, call_next):
        """Process the request through authentication middleware."""
        print(f"DEBUG: AuthMiddleware called for {request.url.path}")  # Force output
        logger.info(f"AuthMiddleware: Processing request for {request.url.path}")
        
        # Skip authentication for certain paths
        if request.url.path in self.skip_paths:
            print(f"DEBUG: Skipping auth for {request.url.path}")  # Force output  
            logger.debug(f"AuthMiddleware: Skipping authentication for {request.url.path}")
            return await call_next(request)
        
        logger.info(f"AuthMiddleware: Authenticating request for {request.url.path}")
        
        try:
            # Extract and validate Bearer token
            gpt_id = await self._authenticate_request(request)
            
            # Inject gpt_id into request state
            request.state.gpt_id = gpt_id
            request.state.authenticated = True
            
            logger.info(f"AuthMiddleware: Successfully authenticated request for gpt_id: {gpt_id}")
            
        except UnauthorizedError as e:
            logger.warning(f"AuthMiddleware: Authentication failed for {request.url.path}: {e.detail}")
            return e.to_response(request)
        except Exception as e:
            logger.error(f"AuthMiddleware: Unexpected error in authentication middleware: {e}")
            error = UnauthorizedError("Authentication failed due to internal error")
            return error.to_response(request)
        
        return await call_next(request)
    
    async def _authenticate_request(self, request: Request) -> str:
        """Authenticate a request and return the gpt_id.
        
        Args:
            request: The incoming FastAPI request
            
        Returns:
            The gpt_id associated with the authenticated token
            
        Raises:
            UnauthorizedError: If authentication fails
        """
        # Extract Authorization header
        auth_header = request.headers.get("Authorization")
        logger.info(f"AuthMiddleware: Authorization header present: {bool(auth_header)}")
        
        if not auth_header:
            raise UnauthorizedError("Missing Authorization header")
        
        # Parse Bearer token
        if not auth_header.startswith("Bearer "):
            logger.warning(f"AuthMiddleware: Invalid auth header format: {auth_header[:20]}...")
            raise UnauthorizedError("Invalid Authorization header format. Expected 'Bearer <token>'")
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        if not token:
            raise UnauthorizedError("Empty bearer token")
        
        logger.info(f"AuthMiddleware: Extracted token: {token[:8]}...")
        
        # Determine token type and validate
        # For now, we assume all tokens are API keys
        # Future enhancement: detect JWT tokens for OAuth
        gpt_id = await self._validate_api_key_token(token)
        
        if not gpt_id:
            logger.warning(f"AuthMiddleware: Token validation failed for token: {token[:8]}...")
            raise UnauthorizedError("Invalid or expired bearer token")
        
        logger.info(f"AuthMiddleware: Token validated successfully for gpt_id: {gpt_id}")
        return gpt_id
    
    async def _validate_api_key_token(self, token: str) -> Optional[str]:
        """Validate an API key token.
        
        Args:
            token: The bearer token to validate
            
        Returns:
            The gpt_id if valid, None if invalid
        """
        try:
            return await validate_api_key(token)
        except Exception as e:
            logger.error(f"Error validating API key: {e}")
            return None
    
    async def _validate_oauth_token(self, token: str) -> Optional[str]:
        """Validate an OAuth access token (future implementation).
        
        Args:
            token: The OAuth access token to validate
            
        Returns:
            The gpt_id if valid, None if invalid
        """
        # TODO: Implement OAuth token validation
        # This would involve:
        # 1. Verifying JWT signature
        # 2. Checking expiration
        # 3. Mapping client_id/scope to gpt_id
        # 4. Updating any usage tracking
        
        logger.debug("OAuth token validation not yet implemented")
        return None


def extract_bearer_token(authorization: str) -> str:
    """Extract bearer token from Authorization header.
    
    Args:
        authorization: The Authorization header value
        
    Returns:
        The extracted token
        
    Raises:
        UnauthorizedError: If the header format is invalid
    """
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Invalid Authorization header format. Expected 'Bearer <token>'")
    
    token = authorization[7:]  # Remove "Bearer " prefix
    if not token:
        raise UnauthorizedError("Empty bearer token")
    
    return token


# HTTP Bearer security scheme for OpenAPI documentation
bearer_scheme = HTTPBearer(
    scheme_name="bearerApiKey",
    description="API key authentication using Bearer token"
)