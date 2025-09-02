"""Main FastAPI application for GPT Object Store."""

import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db.connection import db_manager, get_db_pool
from .errors import register_exception_handlers, create_problem_response
from .errors.problem_details import ServiceUnavailableError
from .routes import collections_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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
    
    app = FastAPI(
        title="GPT Object Store API",
        description="A backend service for Custom GPTs to persist and retrieve JSON documents",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan
    )
    
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