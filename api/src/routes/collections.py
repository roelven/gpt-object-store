"""Collections API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from ..models.collections import (
    Collection, CollectionCreate, CollectionUpdate, 
    CollectionResponse, CollectionListResponse
)
from ..pagination import PaginationParams, create_link_header
from ..auth.dependencies import ValidatedGPTId, CurrentGPTId, AuthenticatedGPTId, DirectValidatedGPTId
from ..db.collections import (
    create_collection, get_collection, list_collections, 
    update_collection, delete_collection
)
from ..errors.problem_details import NotFoundError


logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(
    prefix="/gpts/{gpt_id}/collections",
    tags=["Collections"],
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not Found"},
        429: {"description": "Too Many Requests"}
    }
)


# Test endpoint for debugging authentication
@router.get(
    "/test-auth",
    summary="Test authentication (debug only)",
    description="Test endpoint to debug authentication",
)
async def test_auth(
    authenticated_gpt_id: AuthenticatedGPTId
) -> dict:
    """Test endpoint to verify authentication is working."""
    return {
        "message": "Authentication successful",
        "gpt_id": authenticated_gpt_id
    }


@router.post(
    "",
    response_model=CollectionResponse,
    status_code=201,
    summary="Create or update a collection",
    description="Create a new collection or update an existing one with optional JSON Schema validation.",
    responses={
        201: {"description": "Collection created or updated successfully"},
        400: {"description": "Bad Request - Invalid data"},
        409: {"description": "Conflict - Collection constraint violation"}
    }
)
async def create_or_update_collection(
    collection_data: CollectionCreate,
    validated_gpt_id: DirectValidatedGPTId,
    request: Request
) -> CollectionResponse:
    """Create or update a collection for a GPT.
    
    This endpoint supports upsert behavior - if a collection with the same name
    already exists, it will be updated with the new schema. If it doesn't exist,
    a new collection will be created.
    
    Args:
        collection_data: Collection creation/update data
        validated_gpt_id: Validated GPT ID from path and auth
        request: FastAPI request object
        
    Returns:
        Created or updated collection
    """
    logger.info(f"Creating/updating collection '{collection_data.name}' for GPT {validated_gpt_id}")
    
    collection = await create_collection(validated_gpt_id, collection_data)
    
    logger.info(f"Successfully created/updated collection {collection.id}")
    return CollectionResponse.model_validate(collection.model_dump(by_alias=True))


@router.get(
    "",
    response_model=CollectionListResponse,
    summary="List collections",
    description="List collections for a GPT with cursor-based pagination.",
    responses={
        200: {"description": "Collections retrieved successfully"}
    }
)
async def list_gpt_collections(
    validated_gpt_id: ValidatedGPTId,
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=200, description="Number of collections per page")] = 50,
    cursor: Annotated[str | None, Query(description="Cursor for pagination")] = None,
    order: Annotated[str, Query(pattern="^(asc|desc)$", description="Sort order")] = "desc"
) -> CollectionListResponse:
    """List collections for a GPT with pagination.
    
    Returns collections sorted by creation time (descending by default) with stable
    ordering using UUID as a tiebreaker. Supports cursor-based pagination for
    efficient traversal of large collections.
    
    Args:
        validated_gpt_id: Validated GPT ID from path and auth
        request: FastAPI request object  
        response: FastAPI response object for adding headers
        limit: Maximum number of collections to return (1-200)
        cursor: Pagination cursor for continuing from previous page
        order: Sort order - 'asc' or 'desc'
        
    Returns:
        Paginated list of collections with pagination metadata
    """
    logger.info(f"Listing collections for GPT {validated_gpt_id}")
    
    # Create pagination parameters
    pagination = PaginationParams(
        limit=limit,
        cursor=cursor,
        order=order
    )
    
    # Get collections from database
    collections, next_cursor, has_more = await list_collections(validated_gpt_id, pagination)
    
    # Create response
    response_data = CollectionListResponse(
        collections=collections,
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
    
    logger.info(f"Retrieved {len(collections)} collections for GPT {validated_gpt_id}")
    return response_data


@router.get(
    "/{collection_name}",
    response_model=CollectionResponse,
    summary="Get a collection",
    description="Retrieve a specific collection by name.",
    responses={
        200: {"description": "Collection retrieved successfully"},
        404: {"description": "Collection not found"}
    }
)
async def get_collection_by_name(
    collection_name: str,
    validated_gpt_id: ValidatedGPTId,
    request: Request
) -> CollectionResponse:
    """Get a specific collection by name.
    
    Args:
        collection_name: Name of the collection to retrieve
        validated_gpt_id: Validated GPT ID from path and auth
        request: FastAPI request object
        
    Returns:
        The requested collection
        
    Raises:
        NotFoundError: If collection doesn't exist
    """
    logger.info(f"Getting collection '{collection_name}' for GPT {validated_gpt_id}")
    
    collection = await get_collection(validated_gpt_id, collection_name)
    
    logger.info(f"Successfully retrieved collection {collection.id}")
    return CollectionResponse.model_validate(collection.model_dump(by_alias=True))


@router.patch(
    "/{collection_name}",
    response_model=CollectionResponse,
    summary="Update a collection",
    description="Update a collection's schema.",
    responses={
        200: {"description": "Collection updated successfully"},
        404: {"description": "Collection not found"}
    }
)
async def update_collection_schema(
    collection_name: str,
    update_data: CollectionUpdate,
    validated_gpt_id: ValidatedGPTId,
    request: Request
) -> CollectionResponse:
    """Update a collection's schema.
    
    Args:
        collection_name: Name of the collection to update
        update_data: Update data containing new schema
        validated_gpt_id: Validated GPT ID from path and auth
        request: FastAPI request object
        
    Returns:
        Updated collection
        
    Raises:
        NotFoundError: If collection doesn't exist
    """
    logger.info(f"Updating collection '{collection_name}' for GPT {validated_gpt_id}")
    
    collection = await update_collection(validated_gpt_id, collection_name, update_data)
    
    logger.info(f"Successfully updated collection {collection.id}")
    return CollectionResponse.model_validate(collection.model_dump(by_alias=True))


@router.delete(
    "/{collection_name}",
    status_code=204,
    summary="Delete a collection",
    description="Delete a collection and all its objects.",
    responses={
        204: {"description": "Collection deleted successfully"},
        404: {"description": "Collection not found"}
    }
)
async def delete_collection_by_name(
    collection_name: str,
    validated_gpt_id: ValidatedGPTId,
    request: Request
) -> Response:
    """Delete a collection and all its objects.
    
    Args:
        collection_name: Name of the collection to delete
        validated_gpt_id: Validated GPT ID from path and auth
        request: FastAPI request object
        
    Returns:
        Empty response with 204 status
        
    Raises:
        NotFoundError: If collection doesn't exist
    """
    logger.info(f"Deleting collection '{collection_name}' for GPT {validated_gpt_id}")
    
    deleted = await delete_collection(validated_gpt_id, collection_name)
    
    if not deleted:
        raise NotFoundError(f"Collection '{collection_name}' not found")
    
    logger.info(f"Successfully deleted collection '{collection_name}' for GPT {validated_gpt_id}")
    return Response(status_code=204)


# Add health check endpoint for collections
@router.get(
    "/health",
    tags=["Health"],
    summary="Collections health check",
    description="Health check endpoint for collections API."
)
async def collections_health() -> dict[str, str]:
    """Health check for collections endpoints."""
    return {"status": "healthy", "service": "collections"}