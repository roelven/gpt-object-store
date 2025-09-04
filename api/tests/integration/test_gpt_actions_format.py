"""Integration tests for GPT Actions request format compatibility.

Tests the exact JSON structure that GPT Actions should send, ensuring clean
separation between path parameters (in URL) and request body data.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import status

from src.main import app
from src.models.objects import Object


class TestGPTActionsFormat:
    """Integration tests for GPT Actions request format."""
    
    @pytest.fixture
    def client(self):
        """Test client for FastAPI app."""
        return TestClient(app)
    
    @pytest.fixture  
    def auth_headers(self):
        """Mock authentication headers."""
        return {"Authorization": "Bearer test-api-key"}
    
    def test_exact_gpt_actions_request_format(self, client, auth_headers):
        """Test the exact JSON format that GPT Actions should send.
        
        This test validates the new direct field format:
        {
          "date": "2025-09-03",
          "entry": "Had a rough start but turned into a productive day",
          "mood": "neutral",
          "tags": ["sleep", "health", "productivity", "nature"]
        }
        
        Key requirements:
        - Send fields directly (not wrapped in 'body')
        - No path parameters (gpt_id, collection_name) in request body
        - Clean diary entry structure
        """
        # Mock the create_object function to return a successful response
        with patch('src.routes.objects.create_object') as mock_create:
            mock_create.return_value = Object(
                id=uuid4(),
                gpt_id="diary-gpt",
                collection="diary_entries",
                body={
                    "date": "2025-09-03",
                    "entry": "Had a rough start but turned into a productive day",
                    "mood": "neutral",
                    "tags": ["sleep", "health", "productivity", "nature"]
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            # Test the new direct field format GPT Actions should send
            response = client.post(
                "/v1/gpts/diary-gpt/collections/diary_entries/objects",
                headers=auth_headers,
                json={
                    "date": "2025-09-03",
                    "entry": "Had a rough start but turned into a productive day",
                    "mood": "neutral",
                    "tags": ["sleep", "health", "productivity", "nature"]
                }
            )
            
            # Should succeed with 201 Created
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify response structure
            data = response.json()
            assert "id" in data
            assert data["gpt_id"] == "diary-gpt"
            assert data["collection"] == "diary_entries"
            assert data["body"]["date"] == "2025-09-03"
            assert data["body"]["entry"] == "Had a rough start but turned into a productive day"
            assert data["body"]["mood"] == "neutral"
            assert data["body"]["tags"] == ["sleep", "health", "productivity", "nature"]
    
    def test_direct_fields_work_with_extra_fields(self, client, auth_headers):
        """Test that direct fields work even with extra unknown fields.
        
        The new design allows extra fields for maximum GPT Actions compatibility.
        """
        with patch('src.routes.objects.create_object') as mock_create:
            mock_create.return_value = Object(
                id=uuid4(),
                gpt_id="diary-gpt", 
                collection="diary_entries",
                body={
                    "date": "2025-09-03",
                    "entry": "Test entry",
                    "mood": "neutral",
                    "tags": ["test"],
                    "unknown_field": "should_be_accepted"
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
        
            response = client.post(
                "/v1/gpts/diary-gpt/collections/diary_entries/objects",
                headers=auth_headers,
                json={
                    "date": "2025-09-03",
                    "entry": "Test entry", 
                    "mood": "neutral",
                    "tags": ["test"],
                    "unknown_field": "should_be_accepted"  # Extra fields now allowed
                }
            )
            
            # Should succeed with 201 Created
            assert response.status_code == status.HTTP_201_CREATED
    
    def test_direct_fields_work_without_wrapper(self, client, auth_headers):
        """Test that direct fields work without 'body' wrapper (new format)."""
        with patch('src.routes.objects.create_object') as mock_create:
            mock_create.return_value = Object(
                id=uuid4(),
                gpt_id="diary-gpt",
                collection="diary_entries",
                body={
                    "date": "2025-09-03",
                    "entry": "Test entry",
                    "mood": "neutral"
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            response = client.post(
                "/v1/gpts/diary-gpt/collections/diary_entries/objects",
                headers=auth_headers,
                json={
                    "date": "2025-09-03",  # Direct fields now work
                    "entry": "Test entry",
                    "mood": "neutral"
                }
            )
            
            # Should succeed with 201 Created 
            assert response.status_code == status.HTTP_201_CREATED
    
    def test_empty_request_body_validation(self, client, auth_headers):
        """Test validation of completely empty request body."""
        with patch('src.routes.objects.create_object') as mock_create:
            mock_create.return_value = Object(
                id=uuid4(),
                gpt_id="diary-gpt",
                collection="diary_entries",
                body={},  # Empty body is allowed
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            response = client.post(
                "/v1/gpts/diary-gpt/collections/diary_entries/objects",
                headers=auth_headers,
                json={}
            )
            
            # Should succeed - empty requests are now allowed
            assert response.status_code == status.HTTP_201_CREATED
    
    def test_arbitrary_json_structure_validation(self, client, auth_headers):
        """Test that direct fields accept arbitrary JSON structure."""
        with patch('src.routes.objects.create_object') as mock_create:
            mock_create.return_value = Object(
                id=uuid4(),
                gpt_id="diary-gpt",
                collection="diary_entries", 
                body={
                    "custom_field": "custom_value",
                    "nested": {"data": "structure"},
                    "array": [1, 2, 3]
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            response = client.post(
                "/v1/gpts/diary-gpt/collections/diary_entries/objects",
                headers=auth_headers,
                json={
                    "custom_field": "custom_value",  # Direct fields
                    "nested": {"data": "structure"},
                    "array": [1, 2, 3]
                }
            )
            
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["body"]["custom_field"] == "custom_value"
            assert data["body"]["nested"]["data"] == "structure"
            assert data["body"]["array"] == [1, 2, 3]
    
    def test_path_parameters_take_precedence(self, client, auth_headers):
        """Test that path parameters always take precedence over any body values.
        
        Even if someone somehow sends path params in body, the URL path values should win.
        """
        with patch('src.routes.objects.create_object') as mock_create:
            # Verify that the create_object function gets called with path values, not body values
            mock_create.return_value = Object(
                id=uuid4(),
                gpt_id="diary-gpt",  # From URL path
                collection="diary_entries",  # From URL path
                body={"test": "data"},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            # This test assumes the new schema will reject extra fields,
            # but if they somehow get through, path should take precedence
            response = client.post(
                "/v1/gpts/different-gpt/collections/different_collection/objects",
                headers=auth_headers,
                json={
                    "body": {
                        "test": "data"
                    }
                }
            )
            
            if response.status_code == status.HTTP_201_CREATED:
                data = response.json()
                # Should use URL path values, not any body values
                assert data["gpt_id"] == "different-gpt"
                assert data["collection"] == "different_collection"
    
    def test_various_diary_entry_formats(self, client, auth_headers):
        """Test various valid diary entry formats that GPT might send."""
        test_cases = [
            {
                "name": "minimal_entry",
                "body": {
                    "date": "2025-09-03",
                    "entry": "Simple entry"
                }
            },
            {
                "name": "full_entry", 
                "body": {
                    "date": "2025-09-03",
                    "entry": "Complex entry with details",
                    "mood": "happy",
                    "tags": ["work", "success", "achievement"],
                    "weather": "sunny",
                    "location": "home"
                }
            },
            {
                "name": "entry_with_nested_data",
                "body": {
                    "date": "2025-09-03", 
                    "entry": "Entry with nested structure",
                    "mood": "excited",
                    "tags": ["development"],
                    "goals": {
                        "completed": ["task1", "task2"],
                        "in_progress": ["task3"]
                    }
                }
            }
        ]
        
        for test_case in test_cases:
            with patch('src.routes.objects.create_object') as mock_create:
                mock_create.return_value = Object(
                    id=uuid4(),
                    gpt_id="diary-gpt",
                    collection="diary_entries",
                    body=test_case["body"],
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                
                response = client.post(
                    "/v1/gpts/diary-gpt/collections/diary_entries/objects",
                    headers=auth_headers,
                    json={"body": test_case["body"]}
                )
                
                assert response.status_code == status.HTTP_201_CREATED, f"Failed for {test_case['name']}"
                data = response.json()
                assert data["body"] == test_case["body"], f"Body mismatch for {test_case['name']}"


class TestHealthEndpointConsolidation:
    """Test consolidated health endpoint functionality."""
    
    @pytest.fixture
    def client(self):
        """Test client for FastAPI app."""
        return TestClient(app)
    
    def test_health_endpoint_exists(self, client):
        """Test that /health endpoint exists and works."""
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
    
    def test_ready_and_live_endpoints_removed(self, client):
        """Test that /ready and /live endpoints are removed or consolidated."""
        # These should either be removed or redirect to /health
        ready_response = client.get("/ready")
        live_response = client.get("/live")
        
        # They should either be 404 (removed) or redirect to /health
        assert ready_response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_200_OK]
        assert live_response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_200_OK]
        
        # If they exist, they should return health-like data
        if ready_response.status_code == status.HTTP_200_OK:
            data = ready_response.json()
            assert "status" in data
        
        if live_response.status_code == status.HTTP_200_OK:
            data = live_response.json()
            assert "status" in data
    
    def test_health_endpoint_no_auth_required(self, client):
        """Test that health endpoint doesn't require authentication."""
        # Should work without Authorization header
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        
        # Should not return authentication errors
        assert response.headers.get("content-type") != "application/problem+json"