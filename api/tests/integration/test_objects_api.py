"""Integration tests for objects API endpoints."""

import json
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from fastapi import status

from api.src.main import app
from api.src.models.objects import Object
from api.src.models.collections import Collection
from api.src.pagination import encode_cursor


class TestObjectsAPIIntegration:
    """Integration tests for objects API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Test client for FastAPI app."""
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self):
        """Mock authentication headers."""
        return {"Authorization": "Bearer test-api-key"}
    
    @pytest.fixture
    def sample_collection(self):
        """Sample collection for testing."""
        return Collection(
            id=uuid4(),
            gpt_id="gpt-4-test",
            name="notes",
            json_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]}
                },
                "required": ["title"]
            },
            created_at=datetime.now(timezone.utc)
        )
    
    @pytest.fixture
    def sample_object(self):
        """Sample object for testing."""
        return Object(
            id=uuid4(),
            gpt_id="gpt-4-test",
            collection="notes",
            body={
                "title": "Test Note",
                "content": "This is test content",
                "priority": "medium",
                "tags": ["test", "example"]
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
    
    def test_create_object_success(self, client, auth_headers, sample_object):
        """Test successful object creation."""
        with patch('api.src.routes.objects.create_object') as mock_create:
            mock_create.return_value = sample_object
            
            response = client.post(
                f"/gpts/{sample_object.gpt_id}/collections/{sample_object.collection}/objects",
                headers=auth_headers,
                json={
                    "body": sample_object.body
                }
            )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["id"] == str(sample_object.id)
        assert data["gpt_id"] == sample_object.gpt_id
        assert data["collection"] == sample_object.collection
        assert data["body"] == sample_object.body
    
    def test_create_object_invalid_body(self, client, auth_headers):
        """Test object creation with invalid body."""
        response = client.post(
            "/gpts/gpt-4-test/collections/notes/objects",
            headers=auth_headers,
            json={}  # Missing body field
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_object_validation_error(self, client, auth_headers):
        """Test object creation with schema validation error."""
        from api.src.errors.problem_details import BadRequestError
        
        with patch('api.src.routes.objects.create_object') as mock_create:
            mock_create.side_effect = BadRequestError("Object validation failed: 'title' is a required property")
            
            response = client.post(
                "/gpts/gpt-4-test/collections/notes/objects",
                headers=auth_headers,
                json={
                    "body": {"content": "Missing title"}
                }
            )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.headers["content-type"] == "application/problem+json"
        data = response.json()
        assert "Object validation failed" in data["detail"]
    
    def test_create_object_collection_not_found(self, client, auth_headers):
        """Test object creation when collection doesn't exist."""
        from api.src.errors.problem_details import NotFoundError
        
        with patch('api.src.routes.objects.create_object') as mock_create:
            mock_create.side_effect = NotFoundError("Collection 'nonexistent' not found")
            
            response = client.post(
                "/gpts/gpt-4-test/collections/nonexistent/objects",
                headers=auth_headers,
                json={
                    "body": {"title": "Test"}
                }
            )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.headers["content-type"] == "application/problem+json"
    
    def test_list_objects_success(self, client, auth_headers, sample_object):
        """Test successful object listing."""
        objects = [sample_object]
        
        with patch('api.src.routes.objects.list_objects') as mock_list:
            mock_list.return_value = (objects, None, False)
            
            response = client.get(
                f"/gpts/{sample_object.gpt_id}/collections/{sample_object.collection}/objects",
                headers=auth_headers
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["objects"]) == 1
        assert data["objects"][0]["id"] == str(sample_object.id)
        assert data["next_cursor"] is None
        assert data["has_more"] is False
    
    def test_list_objects_with_pagination(self, client, auth_headers, sample_object):
        """Test object listing with pagination."""
        objects = [sample_object]
        next_cursor = encode_cursor(sample_object.created_at, sample_object.id)
        
        with patch('api.src.routes.objects.list_objects') as mock_list:
            mock_list.return_value = (objects, next_cursor, True)
            
            response = client.get(
                f"/gpts/{sample_object.gpt_id}/collections/{sample_object.collection}/objects",
                headers=auth_headers,
                params={"limit": 1, "order": "desc"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["objects"]) == 1
        assert data["next_cursor"] == next_cursor
        assert data["has_more"] is True
        
        # Check Link header
        assert "Link" in response.headers
        link_header = response.headers["Link"]
        assert 'rel="next"' in link_header
        assert next_cursor in link_header
    
    def test_list_objects_with_cursor(self, client, auth_headers, sample_object):
        """Test object listing with cursor parameter."""
        cursor = encode_cursor(datetime.now(timezone.utc), uuid4())
        
        with patch('api.src.routes.objects.list_objects') as mock_list:
            mock_list.return_value = ([], None, False)
            
            response = client.get(
                f"/gpts/{sample_object.gpt_id}/collections/{sample_object.collection}/objects",
                headers=auth_headers,
                params={"cursor": cursor, "limit": 50}
            )
        
        assert response.status_code == status.HTTP_200_OK
        # Verify cursor was passed to the list function
        mock_list.assert_called_once()
        args = mock_list.call_args[0]
        pagination = args[2]  # Third argument is pagination
        assert pagination.cursor == cursor
    
    def test_list_objects_invalid_pagination(self, client, auth_headers):
        """Test object listing with invalid pagination parameters."""
        response = client.get(
            "/gpts/gpt-4-test/collections/notes/objects",
            headers=auth_headers,
            params={"limit": 0}  # Invalid limit
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_get_object_success(self, client, auth_headers, sample_object):
        """Test successful object retrieval."""
        with patch('api.src.routes.objects.get_object') as mock_get:
            mock_get.return_value = sample_object
            
            response = client.get(
                f"/objects/{sample_object.id}",
                headers=auth_headers
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(sample_object.id)
        assert data["gpt_id"] == sample_object.gpt_id
        assert data["collection"] == sample_object.collection
        assert data["body"] == sample_object.body
    
    def test_get_object_not_found(self, client, auth_headers):
        """Test object retrieval when object doesn't exist."""
        from api.src.errors.problem_details import NotFoundError
        
        object_id = uuid4()
        
        with patch('api.src.routes.objects.get_object') as mock_get:
            mock_get.side_effect = NotFoundError(f"Object '{object_id}' not found")
            
            response = client.get(
                f"/objects/{object_id}",
                headers=auth_headers
            )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.headers["content-type"] == "application/problem+json"
    
    def test_get_object_invalid_uuid(self, client, auth_headers):
        """Test object retrieval with invalid UUID."""
        response = client.get(
            "/objects/invalid-uuid",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_update_object_success(self, client, auth_headers, sample_object):
        """Test successful object update."""
        updated_object = Object(
            id=sample_object.id,
            gpt_id=sample_object.gpt_id,
            collection=sample_object.collection,
            body={**sample_object.body, "priority": "high", "updated": True},
            created_at=sample_object.created_at,
            updated_at=datetime.now(timezone.utc)  # New timestamp
        )
        
        with patch('api.src.routes.objects.update_object') as mock_update:
            mock_update.return_value = updated_object
            
            response = client.patch(
                f"/objects/{sample_object.id}",
                headers=auth_headers,
                json={
                    "body": {"priority": "high", "updated": True}
                }
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(sample_object.id)
        assert data["body"]["priority"] == "high"
        assert data["body"]["updated"] is True
        assert data["updated_at"] != data["created_at"]
    
    def test_update_object_partial_update(self, client, auth_headers, sample_object):
        """Test partial object update."""
        with patch('api.src.routes.objects.update_object') as mock_update:
            mock_update.return_value = sample_object
            
            response = client.patch(
                f"/objects/{sample_object.id}",
                headers=auth_headers,
                json={
                    "body": {"priority": "low"}  # Only updating priority
                }
            )
        
        assert response.status_code == status.HTTP_200_OK
        # Verify update was called with partial data
        mock_update.assert_called_once()
        args = mock_update.call_args[0]
        update_data = args[2]  # Third argument is update data
        assert update_data.body == {"priority": "low"}
    
    def test_update_object_validation_error(self, client, auth_headers, sample_object):
        """Test object update with validation error."""
        from api.src.errors.problem_details import BadRequestError
        
        with patch('api.src.routes.objects.update_object') as mock_update:
            mock_update.side_effect = BadRequestError("Object validation failed: invalid priority")
            
            response = client.patch(
                f"/objects/{sample_object.id}",
                headers=auth_headers,
                json={
                    "body": {"priority": "invalid"}
                }
            )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.headers["content-type"] == "application/problem+json"
    
    def test_update_object_not_found(self, client, auth_headers):
        """Test object update when object doesn't exist."""
        from api.src.errors.problem_details import NotFoundError
        
        object_id = uuid4()
        
        with patch('api.src.routes.objects.update_object') as mock_update:
            mock_update.side_effect = NotFoundError(f"Object '{object_id}' not found")
            
            response = client.patch(
                f"/objects/{object_id}",
                headers=auth_headers,
                json={
                    "body": {"title": "Updated"}
                }
            )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.headers["content-type"] == "application/problem+json"
    
    def test_delete_object_success(self, client, auth_headers, sample_object):
        """Test successful object deletion."""
        with patch('api.src.routes.objects.delete_object') as mock_delete:
            mock_delete.return_value = True
            
            response = client.delete(
                f"/objects/{sample_object.id}",
                headers=auth_headers
            )
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
    
    def test_delete_object_not_found(self, client, auth_headers):
        """Test object deletion when object doesn't exist."""
        object_id = uuid4()
        
        with patch('api.src.routes.objects.delete_object') as mock_delete:
            mock_delete.return_value = False
            
            response = client.delete(
                f"/objects/{object_id}",
                headers=auth_headers
            )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.headers["content-type"] == "application/problem+json"
    
    def test_objects_health_check(self, client):
        """Test objects health check endpoint."""
        response = client.get("/objects/health")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "objects"
    
    def test_unauthorized_access(self, client, sample_object):
        """Test unauthorized access to objects endpoints."""
        # Test without Authorization header
        response = client.get(f"/objects/{sample_object.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        response = client.post(
            f"/gpts/{sample_object.gpt_id}/collections/{sample_object.collection}/objects",
            json={"body": {"title": "Test"}}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        response = client.patch(
            f"/objects/{sample_object.id}",
            json={"body": {"title": "Updated"}}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        response = client.delete(f"/objects/{sample_object.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_gpt_id_validation(self, client, auth_headers):
        """Test GPT ID validation in path parameters."""
        # Test with mismatched GPT IDs (assuming auth returns different GPT ID)
        with patch('api.src.auth.dependencies.get_current_gpt_id') as mock_auth:
            mock_auth.return_value = "different-gpt-id"
            
            response = client.post(
                "/gpts/gpt-4-test/collections/notes/objects",
                headers=auth_headers,
                json={"body": {"title": "Test"}}
            )
        
        # Should fail validation (exact behavior depends on auth implementation)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
    
    def test_request_validation_edge_cases(self, client, auth_headers):
        """Test request validation edge cases."""
        # Test with empty JSON body
        response = client.post(
            "/gpts/gpt-4-test/collections/notes/objects",
            headers=auth_headers,
            json={}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test with invalid JSON
        response = client.post(
            "/gpts/gpt-4-test/collections/notes/objects",
            headers=auth_headers,
            data="invalid json",
            headers={**auth_headers, "Content-Type": "application/json"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test with very large limit
        response = client.get(
            "/gpts/gpt-4-test/collections/notes/objects",
            headers=auth_headers,
            params={"limit": 999}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_pagination_link_header_format(self, client, auth_headers, sample_object):
        """Test Link header format compliance with RFC 8288."""
        next_cursor = encode_cursor(sample_object.created_at, sample_object.id)
        
        with patch('api.src.routes.objects.list_objects') as mock_list:
            mock_list.return_value = ([sample_object], next_cursor, True)
            
            response = client.get(
                f"/gpts/{sample_object.gpt_id}/collections/{sample_object.collection}/objects",
                headers=auth_headers,
                params={"limit": 1, "order": "desc"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        assert "Link" in response.headers
        
        link_header = response.headers["Link"]
        # Check RFC 8288 format: <url>; rel="next"
        assert link_header.startswith("<")
        assert ">; rel=\"next\"" in link_header
        assert next_cursor in link_header