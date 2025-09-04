"""Database operations for objects."""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

import asyncpg
import jsonschema

from ..models.objects import Object, ObjectCreate, ObjectUpdate, ObjectRow
from ..pagination import (
    PaginationParams, decode_cursor, build_where_clause, 
    build_order_clause, paginate_query_results
)
from ..errors.problem_details import (
    NotFoundError, ConflictError, BadRequestError, InternalServerError
)
from .connection import get_db_pool
from .collections import get_collection


logger = logging.getLogger(__name__)


async def validate_object_against_schema(
    gpt_id: str,
    collection_name: str,
    object_data: Dict[str, Any]
) -> None:
    """Validate object data against collection's JSON Schema if present.
    
    Args:
        gpt_id: GPT ID that owns the collection
        collection_name: Name of the collection
        object_data: Object data to validate
        
    Raises:
        BadRequestError: If validation fails
        NotFoundError: If collection doesn't exist
        InternalServerError: If validation check fails
    """
    try:
        # Get collection to check for schema
        collection = await get_collection(gpt_id, collection_name)
        
        # If collection has a schema, validate against it
        if collection.json_schema:
            try:
                jsonschema.validate(object_data, collection.json_schema)
                logger.debug(f"Object validated against schema for collection {collection_name}")
            except jsonschema.ValidationError as e:
                logger.warning(f"Object validation failed for collection {collection_name}: {e.message}")
                raise BadRequestError(f"Object validation failed: {e.message}")
            except jsonschema.SchemaError as e:
                logger.error(f"Invalid schema for collection {collection_name}: {e.message}")
                raise InternalServerError(f"Collection schema is invalid: {e.message}")
        else:
            logger.debug(f"No schema defined for collection {collection_name}, skipping validation")
            
    except NotFoundError:
        raise
    except BadRequestError:
        raise
    except InternalServerError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating object schema: {e}")
        raise InternalServerError(f"Schema validation error: {e}")


