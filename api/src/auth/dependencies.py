"""FastAPI dependencies for authentication and authorization."""

import logging
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .api_key import validate_api_key
from .middleware import extract_bearer_token
from ..errors.problem_details import UnauthorizedError, ForbiddenError


logger = logging.getLogger(__name__)

# HTTP Bearer security scheme for OpenAPI documentation
security = HTTPBearer(
    scheme_name="bearerApiKey",
    description="API key authentication using Bearer token"
)


async def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> str:
    """Extract bearer token from Authorization header.
    
    Args:
        credentials: HTTP authorization credentials from FastAPI security
        
    Returns:
        The extracted bearer token
        
    Raises:
        UnauthorizedError: If token is missing or invalid format
    """
    if not credentials or not credentials.credentials:
        raise UnauthorizedError("Missing or empty bearer token")
    
    return credentials.credentials


async def get_current_gpt_id(
    token: Annotated[str, Depends(get_bearer_token)]
) -> str:
    """Get the current authenticated GPT ID from bearer token.
    
    Args:
        token: The bearer token from the Authorization header
        
    Returns:
        The authenticated GPT ID
        
    Raises:
        UnauthorizedError: If token is invalid or expired
    """
    # Validate API key and get gpt_id
    gpt_id = await validate_api_key(token)
    
    if not gpt_id:
        raise UnauthorizedError("Invalid or expired bearer token")
    
    logger.debug(f"Authenticated gpt_id: {gpt_id}")
    return gpt_id


async def get_current_gpt_id_from_state(request: Request) -> str:
    """Get the current authenticated GPT ID from request state.
    
    This dependency retrieves the gpt_id that was injected by the
    authentication middleware, providing a more efficient alternative
    to re-validating the token.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        The authenticated GPT ID
        
    Raises:
        UnauthorizedError: If no authenticated gpt_id found in request state
    """
    if not hasattr(request.state, 'gpt_id'):
        raise UnauthorizedError("No authenticated GPT ID found in request")
    
    if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
        raise UnauthorizedError("Request is not authenticated")
    
    return request.state.gpt_id


def require_gpt_access(required_gpt_id: str):
    """Create a dependency that requires access to a specific GPT.
    
    This factory function creates a dependency that verifies the authenticated
    user has access to the specified GPT ID.
    
    Args:
        required_gpt_id: The GPT ID that access is required for
        
    Returns:
        A dependency function that validates GPT access
    """
    async def _check_gpt_access(
        current_gpt_id: Annotated[str, Depends(get_current_gpt_id_from_state)]
    ) -> str:
        """Check if the current user has access to the required GPT.
        
        Args:
            current_gpt_id: The authenticated GPT ID
            
        Returns:
            The GPT ID if access is allowed
            
        Raises:
            ForbiddenError: If the user doesn't have access to the GPT
        """
        if current_gpt_id != required_gpt_id:
            raise ForbiddenError(
                f"Access denied. Required GPT ID: {required_gpt_id}, "
                f"authenticated as: {current_gpt_id}"
            )
        
        return current_gpt_id
    
    return _check_gpt_access


# Type aliases for commonly used dependencies
CurrentGPTId = Annotated[str, Depends(get_current_gpt_id_from_state)]
BearerToken = Annotated[str, Depends(get_bearer_token)]
AuthenticatedGPTId = Annotated[str, Depends(get_current_gpt_id)]


# Alternative dependency for when middleware is not used
async def authenticate_and_get_gpt_id(
    token: BearerToken
) -> str:
    """Authenticate bearer token and return GPT ID.
    
    This is an alternative to using the middleware + get_current_gpt_id_from_state
    approach. Use this when you want authentication to be handled at the
    endpoint level rather than middleware level.
    
    Args:
        token: The bearer token from Authorization header
        
    Returns:
        The authenticated GPT ID
        
    Raises:
        UnauthorizedError: If authentication fails
    """
    return await get_current_gpt_id(token)


def create_gpt_path_validator():
    """Create a dependency that validates gpt_id in path matches authenticated user.
    
    Returns:
        A dependency function that validates path gpt_id against authenticated gpt_id
    """
    async def validate_gpt_path(
        gpt_id: str,  # This comes from the path parameter
        current_gpt_id: CurrentGPTId
    ) -> str:
        """Validate that path gpt_id matches authenticated gpt_id.
        
        Args:
            gpt_id: The gpt_id from the URL path
            current_gpt_id: The authenticated gpt_id
            
        Returns:
            The validated gpt_id
            
        Raises:
            ForbiddenError: If path gpt_id doesn't match authenticated gpt_id
        """
        if gpt_id != current_gpt_id:
            # Add detailed logging for debugging character differences
            logger.error(f"GPT ID mismatch - Path: '{gpt_id}' (len={len(gpt_id)}, bytes={gpt_id.encode('utf-8')}) vs Authenticated: '{current_gpt_id}' (len={len(current_gpt_id)}, bytes={current_gpt_id.encode('utf-8')})")
            
            raise ForbiddenError(
                f"Path GPT ID '{gpt_id}' does not match authenticated GPT ID '{current_gpt_id}'"
            )
        
        return gpt_id
    
    return validate_gpt_path


# Create the path validator dependency (middleware-based)
ValidatedGPTId = Annotated[str, Depends(create_gpt_path_validator())]

def create_direct_gpt_path_validator():
    """Create a dependency that validates gpt_id in path with direct auth.
    
    Returns:
        A dependency function that validates path gpt_id against directly authenticated gpt_id
    """
    async def validate_gpt_path_direct(
        gpt_id: str,  # This comes from the path parameter
        current_gpt_id: AuthenticatedGPTId
    ) -> str:
        """Validate that path gpt_id matches directly authenticated gpt_id.
        
        Args:
            gpt_id: The gpt_id from the URL path
            current_gpt_id: The authenticated gpt_id from direct validation
            
        Returns:
            The validated gpt_id
            
        Raises:
            ForbiddenError: If path gpt_id doesn't match authenticated gpt_id
        """
        if gpt_id != current_gpt_id:
            raise ForbiddenError(
                f"Path GPT ID '{gpt_id}' does not match authenticated GPT ID '{current_gpt_id}'"
            )
        
        return gpt_id
    
    return validate_gpt_path_direct

# Create the direct path validator dependency
DirectValidatedGPTId = Annotated[str, Depends(create_direct_gpt_path_validator())]