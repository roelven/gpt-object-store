"""Unit tests for collections functionality."""

import pytest
from datetime import datetime
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, patch

from src.models.collections import (
    Collection, CollectionCreate, CollectionUpdate, CollectionRow
)
from src.pagination import PaginationParams
from src.db.collections import (
    create_collection, get_collection, list_collections,
    update_collection, delete_collection, collection_exists
)
from src.errors.problem_details import (
    NotFoundError, ConflictError, InternalServerError
)


class TestCollectionModels:
    """Test collection Pydantic models."""
    
    def test_collection_create_valid(self):
        """Test valid collection creation model."""
        data = {
            "name": "test-collection",
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"}
                }
            }
        }
        
        collection = CollectionCreate(**data)
        assert collection.name == "test-collection"
        assert collection.json_schema == data["schema"]
    
    def test_collection_create_minimal(self):
        """Test collection creation with minimal data."""
        collection = CollectionCreate(name="minimal")
        assert collection.name == "minimal"
        assert collection.json_schema is None
    
    def test_collection_create_invalid_name(self):
        """Test collection creation with invalid name."""
        with pytest.raises(ValueError):
            CollectionCreate(name="")
    
    def test_collection_update_valid(self):
        """Test valid collection update model."""
        schema = {"type": "object", "properties": {"updated": {"type": "boolean"}}}
        update = CollectionUpdate(schema=schema)
        assert update.json_schema == schema
    
    def test_collection_model_valid(self):
        """Test complete collection model."""
        data = {
            "id": uuid4(),
            "gpt_id": "test-gpt",
            "name": "test-collection",
            "schema": {"type": "object"},
            "created_at": datetime.utcnow()
        }
        
        collection = Collection(**data)
        assert collection.id == data["id"]
        assert collection.gpt_id == data["gpt_id"]
        assert collection.name == data["name"]
        assert collection.json_schema == data["schema"]
        assert collection.created_at == data["created_at"]
    
    def test_collection_row_to_collection(self):
        """Test conversion from database row to collection model."""
        row_data = {
            "id": uuid4(),
            "gpt_id": "test-gpt",
            "name": "test-collection",
            "schema": {"type": "object"},
            "created_at": datetime.utcnow()
        }
        
        row = CollectionRow(**row_data)
        collection = row.to_collection()
        
        assert isinstance(collection, Collection)
        assert collection.id == row_data["id"]
        assert collection.gpt_id == row_data["gpt_id"]


