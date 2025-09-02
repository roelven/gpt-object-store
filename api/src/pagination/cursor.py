"""Cursor-based pagination utilities for GPT Object Store API."""

import json
import base64
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from uuid import UUID

from pydantic import BaseModel, Field
from ..errors.problem_details import BadRequestError


class CursorData(BaseModel):
    """Data structure for cursor pagination."""
    
    created_at: datetime = Field(description="Timestamp for pagination")
    id: UUID = Field(description="UUID for stable ordering")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Additional filters")


class PaginationParams(BaseModel):
    """Query parameters for pagination."""
    
    limit: int = Field(default=50, ge=1, le=200, description="Number of items per page")
    cursor: Optional[str] = Field(default=None, description="Cursor for pagination")
    order: str = Field(default="desc", pattern="^(asc|desc)$", description="Sort order")


class PaginatedResponse(BaseModel):
    """Response model for paginated data."""
    
    items: List[Any] = Field(description="List of items")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for next page")
    has_more: bool = Field(description="Whether more items are available")
    total_count: Optional[int] = Field(default=None, description="Total count if available")


def encode_cursor(created_at: datetime, item_id: UUID, filters: Optional[Dict[str, Any]] = None) -> str:
    """Encode pagination cursor.
    
    Args:
        created_at: The timestamp for pagination
        item_id: The UUID for stable ordering
        filters: Optional additional filters
        
    Returns:
        Base64 encoded cursor string
        
    Raises:
        ValueError: If encoding fails
    """
    try:
        cursor_data = CursorData(
            created_at=created_at,
            id=item_id,
            filters=filters
        )
        
        # Convert to JSON string
        cursor_json = cursor_data.model_dump_json()
        
        # Encode to base64
        cursor_bytes = cursor_json.encode('utf-8')
        encoded = base64.b64encode(cursor_bytes).decode('ascii')
        
        return encoded
        
    except Exception as e:
        raise ValueError(f"Failed to encode cursor: {e}")


def decode_cursor(cursor: str) -> CursorData:
    """Decode pagination cursor.
    
    Args:
        cursor: Base64 encoded cursor string
        
    Returns:
        Decoded cursor data
        
    Raises:
        BadRequestError: If cursor is invalid or malformed
    """
    if not cursor:
        raise BadRequestError("Empty cursor provided")
    
    try:
        # Decode from base64
        cursor_bytes = base64.b64decode(cursor.encode('ascii'))
        cursor_json = cursor_bytes.decode('utf-8')
        
        # Parse JSON and validate
        cursor_dict = json.loads(cursor_json)
        cursor_data = CursorData.model_validate(cursor_dict)
        
        return cursor_data
        
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        raise BadRequestError(f"Invalid cursor format: {e}")
    except Exception as e:
        raise BadRequestError(f"Failed to decode cursor: {e}")


def build_where_clause(
    gpt_id: str,
    collection_name: Optional[str] = None,
    cursor_data: Optional[CursorData] = None,
    order: str = "desc"
) -> tuple[str, List[Any]]:
    """Build WHERE clause for paginated queries.
    
    Args:
        gpt_id: GPT ID for filtering
        collection_name: Optional collection name for filtering
        cursor_data: Optional cursor data for pagination
        order: Sort order ('asc' or 'desc')
        
    Returns:
        Tuple of (where_clause, parameters)
    """
    conditions = ["gpt_id = $1"]
    params = [gpt_id]
    param_count = 1
    
    # Add collection filter if provided
    if collection_name:
        param_count += 1
        conditions.append(f"name = ${param_count}")
        params.append(collection_name)
    
    # Add cursor condition for pagination
    if cursor_data:
        param_count += 1
        created_at_param = f"${param_count}"
        param_count += 1
        id_param = f"${param_count}"
        
        if order.lower() == "desc":
            # For descending order: created_at < cursor OR (created_at = cursor AND id < cursor_id)
            conditions.append(f"(created_at < {created_at_param}::timestamptz OR (created_at = {created_at_param}::timestamptz AND id < {id_param}::uuid))")
        else:
            # For ascending order: created_at > cursor OR (created_at = cursor AND id > cursor_id)
            conditions.append(f"(created_at > {created_at_param}::timestamptz OR (created_at = {created_at_param}::timestamptz AND id > {id_param}::uuid))")
        
        params.extend([cursor_data.created_at, cursor_data.id])
    
    where_clause = " AND ".join(conditions)
    return where_clause, params


def build_order_clause(order: str = "desc") -> str:
    """Build ORDER BY clause for pagination.
    
    Args:
        order: Sort order ('asc' or 'desc')
        
    Returns:
        ORDER BY clause string
    """
    if order.lower() == "desc":
        return "ORDER BY created_at DESC, id DESC"
    else:
        return "ORDER BY created_at ASC, id ASC"


def create_link_header(
    base_url: str,
    params: Dict[str, Any],
    next_cursor: Optional[str] = None,
    prev_cursor: Optional[str] = None
) -> Optional[str]:
    """Create Link header for pagination as per RFC 8288.
    
    Args:
        base_url: Base URL for the resource
        params: Current query parameters
        next_cursor: Cursor for next page
        prev_cursor: Cursor for previous page
        
    Returns:
        Link header value or None if no links
    """
    links = []
    
    if next_cursor:
        next_params = {**params, "cursor": next_cursor}
        next_url = f"{base_url}?" + "&".join([f"{k}={v}" for k, v in next_params.items()])
        links.append(f'<{next_url}>; rel="next"')
    
    if prev_cursor:
        prev_params = {**params, "cursor": prev_cursor}
        prev_url = f"{base_url}?" + "&".join([f"{k}={v}" for k, v in prev_params.items()])
        links.append(f'<{prev_url}>; rel="prev"')
    
    return ", ".join(links) if links else None


def paginate_query_results(
    items: List[Dict[str, Any]],
    limit: int,
    order: str = "desc"
) -> tuple[List[Dict[str, Any]], Optional[str], bool]:
    """Process query results for pagination.
    
    Args:
        items: List of items from database query
        limit: Requested page size
        order: Sort order
        
    Returns:
        Tuple of (page_items, next_cursor, has_more)
    """
    # Check if we have more items than requested
    has_more = len(items) > limit
    
    # Take only the requested number of items
    page_items = items[:limit]
    
    # Generate next cursor if there are more items
    next_cursor = None
    if has_more and page_items:
        last_item = page_items[-1]
        next_cursor = encode_cursor(
            created_at=last_item["created_at"],
            item_id=last_item["id"]
        )
    
    return page_items, next_cursor, has_more