async def create_object(
    gpt_id: str,
    collection_name: str,
    object_data: ObjectCreate
) -> Object:
    """Create a new object in a collection.
    
    Args:
        gpt_id: GPT ID that owns the object
        collection_name: Collection to create object in
        object_data: Object creation data
        
    Returns:
        Created object
        
    Raises:
        NotFoundError: If collection doesn't exist
        BadRequestError: If object validation fails
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        # Convert direct fields to body format for database storage
        body_data = object_data.to_body_format()["body"]
        
        # Validate object against collection schema if present
        await validate_object_against_schema(gpt_id, collection_name, body_data)
        
        async with pool.acquire() as conn:
            query = """
                INSERT INTO objects (gpt_id, collection, body)
                VALUES ($1, $2, $3)
                RETURNING id, gpt_id, collection, body, created_at, updated_at
            """
            
            row = await conn.fetchrow(
                query,
                gpt_id,
                collection_name,
                json.dumps(body_data)  # Convert dict to JSONB
            )
            
            if not row:
                raise InternalServerError("Failed to create object")
            
            # Convert row to dict and handle JSONB body parsing
            row_dict = dict(row)
            if row_dict.get('body') and isinstance(row_dict['body'], str):
                row_dict['body'] = json.loads(row_dict['body'])
            
            object_row = ObjectRow.model_validate(row_dict)
            logger.info(f"Created object {object_row.id} in collection {collection_name} for GPT {gpt_id}")
            
            return object_row.to_object()
            
    except NotFoundError:
        raise
    except BadRequestError:
        raise
    except asyncpg.ForeignKeyViolationError as e:
        logger.error(f"Foreign key violation creating object: {e}")
        raise NotFoundError(f"Collection '{collection_name}' not found for GPT '{gpt_id}'")
    except asyncpg.PostgresError as e:
        logger.error(f"Database error creating object: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error creating object: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def get_object(object_id: UUID, gpt_id: str) -> Object:
    """Get a specific object by ID, ensuring ownership by GPT.
    
    Args:
        object_id: ID of the object to retrieve
        gpt_id: GPT ID that should own the object
        
    Returns:
        The requested object
        
    Raises:
        NotFoundError: If object doesn't exist or doesn't belong to GPT
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            query = """
                SELECT id, gpt_id, collection, body, created_at, updated_at
                FROM objects
                WHERE id = $1 AND gpt_id = $2
            """
            
            row = await conn.fetchrow(query, object_id, gpt_id)
            
            if not row:
                raise NotFoundError(f"Object '{object_id}' not found for GPT '{gpt_id}'")
            
            # Convert row to dict and handle JSONB body parsing
            row_dict = dict(row)
            if row_dict.get('body') and isinstance(row_dict['body'], str):
                row_dict['body'] = json.loads(row_dict['body'])
            
            object_row = ObjectRow.model_validate(row_dict)
            logger.debug(f"Retrieved object {object_row.id} for GPT {gpt_id}")
            
            return object_row.to_object()
            
    except NotFoundError:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error retrieving object: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error retrieving object: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def list_objects(
    gpt_id: str,
    collection_name: str,
    pagination: PaginationParams
) -> tuple[List[Object], Optional[str], bool]:
    """List objects in a collection with pagination.
    
    Args:
        gpt_id: GPT ID that owns the objects
        collection_name: Collection to list objects from
        pagination: Pagination parameters
        
    Returns:
        Tuple of (objects, next_cursor, has_more)
        
    Raises:
        BadRequestError: If pagination parameters are invalid
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        # Decode cursor if provided
        cursor_data = None
        if pagination.cursor:
            cursor_data = decode_cursor(pagination.cursor)
        
        # Build query components - use objects table specific where clause
        conditions = ["gpt_id = $1", "collection = $2"]
        params = [gpt_id, collection_name]
        param_count = 2
        
        # Add cursor condition for pagination
        if cursor_data:
            param_count += 1
            created_at_param = f"${param_count}"
            param_count += 1
            id_param = f"${param_count}"
            
            if pagination.order.lower() == "desc":
                conditions.append(f"(created_at < {created_at_param}::timestamptz OR (created_at = {created_at_param}::timestamptz AND id < {id_param}::uuid))")
            else:
                conditions.append(f"(created_at > {created_at_param}::timestamptz OR (created_at = {created_at_param}::timestamptz AND id > {id_param}::uuid))")
            
            params.extend([cursor_data.created_at, cursor_data.id])
        
        where_clause = " AND ".join(conditions)
        order_clause = build_order_clause(pagination.order)
        
        # Query for one more item than requested to check for more pages
        limit = pagination.limit + 1
        
        async with pool.acquire() as conn:
            query = f"""
                SELECT id, gpt_id, collection, body, created_at, updated_at
                FROM objects
                WHERE {where_clause}
                {order_clause}
                LIMIT ${len(params) + 1}
            """
            
            rows = await conn.fetch(query, *params, limit)
            
            # Convert rows to dictionaries
            items = [dict(row) for row in rows]
            
            # Process pagination results
            page_items, next_cursor, has_more = paginate_query_results(
                items=items,
                limit=pagination.limit,
                order=pagination.order
            )
            
            # Convert to Object models
            objects = []
            for item in page_items:
                # Handle JSONB body parsing
                if item.get('body') and isinstance(item['body'], str):
                    item['body'] = json.loads(item['body'])
                object_row = ObjectRow.model_validate(item)
                objects.append(object_row.to_object())
            
            logger.debug(f"Listed {len(objects)} objects from collection {collection_name} for GPT {gpt_id}")
            
            return objects, next_cursor, has_more
            
    except BadRequestError:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error listing objects: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error listing objects: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def update_object(
    object_id: UUID,
    gpt_id: str,
    update_data: ObjectUpdate
) -> Object:
    """Update an object (partial update support).
    
    Args:
        object_id: ID of the object to update
        gpt_id: GPT ID that should own the object
        update_data: Update data
        
    Returns:
        Updated object
        
    Raises:
        NotFoundError: If object doesn't exist or doesn't belong to GPT
        BadRequestError: If object validation fails
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # First, get the current object to validate ownership and get collection info
            current_object = await get_object(object_id, gpt_id)
            
            # Convert direct fields to body format for database storage
            update_body_format = update_data.to_body_format()
            
            # Determine the new body data
            if update_body_format.get("body"):
                # For partial updates, merge with existing data
                new_body = {**current_object.body, **update_body_format["body"]}
            else:
                # No body update, keep existing
                new_body = current_object.body
            
            # Validate the updated object against collection schema
            await validate_object_against_schema(gpt_id, current_object.collection, new_body)
            
            # Update the object
            query = """
                UPDATE objects
                SET body = $3, updated_at = now()
                WHERE id = $1 AND gpt_id = $2
                RETURNING id, gpt_id, collection, body, created_at, updated_at
            """
            
            row = await conn.fetchrow(
                query,
                object_id,
                gpt_id,
                json.dumps(new_body)  # Convert dict to JSONB
            )
            
            if not row:
                raise NotFoundError(f"Object '{object_id}' not found for GPT '{gpt_id}'")
            
            # Convert row to dict and handle JSONB body parsing
            row_dict = dict(row)
            if row_dict.get('body') and isinstance(row_dict['body'], str):
                row_dict['body'] = json.loads(row_dict['body'])
            
            object_row = ObjectRow.model_validate(row_dict)
            logger.info(f"Updated object {object_row.id} for GPT {gpt_id}")
            
            return object_row.to_object()
            
    except NotFoundError:
        raise
    except BadRequestError:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error updating object: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating object: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def delete_object(object_id: UUID, gpt_id: str) -> bool:
    """Delete an object.
    
    Args:
        object_id: ID of the object to delete
        gpt_id: GPT ID that should own the object
        
    Returns:
        True if object was deleted, False if not found
        
    Raises:
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            query = """
                DELETE FROM objects
                WHERE id = $1 AND gpt_id = $2
            """
            
            result = await conn.execute(query, object_id, gpt_id)
            
            # Check if any rows were affected
            deleted = result.split()[-1] == "1"  # "DELETE 1" means one row deleted
            
            if deleted:
                logger.info(f"Deleted object {object_id} for GPT {gpt_id}")
            else:
                logger.debug(f"Object {object_id} not found for GPT {gpt_id}")
            
            return deleted
            
    except asyncpg.PostgresError as e:
        logger.error(f"Database error deleting object: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting object: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def object_exists(object_id: UUID, gpt_id: str) -> bool:
    """Check if an object exists and belongs to the GPT.
    
    Args:
        object_id: ID of the object
        gpt_id: GPT ID that should own the object
        
    Returns:
        True if object exists and belongs to GPT, False otherwise
        
    Raises:
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            query = """
                SELECT 1 FROM objects
                WHERE id = $1 AND gpt_id = $2
                LIMIT 1
            """
            
            row = await conn.fetchrow(query, object_id, gpt_id)
            exists = row is not None
            
            logger.debug(f"Object {object_id} exists for GPT {gpt_id}: {exists}")
            return exists
            
    except asyncpg.PostgresError as e:
        logger.error(f"Database error checking object existence: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking object existence: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def get_object_count(gpt_id: str, collection_name: Optional[str] = None) -> int:
    """Get total count of objects for a GPT, optionally filtered by collection.
    
    Args:
        gpt_id: GPT ID that owns the objects
        collection_name: Optional collection name to filter by
        
    Returns:
        Total number of objects
        
    Raises:
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            if collection_name:
                query = "SELECT COUNT(*) FROM objects WHERE gpt_id = $1 AND collection = $2"
                count = await conn.fetchval(query, gpt_id, collection_name)
            else:
                query = "SELECT COUNT(*) FROM objects WHERE gpt_id = $1"
                count = await conn.fetchval(query, gpt_id)
            
            logger.debug(f"Total objects for GPT {gpt_id} in collection {collection_name}: {count}")
            return count or 0
            
    except asyncpg.PostgresError as e:
        logger.error(f"Database error counting objects: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error counting objects: {e}")
        raise InternalServerError(f"Unexpected error: {e}")