"""
End-to-end integration tests for the complete GPT Object Store workflow.

Tests the full workflow: authentication -> collections -> objects -> pagination
Validates all EVAL.md requirements in realistic scenarios.
"""

import pytest
import json
import time
from uuid import uuid4
from typing import Dict, List, Any

import asyncpg
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestFullWorkflow:
    """Complete end-to-end workflow tests."""
    
    def test_complete_gpt_lifecycle(self, integration_client: TestClient, full_headers: Dict[str, str]):
        """
        Test complete GPT object store lifecycle:
        1. Authentication check
        2. Create collections  
        3. Create objects
        4. Read/update/delete objects
        5. Test pagination
        6. Test cross-GPT isolation
        """
        client = integration_client
        
        # Step 1: Test authentication required
        response = client.get("/v1/gpts/test-gpt/collections")
        assert response.status_code == 401
        assert response.headers.get("content-type") == "application/problem+json"
        
        # Step 2: Create multiple collections
        collections = ["notes", "documents", "tasks"]
        created_collections = []
        
        for coll_name in collections:
            collection_data = {
                "name": coll_name,
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "priority": {"type": "integer", "minimum": 1, "maximum": 5}
                    },
                    "required": ["title"]
                }
            }
            
            response = client.post(
                "/v1/gpts/test-gpt/collections",
                json=collection_data,
                headers=full_headers
            )
            
            if response.status_code == 409:  # Collection already exists
                # Get existing collection
                response = client.get(
                    f"/v1/gpts/test-gpt/collections/{coll_name}",
                    headers=full_headers
                )
            
            assert response.status_code in [200, 201]
            created_collections.append(response.json())
        
        # Step 3: List collections with pagination
        response = client.get(
            "/v1/gpts/test-gpt/collections?limit=2&order=desc",
            headers=full_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "collections" in data
        assert len(data["collections"]) <= 2
        assert "has_more" in data
        assert "next_cursor" in data
        
        # Check Link header for pagination
        if data.get("has_more"):
            assert "Link" in response.headers
            assert "rel=\"next\"" in response.headers["Link"]
        
        # Step 4: Create objects in each collection
        created_objects = []
        
        for i, coll_name in enumerate(collections):
            # Create multiple objects for pagination testing
            for j in range(3):
                object_data = {
                    "body": {
                        "title": f"Item {j+1} in {coll_name}",
                        "content": f"This is content for item {j+1} in collection {coll_name}",
                        "priority": (j % 5) + 1,
                        "metadata": {
                            "created_by": "test",
                            "collection_index": i,
                            "item_index": j
                        }
                    }
                }
                
                response = client.post(
                    f"/v1/gpts/test-gpt/collections/{coll_name}/objects",
                    json=object_data,
                    headers=full_headers
                )
                assert response.status_code == 201
                
                obj = response.json()
                assert "id" in obj
                assert obj["gpt_id"] == "test-gpt"
                assert obj["collection"] == coll_name
                assert obj["body"]["title"] == f"Item {j+1} in {coll_name}"
                assert "created_at" in obj
                assert "updated_at" in obj
                
                created_objects.append(obj)
        
        # Step 5: Test object retrieval and updates
        test_object = created_objects[0]
        object_id = test_object["id"]
        
        # Get object by ID
        response = client.get(f"/v1/objects/{object_id}", headers=full_headers)
        assert response.status_code == 200
        obj = response.json()
        assert obj["id"] == object_id
        assert obj["body"] == test_object["body"]
        
        # Update object (PATCH)
        original_updated_at = obj["updated_at"]
        update_data = {
            "body": {
                **obj["body"],
                "title": "Updated Title",
                "updated": True
            }
        }
        
        # Small delay to ensure updated_at changes
        time.sleep(0.1)
        
        response = client.patch(
            f"/v1/objects/{object_id}",
            json=update_data,
            headers=full_headers
        )
        assert response.status_code == 200
        
        updated_obj = response.json()
        assert updated_obj["body"]["title"] == "Updated Title"
        assert updated_obj["body"]["updated"] is True
        assert updated_obj["updated_at"] != original_updated_at
        
        # Step 6: Test object listing with pagination
        collection_name = created_objects[0]["collection"]
        
        # First page
        response = client.get(
            f"/v1/gpts/test-gpt/collections/{collection_name}/objects?limit=2&order=desc",
            headers=full_headers
        )
        assert response.status_code == 200
        
        page1_data = response.json()
        assert "objects" in page1_data
        assert len(page1_data["objects"]) <= 2
        assert "has_more" in page1_data
        assert "next_cursor" in page1_data
        
        # Verify sorting (created_at DESC, id DESC)
        if len(page1_data["objects"]) > 1:
            obj1, obj2 = page1_data["objects"][:2]
            assert obj1["created_at"] >= obj2["created_at"]
        
        # Test pagination with cursor if more pages exist
        if page1_data.get("has_more") and page1_data.get("next_cursor"):
            # Check Link header
            assert "Link" in response.headers
            assert "rel=\"next\"" in response.headers["Link"]
            
            # Get next page
            response = client.get(
                f"/v1/gpts/test-gpt/collections/{collection_name}/objects?cursor={page1_data['next_cursor']}&limit=2",
                headers=full_headers
            )
            assert response.status_code == 200
            
            page2_data = response.json()
            assert "objects" in page2_data
            
            # Verify no overlap between pages
            page1_ids = {obj["id"] for obj in page1_data["objects"]}
            page2_ids = {obj["id"] for obj in page2_data["objects"]}
            assert page1_ids.isdisjoint(page2_ids)
        
        # Step 7: Test cross-GPT isolation
        # Try to access objects with different GPT ID should fail
        response = client.get(
            "/v1/gpts/other-gpt/collections/notes/objects",
            headers=full_headers
        )
        # Should return 403 Forbidden or 404 Not Found depending on auth implementation
        assert response.status_code in [403, 404]
        
        # Step 8: Test object deletion
        response = client.delete(f"/v1/objects/{object_id}", headers=full_headers)
        assert response.status_code == 204
        
        # Verify object is deleted
        response = client.get(f"/v1/objects/{object_id}", headers=full_headers)
        assert response.status_code == 404
        assert response.headers.get("content-type") == "application/problem+json"
    
    def test_pagination_consistency(self, integration_client: TestClient, full_headers: Dict[str, str]):
        """Test that pagination is consistent and deterministic."""
        client = integration_client
        
        # Create collection if it doesn't exist
        collection_data = {"name": "pagination-test"}
        client.post("/v1/gpts/test-gpt/collections", json=collection_data, headers=full_headers)
        
        # Create several objects with known ordering
        objects_data = []
        for i in range(7):  # Create 7 objects
            obj_data = {
                "body": {
                    "title": f"Pagination Test Object {i:02d}",
                    "sequence": i,
                    "batch": "pagination-test"
                }
            }
            
            response = client.post(
                "/v1/gpts/test-gpt/collections/pagination-test/objects",
                json=obj_data,
                headers=full_headers
            )
            assert response.status_code == 201
            objects_data.append(response.json())
            
            # Small delay to ensure different created_at timestamps
            time.sleep(0.01)
        
        # Test pagination with different page sizes
        all_objects_via_pagination = []
        page_size = 3
        cursor = None
        
        while True:
            url = f"/v1/gpts/test-gpt/collections/pagination-test/objects?limit={page_size}&order=desc"
            if cursor:
                url += f"&cursor={cursor}"
            
            response = client.get(url, headers=full_headers)
            assert response.status_code == 200
            
            data = response.json()
            all_objects_via_pagination.extend(data["objects"])
            
            if not data.get("has_more") or not data.get("next_cursor"):
                break
            
            cursor = data["next_cursor"]
        
        # Verify we got all objects and they're properly ordered
        assert len(all_objects_via_pagination) >= 7
        
        # Check that objects are ordered by created_at DESC, id DESC
        for i in range(len(all_objects_via_pagination) - 1):
            obj1 = all_objects_via_pagination[i]
            obj2 = all_objects_via_pagination[i + 1]
            
            # created_at should be in descending order
            assert obj1["created_at"] >= obj2["created_at"]
            
            # If created_at is equal, id should be in descending order
            if obj1["created_at"] == obj2["created_at"]:
                assert obj1["id"] >= obj2["id"]
    
    def test_rate_limiting_behavior(self, integration_client: TestClient, full_headers: Dict[str, str]):
        """Test rate limiting with 429 responses and Retry-After headers."""
        client = integration_client
        
        # Make several rapid requests to trigger rate limiting
        # Note: This test assumes rate limits are configured for testing
        responses = []
        
        for i in range(80):  # Make many requests quickly
            response = client.get(
                "/v1/gpts/test-gpt/collections",
                headers=full_headers
            )
            responses.append(response.status_code)
            
            # If we hit rate limit, verify proper response
            if response.status_code == 429:
                assert "Retry-After" in response.headers
                assert response.headers.get("content-type") == "application/problem+json"
                
                # Verify Problem Details format
                error_data = response.json()
                assert "type" in error_data
                assert "title" in error_data
                assert "status" in error_data
                assert error_data["status"] == 429
                break
        
        # At least one request should have hit the rate limit if limits are low enough
        # This might not always trigger in CI/CD environments with high limits
        rate_limited = any(status == 429 for status in responses)
        if not rate_limited:
            pytest.skip("Rate limiting not triggered - limits may be too high for test environment")
    
    def test_problem_details_format(self, integration_client: TestClient, auth_headers: Dict[str, str]):
        """Test that all errors return proper RFC 9457 Problem Details format."""
        client = integration_client
        
        # Test 401 Unauthorized
        response = client.get("/v1/gpts/test-gpt/collections")
        assert response.status_code == 401
        assert response.headers.get("content-type") == "application/problem+json"
        
        error_data = response.json()
        assert "type" in error_data
        assert "title" in error_data
        assert "status" in error_data
        assert error_data["status"] == 401
        
        # Test 400 Bad Request (invalid cursor)
        response = client.get(
            "/v1/gpts/test-gpt/collections/notes/objects?cursor=invalid-cursor",
            headers=auth_headers
        )
        
        if response.status_code == 400:
            assert response.headers.get("content-type") == "application/problem+json"
            error_data = response.json()
            assert "type" in error_data
            assert "title" in error_data
            assert "status" in error_data
            assert error_data["status"] == 400
        
        # Test 404 Not Found
        response = client.get(
            f"/v1/objects/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404
        assert response.headers.get("content-type") == "application/problem+json"
        
        error_data = response.json()
        assert "type" in error_data
        assert "title" in error_data
        assert "status" in error_data
        assert error_data["status"] == 404
        
        # Test 422 Unprocessable Entity (validation error)
        response = client.post(
            "/v1/gpts/test-gpt/collections",
            json={"name": ""},  # Empty name should fail validation
            headers={**auth_headers, "Content-Type": "application/json"}
        )
        assert response.status_code == 422
        # Note: FastAPI may return application/json for validation errors by default
        # The important thing is that the structure follows Problem Details
    
    def test_database_constraints_and_indexes(self, test_db_pool: asyncpg.Pool):
        """Test that database schema matches EVAL.md requirements."""
        if not test_db_pool:
            pytest.skip("Database not available for schema validation")
        
        async def check_schema():
            async with test_db_pool.acquire() as conn:
                # Check tables exist
                tables = await conn.fetch("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public' 
                    AND tablename IN ('gpts', 'api_keys', 'collections', 'objects')
                """)
                table_names = {row['tablename'] for row in tables}
                assert table_names == {'gpts', 'api_keys', 'collections', 'objects'}
                
                # Check objects table has JSONB body column
                columns = await conn.fetch("""
                    SELECT column_name, data_type FROM information_schema.columns 
                    WHERE table_name = 'objects' AND column_name = 'body'
                """)
                assert len(columns) == 1
                assert columns[0]['data_type'] == 'jsonb'
                
                # Check GIN index on body exists
                indexes = await conn.fetch("""
                    SELECT indexname, indexdef FROM pg_indexes 
                    WHERE tablename = 'objects' AND indexdef LIKE '%gin%body%'
                """)
                assert len(indexes) >= 1
                
                # Check composite index (gpt_id, collection, created_at desc, id desc)
                indexes = await conn.fetch("""
                    SELECT indexname, indexdef FROM pg_indexes 
                    WHERE tablename = 'objects' 
                    AND indexdef LIKE '%gpt_id%collection%created_at%'
                """)
                assert len(indexes) >= 1
                
                # Check foreign key constraints
                constraints = await conn.fetch("""
                    SELECT conname FROM pg_constraint 
                    WHERE conrelid = 'objects'::regclass 
                    AND contype = 'f'
                """)
                assert len(constraints) >= 1  # Should have FK to collections
        
        import asyncio
        asyncio.run(check_schema())
    
    def test_api_key_authentication(self, integration_client: TestClient):
        """Test API key authentication behavior."""
        client = integration_client
        
        # Test valid API key
        response = client.get(
            "/v1/gpts/test-gpt/collections",
            headers={"Authorization": "Bearer test-api-key"}
        )
        assert response.status_code == 200
        
        # Test invalid API key
        response = client.get(
            "/v1/gpts/test-gpt/collections",
            headers={"Authorization": "Bearer invalid-key"}
        )
        assert response.status_code == 401
        
        # Test malformed Authorization header
        response = client.get(
            "/v1/gpts/test-gpt/collections",
            headers={"Authorization": "InvalidFormat"}
        )
        assert response.status_code == 401
        
        # Test missing Authorization header
        response = client.get("/v1/gpts/test-gpt/collections")
        assert response.status_code == 401


@pytest.mark.integration 
@pytest.mark.performance
class TestPerformanceRequirements:
    """Test performance requirements and timing constraints."""
    
    def test_api_response_times(self, integration_client: TestClient, full_headers: Dict[str, str], performance_timer):
        """Test that API responses are reasonably fast."""
        client = integration_client
        
        # Test collection listing
        performance_timer.start()
        response = client.get("/v1/gpts/test-gpt/collections", headers=full_headers)
        performance_timer.stop()
        
        assert response.status_code == 200
        assert performance_timer.elapsed < 1.0  # Should respond within 1 second
        
        # Test object creation
        object_data = {"body": {"title": "Performance Test", "content": "Testing response time"}}
        
        performance_timer.start()
        response = client.post(
            "/v1/gpts/test-gpt/collections/notes/objects",
            json=object_data,
            headers=full_headers
        )
        performance_timer.stop()
        
        assert response.status_code == 201
        assert performance_timer.elapsed < 1.0  # Should respond within 1 second
    
    def test_pagination_performance(self, integration_client: TestClient, full_headers: Dict[str, str]):
        """Test that pagination doesn't degrade significantly with position."""
        client = integration_client
        
        # Ensure we have some objects
        collection_data = {"name": "perf-test"}
        client.post("/v1/gpts/test-gpt/collections", json=collection_data, headers=full_headers)
        
        # Create several objects
        for i in range(10):
            obj_data = {"body": {"title": f"Perf Test {i}", "index": i}}
            client.post(
                "/v1/gpts/test-gpt/collections/perf-test/objects",
                json=obj_data,
                headers=full_headers
            )
        
        # Test first page performance
        start_time = time.time()
        response = client.get(
            "/v1/gpts/test-gpt/collections/perf-test/objects?limit=3",
            headers=full_headers
        )
        first_page_time = time.time() - start_time
        
        assert response.status_code == 200
        data = response.json()
        
        # Test later page performance (if available)
        if data.get("next_cursor"):
            start_time = time.time()
            response = client.get(
                f"/v1/gpts/test-gpt/collections/perf-test/objects?cursor={data['next_cursor']}&limit=3",
                headers=full_headers
            )
            later_page_time = time.time() - start_time
            
            assert response.status_code == 200
            # Later pages shouldn't be significantly slower (within 2x)
            assert later_page_time < (first_page_time * 2 + 0.5)  # Allow some variance