"""Integration tests for collections API endpoints."""

import pytest
import json
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from fastapi import status

from src.main import create_app
from src.models.collections import Collection
from src.errors.problem_details import NotFoundError


@pytest.fixture
def test_client():
    """Create test client for API testing."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_auth():
    """Mock authentication middleware."""
    with patch('src.auth.middleware.auth_middleware') as mock:
        mock.return_value = AsyncMock()
        yield mock


@pytest.fixture
def mock_get_current_gpt_id():
    """Mock current GPT ID dependency."""
    with patch('src.auth.dependencies.get_current_gpt_id_from_state') as mock:
        mock.return_value = "test-gpt"
        yield mock


@pytest.fixture
def sample_collection():
    """Sample collection data."""
    return {
        "id": str(uuid4()),
        "gpt_id": "test-gpt",
        "name": "test-collection",
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["title"]
        },
        "created_at": datetime.utcnow().isoformat()
    }


class TestCollectionsAPI:
    """Test collections API endpoints."""
    
    def test_create_collection_success(self, test_client, mock_get_current_gpt_id):
        """Test successful collection creation."""
        with patch('src.db.collections.create_collection') as mock_create:
            # Mock the create_collection function
            mock_collection = Collection(
                id=uuid4(),
                gpt_id="test-gpt",
                name="new-collection",
                schema={"type": "object"},
                created_at=datetime.utcnow()
            )
            mock_create.return_value = mock_collection
            
            collection_data = {
                "name": "new-collection",
                "schema": {"type": "object"}
            }
            
            response = test_client.post(
                "/v1/gpts/test-gpt/collections",
                json=collection_data,
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["name"] == "new-collection"
            assert data["gpt_id"] == "test-gpt"
            assert data["schema"] == {"type": "object"}
    
    def test_create_collection_minimal(self, test_client, mock_get_current_gpt_id):
        """Test collection creation with minimal data."""
        with patch('src.db.collections.create_collection') as mock_create:
            mock_collection = Collection(
                id=uuid4(),
                gpt_id="test-gpt",
                name="minimal-collection",
                schema=None,
                created_at=datetime.utcnow()
            )
            mock_create.return_value = mock_collection
            
            collection_data = {"name": "minimal-collection"}
            
            response = test_client.post(
                "/v1/gpts/test-gpt/collections",
                json=collection_data,
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["name"] == "minimal-collection"
            assert data["schema"] is None
    
    def test_create_collection_invalid_data(self, test_client, mock_get_current_gpt_id):
        """Test collection creation with invalid data."""
        collection_data = {"name": ""}  # Empty name should fail validation
        
        response = test_client.post(
            "/v1/gpts/test-gpt/collections",
            json=collection_data,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_collection_unauthorized(self, test_client):
        """Test collection creation without authorization."""
        collection_data = {"name": "test-collection"}
        
        response = test_client.post(
            "/v1/gpts/test-gpt/collections",
            json=collection_data
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_collection_success(self, test_client, mock_get_current_gpt_id, sample_collection):
        """Test successful collection retrieval."""
        with patch('src.db.collections.get_collection') as mock_get:
            mock_collection = Collection(**sample_collection)
            mock_get.return_value = mock_collection
            
            response = test_client.get(
                "/v1/gpts/test-gpt/collections/test-collection",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["name"] == "test-collection"
            assert data["gpt_id"] == "test-gpt"
    
    def test_get_collection_not_found(self, test_client, mock_get_current_gpt_id):
        """Test collection retrieval when not found."""
        with patch('src.db.collections.get_collection') as mock_get:
            mock_get.side_effect = NotFoundError("Collection not found")
            
            response = test_client.get(
                "/v1/gpts/test-gpt/collections/nonexistent",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert response.headers["content-type"] == "application/problem+json"
    
    def test_list_collections_success(self, test_client, mock_get_current_gpt_id, sample_collection):
        """Test successful collections listing."""
        with patch('src.db.collections.list_collections') as mock_list:
            mock_collection = Collection(**sample_collection)
            mock_list.return_value = ([mock_collection], None, False)
            
            response = test_client.get(
                "/v1/gpts/test-gpt/collections",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "collections" in data
            assert len(data["collections"]) == 1
            assert data["collections"][0]["name"] == "test-collection"
            assert data["has_more"] is False
            assert data["next_cursor"] is None
    
    def test_list_collections_with_pagination(self, test_client, mock_get_current_gpt_id):
        """Test collections listing with pagination."""
        with patch('src.db.collections.list_collections') as mock_list:
            collections = [
                Collection(
                    id=uuid4(),
                    gpt_id="test-gpt",
                    name=f"collection-{i}",
                    schema=None,
                    created_at=datetime.utcnow()
                )
                for i in range(2)
            ]
            mock_list.return_value = (collections, "next-cursor", True)
            
            response = test_client.get(
                "/v1/gpts/test-gpt/collections?limit=2",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data["collections"]) == 2
            assert data["has_more"] is True
            assert data["next_cursor"] == "next-cursor"
            
            # Check Link header is present
            assert "Link" in response.headers
    
    def test_list_collections_with_cursor(self, test_client, mock_get_current_gpt_id):
        """Test collections listing with cursor."""
        with patch('src.db.collections.list_collections') as mock_list:
            mock_list.return_value = ([], None, False)
            
            response = test_client.get(
                "/v1/gpts/test-gpt/collections?cursor=test-cursor&limit=10&order=asc",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_200_OK
            
            # Verify the mock was called with correct pagination params
            mock_list.assert_called_once()
            call_args = mock_list.call_args
            pagination = call_args[0][1]  # Second argument is pagination
            assert pagination.cursor == "test-cursor"
            assert pagination.limit == 10
            assert pagination.order == "asc"
    
    def test_update_collection_success(self, test_client, mock_get_current_gpt_id, sample_collection):
        """Test successful collection update."""
        with patch('src.db.collections.update_collection') as mock_update:
            updated_collection = Collection(**sample_collection)
            updated_collection.schema = {"type": "object", "updated": True}
            mock_update.return_value = updated_collection
            
            update_data = {"schema": {"type": "object", "updated": True}}
            
            response = test_client.patch(
                "/v1/gpts/test-gpt/collections/test-collection",
                json=update_data,
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["schema"]["updated"] is True
    
    def test_update_collection_not_found(self, test_client, mock_get_current_gpt_id):
        """Test collection update when not found."""
        with patch('src.db.collections.update_collection') as mock_update:
            mock_update.side_effect = NotFoundError("Collection not found")
            
            update_data = {"schema": {"type": "object"}}
            
            response = test_client.patch(
                "/v1/gpts/test-gpt/collections/nonexistent",
                json=update_data,
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_delete_collection_success(self, test_client, mock_get_current_gpt_id):
        """Test successful collection deletion."""
        with patch('src.db.collections.delete_collection') as mock_delete:
            mock_delete.return_value = True
            
            response = test_client.delete(
                "/v1/gpts/test-gpt/collections/test-collection",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_204_NO_CONTENT
    
    def test_delete_collection_not_found(self, test_client, mock_get_current_gpt_id):
        """Test collection deletion when not found."""
        with patch('src.db.collections.delete_collection') as mock_delete:
            mock_delete.return_value = False
            
            response = test_client.delete(
                "/v1/gpts/test-gpt/collections/nonexistent",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_collections_health(self, test_client):
        """Test collections health endpoint."""
        response = test_client.get("/v1/gpts/test-gpt/collections/health")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "collections"


class TestCollectionsValidation:
    """Test collections API parameter validation."""
    
    def test_list_collections_invalid_limit(self, test_client, mock_get_current_gpt_id):
        """Test collections listing with invalid limit."""
        response = test_client.get(
            "/v1/gpts/test-gpt/collections?limit=0",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_list_collections_limit_too_large(self, test_client, mock_get_current_gpt_id):
        """Test collections listing with limit too large."""
        response = test_client.get(
            "/v1/gpts/test-gpt/collections?limit=300",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_list_collections_invalid_order(self, test_client, mock_get_current_gpt_id):
        """Test collections listing with invalid order."""
        response = test_client.get(
            "/v1/gpts/test-gpt/collections?order=invalid",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_list_collections_invalid_cursor(self, test_client, mock_get_current_gpt_id):
        """Test collections listing with invalid cursor."""
        with patch('src.db.collections.list_collections') as mock_list:
            from src.errors.problem_details import BadRequestError
            mock_list.side_effect = BadRequestError("Invalid cursor format")
            
            response = test_client.get(
                "/v1/gpts/test-gpt/collections?cursor=invalid-cursor",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestCollectionsAuth:
    """Test collections API authentication and authorization."""
    
    def test_gpt_id_mismatch(self, test_client):
        """Test access denied when GPT ID doesn't match authenticated user."""
        with patch('src.auth.dependencies.get_current_gpt_id_from_state') as mock_auth:
            mock_auth.return_value = "different-gpt"
            
            response = test_client.get(
                "/v1/gpts/test-gpt/collections",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == status.HTTP_403_FORBIDDEN


if __name__ == "__main__":
    pytest.main([__file__])