class TestCollectionDatabase:
    """Test collection database operations."""
    
    @pytest.fixture  
    def mock_db_pool(self):
        """Mock database pool with proper async context manager."""
        pool = AsyncMock()
        conn = AsyncMock()
        
        # Mock the context manager directly
        pool.acquire = AsyncMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        
        return pool, conn
    
    @pytest.fixture
    def sample_collection_row(self):
        """Sample collection database row."""
        return {
            "id": uuid4(),
            "gpt_id": "test-gpt",
            "name": "test-collection",
            "schema": {"type": "object"},
            "created_at": datetime.utcnow()
        }
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_create_collection_success(self, mock_get_pool, mock_db_pool, sample_collection_row):
        """Test successful collection creation."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.fetchrow.return_value = sample_collection_row
        
        collection_data = CollectionCreate(
            name="test-collection",
            schema={"type": "object"}
        )
        
        result = await create_collection("test-gpt", collection_data)
        
        assert isinstance(result, Collection)
        assert result.name == "test-collection"
        assert result.gpt_id == "test-gpt"
        conn.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_create_collection_database_error(self, mock_get_pool, mock_db_pool):
        """Test collection creation with database error."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.fetchrow.side_effect = Exception("Database error")
        
        collection_data = CollectionCreate(name="test-collection")
        
        with pytest.raises(InternalServerError):
            await create_collection("test-gpt", collection_data)
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_get_collection_success(self, mock_get_pool, mock_db_pool, sample_collection_row):
        """Test successful collection retrieval."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.fetchrow.return_value = sample_collection_row
        
        result = await get_collection("test-gpt", "test-collection")
        
        assert isinstance(result, Collection)
        assert result.name == "test-collection"
        conn.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_get_collection_not_found(self, mock_get_pool, mock_db_pool):
        """Test collection retrieval when not found."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.fetchrow.return_value = None
        
        with pytest.raises(NotFoundError):
            await get_collection("test-gpt", "nonexistent")
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_list_collections_success(self, mock_get_pool, mock_db_pool, sample_collection_row):
        """Test successful collection listing."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.fetch.return_value = [sample_collection_row]
        
        pagination = PaginationParams(limit=10)
        collections, next_cursor, has_more = await list_collections("test-gpt", pagination)
        
        assert len(collections) == 1
        assert isinstance(collections[0], Collection)
        assert next_cursor is None
        assert has_more is False
        conn.fetch.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_list_collections_with_pagination(self, mock_get_pool, mock_db_pool, sample_collection_row):
        """Test collection listing with pagination."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        
        # Return more items than limit to test pagination
        rows = [sample_collection_row.copy() for _ in range(3)]
        for i, row in enumerate(rows):
            row["id"] = uuid4()
            row["name"] = f"collection-{i}"
        
        conn.fetch.return_value = rows
        
        pagination = PaginationParams(limit=2)
        collections, next_cursor, has_more = await list_collections("test-gpt", pagination)
        
        assert len(collections) == 2
        assert has_more is True
        assert next_cursor is not None
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_update_collection_success(self, mock_get_pool, mock_db_pool, sample_collection_row):
        """Test successful collection update."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        
        updated_row = sample_collection_row.copy()
        updated_row["schema"] = {"type": "object", "updated": True}
        conn.fetchrow.return_value = updated_row
        
        update_data = CollectionUpdate(schema={"type": "object", "updated": True})
        result = await update_collection("test-gpt", "test-collection", update_data)
        
        assert isinstance(result, Collection)
        assert result.schema == {"type": "object", "updated": True}
        conn.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_update_collection_not_found(self, mock_get_pool, mock_db_pool):
        """Test collection update when not found."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.fetchrow.return_value = None
        
        update_data = CollectionUpdate(schema={"type": "object"})
        
        with pytest.raises(NotFoundError):
            await update_collection("test-gpt", "nonexistent", update_data)
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_delete_collection_success(self, mock_get_pool, mock_db_pool):
        """Test successful collection deletion."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.execute.return_value = "DELETE 1"
        
        result = await delete_collection("test-gpt", "test-collection")
        
        assert result is True
        conn.execute.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_delete_collection_not_found(self, mock_get_pool, mock_db_pool):
        """Test collection deletion when not found."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.execute.return_value = "DELETE 0"
        
        result = await delete_collection("test-gpt", "nonexistent")
        
        assert result is False
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_collection_exists_true(self, mock_get_pool, mock_db_pool):
        """Test collection existence check when exists."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.fetchrow.return_value = {"exists": True}
        
        result = await collection_exists("test-gpt", "test-collection")
        
        assert result is True
        conn.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.db.collections.get_db_pool')
    async def test_collection_exists_false(self, mock_get_pool, mock_db_pool):
        """Test collection existence check when not exists."""
        pool, conn = mock_db_pool
        mock_get_pool.return_value = pool
        conn.fetchrow.return_value = None
        
        result = await collection_exists("test-gpt", "nonexistent")
        
        assert result is False


class TestPaginationParams:
    """Test pagination parameter validation."""
    
    def test_pagination_params_defaults(self):
        """Test pagination parameters with defaults."""
        params = PaginationParams()
        assert params.limit == 50
        assert params.cursor is None
        assert params.order == "desc"
    
    def test_pagination_params_custom(self):
        """Test pagination parameters with custom values."""
        params = PaginationParams(limit=10, cursor="test", order="asc")
        assert params.limit == 10
        assert params.cursor == "test"
        assert params.order == "asc"
    
    def test_pagination_params_validation(self):
        """Test pagination parameter validation."""
        with pytest.raises(ValueError):
            PaginationParams(limit=0)  # Too small
        
        with pytest.raises(ValueError):
            PaginationParams(limit=300)  # Too large
        
        with pytest.raises(ValueError):
            PaginationParams(order="invalid")  # Invalid order


if __name__ == "__main__":
    pytest.main([__file__])