"""Main FastAPI application for GPT Object Store."""

import logging
import asyncio
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db.connection import db_manager, get_db_pool
from .errors import register_exception_handlers, create_problem_response
from .errors.problem_details import ServiceUnavailableError
from .rate_limit.middleware import RateLimitMiddleware
from .auth.middleware import AuthenticationMiddleware
from .middleware.request_logging import RequestLoggingMiddleware
from .routes import collections_router
from .routes.objects import collection_objects_router, objects_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_openapi_spec() -> Dict[str, Any]:
    """Load the custom OpenAPI specification from YAML file."""
    openapi_file = Path(__file__).parent.parent / "openapi" / "gpt-object-store.yaml"
    
    try:
        with open(openapi_file, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"OpenAPI spec file not found at {openapi_file}, using auto-generated spec")
        return {}
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse OpenAPI spec: {e}, using auto-generated spec")
        return {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting GPT Object Store API")
    settings = get_settings()
    
    # Configure logging level from settings
    logging.getLogger().setLevel(getattr(logging, settings.log_level))
    
    try:
        # Initialize database connection
        await db_manager.initialize()
        logger.info("Database connection pool initialized")
        
        # Verify database connectivity
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        logger.info("Database connectivity verified")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down GPT Object Store API")
    try:
        await db_manager.close()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    # Load custom OpenAPI specification
    custom_openapi = load_openapi_spec()
    
    # Create app with custom OpenAPI if available, otherwise use defaults
    if custom_openapi:
        app = FastAPI(
            title=custom_openapi.get("info", {}).get("title", "GPT Object Store API"),
            description=custom_openapi.get("info", {}).get("description", "A backend service for Custom GPTs to persist and retrieve JSON documents"),
            version=custom_openapi.get("info", {}).get("version", "1.0.0"),
            docs_url="/docs",
            redoc_url="/redoc",
            openapi_url="/openapi.json",
            lifespan=lifespan
        )
        
        # Override the openapi method to return our custom spec with dynamic server URL
        def get_custom_openapi():
            spec = custom_openapi.copy()
            # Update server URL with the actual API_URL from settings
            if 'servers' in spec and spec['servers']:
                spec['servers'][0]['url'] = settings.api_url
            return spec
        
        app.openapi = get_custom_openapi
    else:
        app = FastAPI(
            title="GPT Object Store API",
            description="A backend service for Custom GPTs to persist and retrieve JSON documents",
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
            openapi_url="/openapi.json",
            lifespan=lifespan
        )
    
    # Add request logging middleware for debugging (first, so it captures everything)
    # TODO: Temporarily disabled due to body parsing interference
    # app.add_middleware(RequestLoggingMiddleware)
    
    # Add rate limiting middleware (before CORS to limit all requests)
    # Use same skip paths as auth middleware
    rate_limit_skip_paths = [
        "/health", "/ready", "/live", "/", "/docs", "/redoc", "/openapi.json",
        "/v1/health", "/v1/ready", "/v1/live", "/v1/"
    ]
    app.add_middleware(RateLimitMiddleware, skip_paths=rate_limit_skip_paths)
    
    # Add authentication middleware (after rate limiting, before CORS)
    # Skip paths for health checks and docs (include both with and without /v1 prefix)
    auth_skip_paths = [
        "/health", "/ready", "/live", "/", "/docs", "/redoc", "/openapi.json",
        "/v1/health", "/v1/ready", "/v1/live", "/v1/"
    ]
    app.add_middleware(AuthenticationMiddleware, skip_paths=auth_skip_paths)
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
    
    # Register exception handlers
    register_exception_handlers(app)
    
    # Register API routes with version prefix
    app.include_router(collections_router, prefix="/v1")
    app.include_router(collection_objects_router, prefix="/v1")
    app.include_router(objects_router, prefix="/v1")
    
    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check() -> Dict[str, Any]:
        """Health check endpoint with database connectivity test."""
        try:
            # Test database connectivity
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            
            return {
                "status": "healthy",
                "service": "GPT Object Store API",
                "version": "1.0.0",
                "database": "connected"
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise ServiceUnavailableError(
                detail="Database connection failed",
                database_error=str(e)
            )
    
    # Ready check endpoint (Kubernetes style)
    @app.get("/ready", tags=["Health"])
    async def ready_check() -> Dict[str, Any]:
        """Readiness check endpoint."""
        try:
            # Test database connectivity
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchval("SELECT COUNT(*) FROM pg_stat_activity")
                
            return {
                "status": "ready",
                "service": "GPT Object Store API",
                "database_connections": result
            }
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            raise ServiceUnavailableError(
                detail="Service not ready",
                database_error=str(e)
            )
    
    # Live check endpoint (Kubernetes style)
    @app.get("/live", tags=["Health"])
    async def liveness_check() -> Dict[str, str]:
        """Liveness check endpoint."""
        return {
            "status": "alive",
            "service": "GPT Object Store API"
        }
    
    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root() -> Dict[str, str]:
        """Root endpoint with API information."""
        return {
            "service": "GPT Object Store API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health"
        }
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )