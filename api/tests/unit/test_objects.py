"""Unit tests for objects models and database operations."""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import asyncpg
import jsonschema

from api.src.models.objects import (
    ObjectBase, ObjectCreate, ObjectUpdate, Object, ObjectResponse,
    ObjectListResponse, ObjectRow, ObjectsQueryParams
)
from api.src.db.objects import (
    validate_object_against_schema, create_object, get_object, list_objects,
    update_object, delete_object, object_exists, get_object_count
)
from api.src.pagination import PaginationParams
from api.src.errors.problem_details import (
    NotFoundError, BadRequestError, InternalServerError
)


class TestObjectModels:
    """Test object Pydantic models."""
    
    def test_object_base_model(self):
        """Test ObjectBase model validation."""
        data = {
            "body": {"title": "Test", "content": "Content", "tags": ["tag1", "tag2"]}
        }
        obj = ObjectBase(**data)
        assert obj.body == data["body"]
    
    def test_object_create_model(self):
        """Test ObjectCreate model validation."""
        data = {
            "body": {"title": "Test Note", "content": "Note content"}
        }
        obj = ObjectCreate(**data)
        assert obj.body == data["body"]
    
    def test_object_update_model(self):
        """Test ObjectUpdate model validation."""
        # Test with body
        data = {"body": {"priority": "high"}}
        obj = ObjectUpdate(**data)
        assert obj.body == data["body"]
        
        # Test with None body (no update)
        obj_none = ObjectUpdate()
        assert obj_none.body is None
    
    def test_object_model(self):
        """Test complete Object model."""
        object_id = uuid4()
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)
        
        data = {
            "id": object_id,
            "gpt_id": "gpt-4",
            "collection": "notes",
            "body": {"title": "Test", "content": "Content"},
            "created_at": created_at,
            "updated_at": updated_at
        }
        
        obj = Object(**data)
        assert obj.id == object_id
        assert obj.gpt_id == "gpt-4"
        assert obj.collection == "notes"
        assert obj.body == data["body"]
        assert obj.created_at == created_at
        assert obj.updated_at == updated_at
    
    def test_object_row_to_object_conversion(self):
        """Test ObjectRow to Object conversion."""
        object_id = uuid4()
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)
        
        row_data = {
            "id": object_id,
            "gpt_id": "gpt-4",
            "collection": "notes",
            "body": {"title": "Test", "content": "Content"},
            "created_at": created_at,
            "updated_at": updated_at
        }
        
        row = ObjectRow(**row_data)
        obj = row.to_object()
        
        assert isinstance(obj, Object)
        assert obj.id == object_id
        assert obj.gpt_id == "gpt-4"
        assert obj.collection == "notes"
        assert obj.body == row_data["body"]
    
    def test_object_list_response_model(self):
        """Test ObjectListResponse model."""
        object_id = uuid4()
        obj_data = {
            "id": object_id,
            "gpt_id": "gpt-4",
            "collection": "notes",
            "body": {"title": "Test"},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        obj = Object(**obj_data)
        response_data = {
            "objects": [obj],
            "next_cursor": "cursor123",
            "has_more": True
        }
        
        response = ObjectListResponse(**response_data)
        assert len(response.objects) == 1
        assert response.next_cursor == "cursor123"
        assert response.has_more is True
    
    def test_objects_query_params(self):
        """Test ObjectsQueryParams model."""
        # Test defaults
        params = ObjectsQueryParams()
        assert params.limit == 50
        assert params.cursor is None
        assert params.order == "desc"
        
        # Test with values
        params = ObjectsQueryParams(limit=100, cursor="abc123", order="asc")
        assert params.limit == 100
        assert params.cursor == "abc123"
        assert params.order == "asc"
        
        # Test validation
        with pytest.raises(ValueError):
            ObjectsQueryParams(limit=0)  # Below minimum
        
        with pytest.raises(ValueError):
            ObjectsQueryParams(limit=300)  # Above maximum
        
        with pytest.raises(ValueError):
            ObjectsQueryParams(order="invalid")  # Invalid order


class TestObjectSchemaValidation:
    """Test JSON Schema validation for objects."""
    
    @pytest.fixture
    def mock_collection_with_schema(self):
        """Mock collection with JSON schema."""
        collection = MagicMock()
        collection.json_schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]}
            },
            "required": ["title"]
        }
        return collection
    
    @pytest.fixture
    def mock_collection_no_schema(self):
        """Mock collection without JSON schema."""
        collection = MagicMock()
        collection.json_schema = None
        return collection
    
    @pytest.mark.asyncio
    async def test_validate_object_against_schema_valid(self, mock_collection_with_schema):
        """Test validation with valid object data."""
        with patch('api.src.db.objects.get_collection', return_value=mock_collection_with_schema):
            object_data = {"title": "Test Note", "priority": "high"}
            # Should not raise any exception
            await validate_object_against_schema("gpt-4", "notes", object_data)
    
    @pytest.mark.asyncio
    async def test_validate_object_against_schema_invalid(self, mock_collection_with_schema):
        """Test validation with invalid object data."""
        with patch('api.src.db.objects.get_collection', return_value=mock_collection_with_schema):
            # Missing required field
            object_data = {"priority": "high"}
            
            with pytest.raises(BadRequestError) as exc_info:
                await validate_object_against_schema("gpt-4", "notes", object_data)
            
            assert "Object validation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_object_against_schema_no_schema(self, mock_collection_no_schema):
        """Test validation when collection has no schema."""
        with patch('api.src.db.objects.get_collection', return_value=mock_collection_no_schema):
            object_data = {"anything": "goes"}
            # Should not raise any exception
            await validate_object_against_schema("gpt-4", "notes", object_data)
    
    @pytest.mark.asyncio
    async def test_validate_object_against_schema_invalid_schema(self):
        """Test validation with invalid schema."""
        collection = MagicMock()
        collection.json_schema = {"type": "invalid_type"}  # Invalid schema
        
        with patch('api.src.db.objects.get_collection', return_value=collection):
            object_data = {"title": "Test"}
            
            with pytest.raises(InternalServerError) as exc_info:
                await validate_object_against_schema("gpt-4", "notes", object_data)
            
            assert "Collection schema is invalid" in str(exc_info.value)


