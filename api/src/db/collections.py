"""Database operations for collections."""

import json
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID

import asyncpg

from ..models.collections import Collection, CollectionCreate, CollectionUpdate, CollectionRow
from ..pagination import (
    PaginationParams, decode_cursor, build_where_clause, 
    build_order_clause, paginate_query_results
)
from ..errors.problem_details import (
    NotFoundError, ConflictError, BadRequestError, InternalServerError
)
from .connection import get_db_pool


logger = logging.getLogger(__name__)


async def create_collection(
    gpt_id: str, 
    collection_data: CollectionCreate
) -> Collection:
    """Create a new collection (with upsert behavior).
    
    Args:
        gpt_id: GPT ID that owns the collection
        collection_data: Collection creation data
        
    Returns:
        Created or existing collection
        
    Raises:
        ConflictError: If there's a constraint violation
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Use UPSERT (INSERT ... ON CONFLICT ... DO UPDATE)
            query = """
                INSERT INTO collections (gpt_id, name, schema)
                VALUES ($1, $2, $3)
                ON CONFLICT (gpt_id, name)
                DO UPDATE SET 
                    schema = EXCLUDED.schema,
                    created_at = collections.created_at
                RETURNING id, gpt_id, name, schema, created_at
            """
            
            # Convert schema dict to JSON string for JSONB parameter
            schema_json = None
            if collection_data.json_schema:
                schema_json = json.dumps(collection_data.json_schema)
            
            row = await conn.fetchrow(
                query,
                gpt_id,
                collection_data.name,
                schema_json
            )
            
            if not row:
                raise InternalServerError("Failed to create collection")
            
            # Convert row to dict and handle JSONB schema parsing
            row_dict = dict(row)
            if row_dict.get('schema') and isinstance(row_dict['schema'], str):
                row_dict['schema'] = json.loads(row_dict['schema'])
            
            collection_row = CollectionRow.model_validate(row_dict)
            logger.info(f"Created/updated collection {collection_row.id} for GPT {gpt_id}")
            
            return collection_row.to_collection()
            
    except asyncpg.UniqueViolationError as e:
        logger.error(f"Unique constraint violation creating collection: {e}")
        raise ConflictError(f"Collection '{collection_data.name}' already exists for GPT '{gpt_id}'")
    except asyncpg.PostgresError as e:
        logger.error(f"Database error creating collection: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error creating collection: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def get_collection(
    gpt_id: str, 
    collection_name: str
) -> Collection:
    """Get a specific collection by name.
    
    Args:
        gpt_id: GPT ID that owns the collection
        collection_name: Name of the collection
        
    Returns:
        The requested collection
        
    Raises:
        NotFoundError: If collection doesn't exist
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            query = """
                SELECT id, gpt_id, name, schema, created_at
                FROM collections
                WHERE gpt_id = $1 AND name = $2
            """
            
            row = await conn.fetchrow(query, gpt_id, collection_name)
            
            if not row:
                raise NotFoundError(f"Collection '{collection_name}' not found for GPT '{gpt_id}'")
            
            # Convert row to dict and handle JSONB schema parsing
            row_dict = dict(row)
            if row_dict.get('schema') and isinstance(row_dict['schema'], str):
                row_dict['schema'] = json.loads(row_dict['schema'])
            
            collection_row = CollectionRow.model_validate(row_dict)
            logger.debug(f"Retrieved collection {collection_row.id} for GPT {gpt_id}")
            
            return collection_row.to_collection()
            
    except NotFoundError:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error retrieving collection: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error retrieving collection: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def list_collections(
    gpt_id: str,
    pagination: PaginationParams
) -> tuple[List[Collection], Optional[str], bool]:
    """List collections for a GPT with pagination.
    
    Args:
        gpt_id: GPT ID that owns the collections
        pagination: Pagination parameters
        
    Returns:
        Tuple of (collections, next_cursor, has_more)
        
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
        
        # Build query components
        where_clause, params = build_where_clause(
            gpt_id=gpt_id,
            cursor_data=cursor_data,
            order=pagination.order
        )
        order_clause = build_order_clause(pagination.order)
        
        # Query for one more item than requested to check for more pages
        limit = pagination.limit + 1
        
        async with pool.acquire() as conn:
            query = f"""
                SELECT id, gpt_id, name, schema, created_at
                FROM collections
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
            
            # Convert to Collection models
            collections = []
            for item in page_items:
                # Handle JSONB schema parsing
                if item.get('schema') and isinstance(item['schema'], str):
                    item['schema'] = json.loads(item['schema'])
                collection_row = CollectionRow.model_validate(item)
                collections.append(collection_row.to_collection())
            
            logger.debug(f"Listed {len(collections)} collections for GPT {gpt_id}")
            
            return collections, next_cursor, has_more
            
    except BadRequestError:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error listing collections: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error listing collections: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def update_collection(
    gpt_id: str,
    collection_name: str,
    update_data: CollectionUpdate
) -> Collection:
    """Update a collection's schema.
    
    Args:
        gpt_id: GPT ID that owns the collection
        collection_name: Name of the collection to update
        update_data: Update data
        
    Returns:
        Updated collection
        
    Raises:
        NotFoundError: If collection doesn't exist
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            query = """
                UPDATE collections
                SET schema = $3
                WHERE gpt_id = $1 AND name = $2
                RETURNING id, gpt_id, name, schema, created_at
            """
            
            # Convert schema dict to JSON string for JSONB parameter
            schema_json = None
            if update_data.json_schema:
                schema_json = json.dumps(update_data.json_schema)
            
            row = await conn.fetchrow(
                query,
                gpt_id,
                collection_name,
                schema_json
            )
            
            if not row:
                raise NotFoundError(f"Collection '{collection_name}' not found for GPT '{gpt_id}'")
            
            # Convert row to dict and handle JSONB schema parsing
            row_dict = dict(row)
            if row_dict.get('schema') and isinstance(row_dict['schema'], str):
                row_dict['schema'] = json.loads(row_dict['schema'])
            
            collection_row = CollectionRow.model_validate(row_dict)
            logger.info(f"Updated collection {collection_row.id} for GPT {gpt_id}")
            
            return collection_row.to_collection()
            
    except NotFoundError:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error updating collection: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating collection: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def delete_collection(
    gpt_id: str,
    collection_name: str
) -> bool:
    """Delete a collection.
    
    Args:
        gpt_id: GPT ID that owns the collection
        collection_name: Name of the collection to delete
        
    Returns:
        True if collection was deleted, False if not found
        
    Raises:
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            query = """
                DELETE FROM collections
                WHERE gpt_id = $1 AND name = $2
            """
            
            result = await conn.execute(query, gpt_id, collection_name)
            
            # Check if any rows were affected
            deleted = result.split()[-1] == "1"  # "DELETE 1" means one row deleted
            
            if deleted:
                logger.info(f"Deleted collection '{collection_name}' for GPT {gpt_id}")
            else:
                logger.debug(f"Collection '{collection_name}' not found for GPT {gpt_id}")
            
            return deleted
            
    except asyncpg.PostgresError as e:
        logger.error(f"Database error deleting collection: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting collection: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def collection_exists(
    gpt_id: str,
    collection_name: str
) -> bool:
    """Check if a collection exists.
    
    Args:
        gpt_id: GPT ID that owns the collection
        collection_name: Name of the collection
        
    Returns:
        True if collection exists, False otherwise
        
    Raises:
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            query = """
                SELECT 1 FROM collections
                WHERE gpt_id = $1 AND name = $2
                LIMIT 1
            """
            
            row = await conn.fetchrow(query, gpt_id, collection_name)
            exists = row is not None
            
            logger.debug(f"Collection '{collection_name}' exists for GPT {gpt_id}: {exists}")
            return exists
            
    except asyncpg.PostgresError as e:
        logger.error(f"Database error checking collection existence: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking collection existence: {e}")
        raise InternalServerError(f"Unexpected error: {e}")


async def get_collection_count(gpt_id: str) -> int:
    """Get total count of collections for a GPT.
    
    Args:
        gpt_id: GPT ID that owns the collections
        
    Returns:
        Total number of collections
        
    Raises:
        InternalServerError: If database operation fails
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            query = "SELECT COUNT(*) FROM collections WHERE gpt_id = $1"
            count = await conn.fetchval(query, gpt_id)
            
            logger.debug(f"Total collections for GPT {gpt_id}: {count}")
            return count or 0
            
    except asyncpg.PostgresError as e:
        logger.error(f"Database error counting collections: {e}")
        raise InternalServerError(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error counting collections: {e}")
        raise InternalServerError(f"Unexpected error: {e}")