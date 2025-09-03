"""Objects API endpoints."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from ..models.objects import (
    Object, ObjectCreate, ObjectUpdate, 
    ObjectResponse, ObjectListResponse, ObjectsQueryParams
)
from ..pagination import PaginationParams, create_link_header
from ..auth.dependencies import ValidatedGPTId, CurrentGPTId
from ..db.objects import (
    create_object, get_object, list_objects, 
    update_object, delete_object
)
from ..errors.problem_details import NotFoundError


logger = logging.getLogger(__name__)

# Create router for collection-based object endpoints
collection_objects_router = APIRouter(
    prefix="/gpts/{gpt_id}/collections/{collection_name}/objects",
    tags=["Objects"],
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not Found"},
        429: {"description": "Too Many Requests"}
    }
)

# Create router for direct object endpoints
objects_router = APIRouter(
    prefix="/objects",
    tags=["Objects"],
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not Found"},
        429: {"description": "Too Many Requests"}
    }
)


@collection_objects_router.post(
    "",
    response_model=ObjectResponse,
    status_code=201,
    summary="Create an object",
    description="Create a new object in a collection with optional JSON Schema validation.",
    responses={
        201: {"description": "Object created successfully"},
        400: {"description": "Bad Request - Invalid data or schema validation failed"},
        404: {"description": "Collection not found"}
    }
)
async def create_collection_object(
    collection_name: str,
    object_data: ObjectCreate,
    validated_gpt_id: ValidatedGPTId,
    request: Request
) -> ObjectResponse:
    """Create a new object in a collection.
    
    The object will be validated against the collection's JSON Schema if one is defined.
    Objects are stored as JSONB in PostgreSQL for efficient queries and indexing.
    
    Args:
        collection_name: Name of the collection to create object in
        object_data: Object creation data containing the body
        validated_gpt_id: Validated GPT ID from path and auth
        request: FastAPI request object
        
    Returns:
        Created object with generated UUID and timestamps
    """
    logger.info(f"Creating object in collection '{collection_name}' for GPT {validated_gpt_id}")
    logger.info(f"Request body data: {object_data.model_dump()}")
    
    obj = await create_object(validated_gpt_id, collection_name, object_data)
    
    logger.info(f"Successfully created object {obj.id} in collection '{collection_name}'")
    return ObjectResponse.model_validate(obj.model_dump())


@collection_objects_router.get(
    "",
    response_model=ObjectListResponse,
    summary="List objects",
    description="List objects in a collection with cursor-based pagination and stable ordering.",
    responses={
        200: {"description": "Objects retrieved successfully"},
        400: {"description": "Bad Request - Invalid pagination parameters"}
    }
)
async def list_collection_objects(
    collection_name: str,
    validated_gpt_id: ValidatedGPTId,
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=200, description="Number of objects per page")] = 50,
    cursor: Annotated[str | None, Query(description="Cursor for pagination")] = None,
    order: Annotated[str, Query(pattern="^(asc|desc)$", description="Sort order")] = "desc"
) -> ObjectListResponse:
    """List objects in a collection with seek-based pagination.
    
    Objects are returned sorted by creation time (descending by default) with stable
    ordering using UUID as a tiebreaker. This ensures consistent pagination even
    when objects have the same creation timestamp.
    
    The pagination uses seek/cursor methodology rather than offset for better
    performance and stability at scale.
    
    Args:
        collection_name: Name of the collection to list objects from
        validated_gpt_id: Validated GPT ID from path and auth
        request: FastAPI request object  
        response: FastAPI response object for adding headers
        limit: Maximum number of objects to return (1-200)
        cursor: Pagination cursor for continuing from previous page
        order: Sort order - 'asc' or 'desc'
        
    Returns:
        Paginated list of objects with pagination metadata and Link header
    """
    logger.info(f"Listing objects in collection '{collection_name}' for GPT {validated_gpt_id}")
    
    # Create pagination parameters
    pagination = PaginationParams(
        limit=limit,
        cursor=cursor,
        order=order
    )
    
    # Get objects from database
    objects, next_cursor, has_more = await list_objects(validated_gpt_id, collection_name, pagination)
    
    # Create response
    response_data = ObjectListResponse(
        objects=objects,
        next_cursor=next_cursor,
        has_more=has_more
    )
    
    # Add Link header for pagination (RFC 8288)
    if next_cursor:
        base_url = str(request.url).split('?')[0]  # Remove existing query params
        current_params = {
            "limit": str(limit),
            "order": order
        }
        
        link_header = create_link_header(
            base_url=base_url,
            params=current_params,
            next_cursor=next_cursor
        )
        
        if link_header:
            response.headers["Link"] = link_header
    
    logger.info(f"Retrieved {len(objects)} objects from collection '{collection_name}' for GPT {validated_gpt_id}")
    return response_data


@objects_router.get(
    "/{object_id}",
    response_model=ObjectResponse,
    summary="Get an object",
    description="Retrieve a specific object by ID with GPT ownership validation.",
    responses={
        200: {"description": "Object retrieved successfully"},
        404: {"description": "Object not found or access denied"}
    }
)
async def get_object_by_id(
    object_id: UUID,
    current_gpt_id: CurrentGPTId,
    request: Request
) -> ObjectResponse:
    """Get a specific object by ID.
    
    The object must belong to the authenticated GPT. This provides a direct way
    to access objects without needing to know the collection name.
    
    Args:
        object_id: UUID of the object to retrieve
        current_gpt_id: GPT ID from authentication
        request: FastAPI request object
        
    Returns:
        The requested object
        
    Raises:
        NotFoundError: If object doesn't exist or doesn't belong to GPT
    """
    logger.info(f"Getting object {object_id} for GPT {current_gpt_id}")
    
    obj = await get_object(object_id, current_gpt_id)
    
    logger.info(f"Successfully retrieved object {object_id}")
    return ObjectResponse.model_validate(obj.model_dump())


@objects_router.patch(
    "/{object_id}",
    response_model=ObjectResponse,
    summary="Update an object",
    description="Partially update an object with JSON Schema validation and automatic updated_at timestamp.",
    responses={
        200: {"description": "Object updated successfully"},
        400: {"description": "Bad Request - Invalid data or schema validation failed"},
        404: {"description": "Object not found or access denied"}
    }
)
async def update_object_by_id(
    object_id: UUID,
    update_data: ObjectUpdate,
    current_gpt_id: CurrentGPTId,
    request: Request
) -> ObjectResponse:
    """Update an object (supports partial updates).
    
    This endpoint supports partial updates - you can update just specific fields
    in the object's body while preserving other fields. The updated object will
    be validated against the collection's JSON Schema if one is defined.
    
    The updated_at timestamp is automatically set to the current time.
    
    Args:
        object_id: UUID of the object to update
        update_data: Update data containing partial or complete body
        current_gpt_id: GPT ID from authentication
        request: FastAPI request object
        
    Returns:
        Updated object with new updated_at timestamp
        
    Raises:
        NotFoundError: If object doesn't exist or doesn't belong to GPT
        BadRequestError: If schema validation fails
    """
    logger.info(f"Updating object {object_id} for GPT {current_gpt_id}")
    
    obj = await update_object(object_id, current_gpt_id, update_data)
    
    logger.info(f"Successfully updated object {object_id}")
    return ObjectResponse.model_validate(obj.model_dump())


@objects_router.delete(
    "/{object_id}",
    status_code=204,
    summary="Delete an object",
    description="Delete an object with GPT ownership validation.",
    responses={
        204: {"description": "Object deleted successfully"},
        404: {"description": "Object not found or access denied"}
    }
)
async def delete_object_by_id(
    object_id: UUID,
    current_gpt_id: CurrentGPTId,
    request: Request
) -> Response:
    """Delete an object.
    
    The object must belong to the authenticated GPT. Once deleted, the object
    cannot be recovered.
    
    Args:
        object_id: UUID of the object to delete
        current_gpt_id: GPT ID from authentication
        request: FastAPI request object
        
    Returns:
        Empty response with 204 status
        
    Raises:
        NotFoundError: If object doesn't exist or doesn't belong to GPT
    """
    logger.info(f"Deleting object {object_id} for GPT {current_gpt_id}")
    
    deleted = await delete_object(object_id, current_gpt_id)
    
    if not deleted:
        raise NotFoundError(f"Object '{object_id}' not found")
    
    logger.info(f"Successfully deleted object {object_id} for GPT {current_gpt_id}")
    return Response(status_code=204)


# Add health check endpoint for objects
@objects_router.get(
    "/health",
    tags=["Health"],
    summary="Objects health check",
    description="Health check endpoint for objects API."
)
async def objects_health() -> dict[str, str]:
    """Health check for objects endpoints."""
    return {"status": "healthy", "service": "objects"}


# Export both routers for inclusion in main app
__all__ = ["collection_objects_router", "objects_router"]