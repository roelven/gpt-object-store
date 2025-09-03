"""Request logging middleware for debugging."""

import logging
import json
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request details for debugging."""
    
    async def dispatch(self, request: Request, call_next):
        """Log request details and call next middleware."""
        
        # Only log POST requests to object endpoints
        if request.method == "POST" and "/objects" in str(request.url.path):
            logger.info(f"POST request to: {request.url.path}")
            logger.info(f"Headers: {dict(request.headers)}")
            
            # Read and log request body
            try:
                body = await request.body()
                if body:
                    try:
                        # Try to parse as JSON for better formatting
                        body_json = json.loads(body.decode('utf-8'))
                        logger.info(f"Request body (JSON): {body_json}")
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # If not JSON, log as raw string
                        logger.info(f"Request body (raw): {body.decode('utf-8', errors='ignore')}")
                else:
                    logger.info("Request body: (empty)")
                    
                # We need to recreate the request with the body since we consumed it
                from starlette.requests import Request as StarletteRequest
                from starlette.datastructures import Headers
                
                # Create a new request with the body preserved
                scope = request.scope.copy()
                scope["body"] = body
                
                # Create new request object
                new_request = StarletteRequest(scope)
                new_request._body = body
                
                response = await call_next(new_request)
                
            except Exception as e:
                logger.error(f"Error logging request: {e}")
                response = await call_next(request)
                
        else:
            response = await call_next(request)
            
        return response