class TestObjectDatabaseOperations:
    """Test object database operations."""
    
    @pytest.fixture
    def mock_db_pool(self):
        """Mock database connection pool with proper async context manager."""
        from unittest.mock import MagicMock
        
        pool = MagicMock()
        conn = AsyncMock()
        
        # Create a simple context manager that doesn't use asyncio
        class MockContextManager:
            def __init__(self, conn):
                self.conn = conn
            
            async def __aenter__(self):
                return self.conn
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False
        
        # Mock pool.acquire() to return the context manager
        pool.acquire.return_value = MockContextManager(conn)
        
        return pool, conn
    
    @pytest.fixture
    def sample_object_data(self):
        """Sample object data for testing."""
        return {
            "id": uuid4(),
            "gpt_id": "gpt-4",
            "collection": "notes",
            "body": {"title": "Test Note", "content": "Content"},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
    
    @pytest.mark.asyncio
    async def test_create_object_success(self, mock_db_pool, sample_object_data):
        """Test successful object creation."""
        pool, conn = mock_db_pool
        
        async def mock_get_pool():
            return pool
            
        conn.fetchrow.return_value = sample_object_data
        
        object_create = ObjectCreate(body=sample_object_data["body"])
        
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            with patch('api.src.db.objects.validate_object_against_schema') as mock_validate:
                result = await create_object("gpt-4", "notes", object_create)
        
        mock_validate.assert_called_once()
        assert isinstance(result, Object)
        assert result.gpt_id == "gpt-4"
        assert result.collection == "notes"
        assert result.body == sample_object_data["body"]
    
    @pytest.mark.asyncio
    async def test_create_object_foreign_key_violation(self, mock_db_pool):
        """Test object creation with foreign key violation."""
        pool, conn = mock_db_pool
        conn.fetchrow.side_effect = asyncpg.ForeignKeyViolationError("Foreign key violation")
        
        async def mock_get_pool():
            return pool
        
        object_create = ObjectCreate(body={"title": "Test"})
        
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            with patch('api.src.db.objects.validate_object_against_schema'):
                with pytest.raises(NotFoundError) as exc_info:
                    await create_object("gpt-4", "nonexistent", object_create)
        
        assert "Collection 'nonexistent' not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_object_success(self, mock_db_pool, sample_object_data):
        """Test successful object retrieval."""
        pool, conn = mock_db_pool
        conn.fetchrow.return_value = sample_object_data
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            result = await get_object(sample_object_data["id"], "gpt-4")
        
        assert isinstance(result, Object)
        assert result.id == sample_object_data["id"]
        assert result.gpt_id == "gpt-4"
    
    @pytest.mark.asyncio
    async def test_get_object_not_found(self, mock_db_pool):
        """Test object retrieval when object doesn't exist."""
        pool, conn = mock_db_pool
        conn.fetchrow.return_value = None
        
        object_id = uuid4()
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            with pytest.raises(NotFoundError) as exc_info:
                await get_object(object_id, "gpt-4")
        
        assert f"Object '{object_id}' not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_list_objects_success(self, mock_db_pool, sample_object_data):
        """Test successful object listing."""
        pool, conn = mock_db_pool
        
        # Mock database rows
        rows = [sample_object_data]
        conn.fetch.return_value = rows
        
        pagination = PaginationParams(limit=50, cursor=None, order="desc")
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            objects, next_cursor, has_more = await list_objects("gpt-4", "notes", pagination)
        
        assert len(objects) == 1
        assert isinstance(objects[0], Object)
        assert objects[0].id == sample_object_data["id"]
        assert next_cursor is None  # No more items
        assert has_more is False
    
    @pytest.mark.asyncio
    async def test_update_object_success(self, mock_db_pool, sample_object_data):
        """Test successful object update."""
        pool, conn = mock_db_pool
        
        # Mock get_object to return existing object
        existing_object = Object(**sample_object_data)
        
        # Mock updated object data
        updated_data = {**sample_object_data}
        updated_data["body"] = {"title": "Updated Title", "content": "Updated Content"}
        updated_data["updated_at"] = datetime.now(timezone.utc)
        conn.fetchrow.return_value = updated_data
        
        update_data = ObjectUpdate(body={"title": "Updated Title"})
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            with patch('api.src.db.objects.get_object', return_value=existing_object):
                with patch('api.src.db.objects.validate_object_against_schema'):
                    result = await update_object(sample_object_data["id"], "gpt-4", update_data)
        
        assert isinstance(result, Object)
        assert result.body["title"] == "Updated Title"
        assert result.body["content"] == "Updated Content"  # Merged from existing
    
    @pytest.mark.asyncio
    async def test_delete_object_success(self, mock_db_pool):
        """Test successful object deletion."""
        pool, conn = mock_db_pool
        conn.execute.return_value = "DELETE 1"
        
        object_id = uuid4()
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            result = await delete_object(object_id, "gpt-4")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_delete_object_not_found(self, mock_db_pool):
        """Test object deletion when object doesn't exist."""
        pool, conn = mock_db_pool
        conn.execute.return_value = "DELETE 0"
        
        object_id = uuid4()
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            result = await delete_object(object_id, "gpt-4")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_object_exists_true(self, mock_db_pool):
        """Test object existence check when object exists."""
        pool, conn = mock_db_pool
        conn.fetchrow.return_value = {"exists": True}
        
        object_id = uuid4()
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            result = await object_exists(object_id, "gpt-4")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_object_exists_false(self, mock_db_pool):
        """Test object existence check when object doesn't exist."""
        pool, conn = mock_db_pool
        conn.fetchrow.return_value = None
        
        object_id = uuid4()
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            result = await object_exists(object_id, "gpt-4")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_object_count_with_collection(self, mock_db_pool):
        """Test object count with collection filter."""
        pool, conn = mock_db_pool
        conn.fetchval.return_value = 5
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            count = await get_object_count("gpt-4", "notes")
        
        assert count == 5
    
    @pytest.mark.asyncio
    async def test_get_object_count_all_collections(self, mock_db_pool):
        """Test object count for all collections."""
        pool, conn = mock_db_pool
        conn.fetchval.return_value = 10
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            count = await get_object_count("gpt-4")
        
        assert count == 10
    
    @pytest.mark.asyncio
    async def test_database_error_handling(self, mock_db_pool):
        """Test database error handling."""
        pool, conn = mock_db_pool
        conn.fetchrow.side_effect = asyncpg.PostgresError("Database error")
        
        object_id = uuid4()
        
        async def mock_get_pool():
            return pool
            
        with patch('api.src.db.objects.get_db_pool', side_effect=mock_get_pool):
            with pytest.raises(InternalServerError) as exc_info:
                await get_object(object_id, "gpt-4")
        
        assert "Database error" in str(exc_info.value)