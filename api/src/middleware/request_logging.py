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
            
            # Read and log request body - but properly preserve it for FastAPI
            try:
                # Get the body from the request
                body_bytes = await request.body()
                if body_bytes:
                    try:
                        # Try to parse as JSON for better formatting
                        body_json = json.loads(body_bytes.decode('utf-8'))
                        logger.info(f"Request body (JSON): {body_json}")
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # If not JSON, log as raw string
                        logger.info(f"Request body (raw): {body_bytes.decode('utf-8', errors='ignore')}")
                else:
                    logger.info("Request body: (empty)")
                
                # Properly recreate the request with the preserved body
                # We need to replace the body stream in the ASGI scope
                async def receive():
                    return {"type": "http.request", "body": body_bytes, "more_body": False}
                
                # Update the scope with the new receive callable
                scope = request.scope.copy()
                scope["receive"] = receive
                
                # Create new request with proper body preservation
                from starlette.requests import Request as StarletteRequest
                new_request = StarletteRequest(scope, receive)
                
                response = await call_next(new_request)
                
            except Exception as e:
                logger.error(f"Error logging request: {e}")
                response = await call_next(request)
                
        else:
            response = await call_next(request)
            
        return response