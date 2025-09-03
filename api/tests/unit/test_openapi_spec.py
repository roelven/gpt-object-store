"""Tests for OpenAPI specification validation."""

import pytest
import yaml
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from fastapi import FastAPI
from src.main import create_app, load_openapi_spec


class TestOpenAPISpecification:
    """Test suite for OpenAPI specification validation."""
    
    def test_openapi_file_exists(self):
        """Test that the OpenAPI specification file exists."""
        openapi_file = Path(__file__).parent.parent.parent / "openapi" / "gpt-object-store.yaml"
        assert openapi_file.exists(), f"OpenAPI specification file not found at {openapi_file}"
    
    def test_openapi_file_is_valid_yaml(self):
        """Test that the OpenAPI specification file is valid YAML."""
        openapi_file = Path(__file__).parent.parent.parent / "openapi" / "gpt-object-store.yaml"
        
        with open(openapi_file, 'r') as f:
            try:
                spec = yaml.safe_load(f)
                assert spec is not None, "OpenAPI spec should not be None"
                assert isinstance(spec, dict), "OpenAPI spec should be a dictionary"
            except yaml.YAMLError as e:
                pytest.fail(f"OpenAPI specification contains invalid YAML: {e}")
    
    def test_load_openapi_spec_function(self):
        """Test the load_openapi_spec function."""
        spec = load_openapi_spec()
        
        assert isinstance(spec, dict), "load_openapi_spec should return a dictionary"
        assert len(spec) > 0, "OpenAPI spec should not be empty"
    
    def test_openapi_spec_structure(self):
        """Test that the OpenAPI specification has the required structure."""
        spec = load_openapi_spec()
        
        # Required top-level fields
        assert "openapi" in spec, "OpenAPI spec must have 'openapi' field"
        assert "info" in spec, "OpenAPI spec must have 'info' field"
        assert "paths" in spec, "OpenAPI spec must have 'paths' field"
        
        # Check OpenAPI version
        assert spec["openapi"] == "3.1.0", "OpenAPI version should be 3.1.0"
        
        # Check info section
        info = spec["info"]
        assert "title" in info, "Info section must have 'title'"
        assert "version" in info, "Info section must have 'version'"
        assert "description" in info, "Info section must have 'description'"
        
        # Check expected title and version
        assert info["title"] == "GPT Object Store API"
        assert info["version"] == "1.0.0"
    
    def test_security_schemes(self):
        """Test that security schemes are properly defined."""
        spec = load_openapi_spec()
        
        assert "components" in spec, "OpenAPI spec must have 'components' field"
        assert "securitySchemes" in spec["components"], "Components must have 'securitySchemes'"
        
        security_schemes = spec["components"]["securitySchemes"]
        
        # Check API key security scheme
        assert "bearerApiKey" in security_schemes, "Must have bearerApiKey security scheme"
        api_key_scheme = security_schemes["bearerApiKey"]
        assert api_key_scheme["type"] == "http"
        assert api_key_scheme["scheme"] == "bearer"
        assert api_key_scheme["bearerFormat"] == "APIKey"
        
        # OAuth2 security scheme removed for GPT Actions compatibility
        # GPT Actions require single security scheme only
        assert "oauth2" not in security_schemes, "oauth2 security scheme should be removed for GPT Actions compatibility"
    
    def test_required_schemas(self):
        """Test that all required schemas are defined."""
        spec = load_openapi_spec()
        
        schemas = spec["components"]["schemas"]
        
        # Core data model schemas
        required_schemas = [
            "Collection", "CollectionCreate", "CollectionUpdate", "CollectionListResponse",
            "Object", "ObjectCreate", "ObjectUpdate", "ObjectListResponse",
            "ProblemDetail", "HealthStatus", "ReadinessStatus", "LivenessStatus", "RootInfo"
        ]
        
        for schema_name in required_schemas:
            assert schema_name in schemas, f"Schema '{schema_name}' must be defined"
    
    def test_collection_endpoints(self):
        """Test that all collection endpoints are defined."""
        spec = load_openapi_spec()
        
        paths = spec["paths"]
        
        # Collection endpoints (updated for v1 prefix)
        collection_base = "/v1/gpts/{gpt_id}/collections"
        collection_item = "/v1/gpts/{gpt_id}/collections/{collection_name}"
        
        assert collection_base in paths, f"Path {collection_base} must be defined"
        assert collection_item in paths, f"Path {collection_item} must be defined"
        
        # Check HTTP methods for collection base
        collection_base_methods = paths[collection_base]
        assert "get" in collection_base_methods, "Collections list endpoint must have GET method"
        assert "post" in collection_base_methods, "Collections endpoint must have POST method"
        
        # Check HTTP methods for collection item
        collection_item_methods = paths[collection_item]
        assert "get" in collection_item_methods, "Collection item must have GET method"
        assert "patch" in collection_item_methods, "Collection item must have PATCH method"
        assert "delete" in collection_item_methods, "Collection item must have DELETE method"
    
    def test_object_endpoints(self):
        """Test that all object endpoints are defined."""
        spec = load_openapi_spec()
        
        paths = spec["paths"]
        
        # Object endpoints (updated for v1 prefix)
        collection_objects = "/v1/gpts/{gpt_id}/collections/{collection_name}/objects"
        direct_object = "/v1/objects/{object_id}"
        
        assert collection_objects in paths, f"Path {collection_objects} must be defined"
        assert direct_object in paths, f"Path {direct_object} must be defined"
        
        # Check HTTP methods for collection objects
        collection_objects_methods = paths[collection_objects]
        assert "get" in collection_objects_methods, "Objects list endpoint must have GET method"
        assert "post" in collection_objects_methods, "Objects endpoint must have POST method"
        
        # Check HTTP methods for direct object access
        direct_object_methods = paths[direct_object]
        assert "get" in direct_object_methods, "Direct object access must have GET method"
        assert "patch" in direct_object_methods, "Direct object access must have PATCH method"
        assert "delete" in direct_object_methods, "Direct object access must have DELETE method"
    
    def test_health_endpoints(self):
        """Test that all health endpoints are defined."""
        spec = load_openapi_spec()
        
        paths = spec["paths"]
        
        # Health endpoints
        health_endpoints = ["/", "/health", "/ready", "/live"]
        
        for endpoint in health_endpoints:
            assert endpoint in paths, f"Health endpoint {endpoint} must be defined"
            assert "get" in paths[endpoint], f"Health endpoint {endpoint} must have GET method"
    
    def test_error_responses(self):
        """Test that error responses are properly defined."""
        spec = load_openapi_spec()
        
        responses = spec["components"]["responses"]
        
        # Check error response definitions
        error_responses = [
            "BadRequest", "Unauthorized", "Forbidden", "NotFound", 
            "Conflict", "UnprocessableEntity", "TooManyRequests", 
            "InternalServerError", "ServiceUnavailable"
        ]
        
        for error_response in error_responses:
            assert error_response in responses, f"Error response '{error_response}' must be defined"
            
            response_def = responses[error_response]
            assert "content" in response_def, f"Error response '{error_response}' must have content"
            assert "application/problem+json" in response_def["content"], \
                f"Error response '{error_response}' must use Problem Details format"
    
    def test_pagination_parameters(self):
        """Test that pagination parameters are properly defined."""
        spec = load_openapi_spec()
        
        parameters = spec["components"]["parameters"]
        
        # Check pagination parameters
        pagination_params = ["Limit", "Cursor", "Order"]
        
        for param in pagination_params:
            assert param in parameters, f"Pagination parameter '{param}' must be defined"
            
            param_def = parameters[param]
            assert "in" in param_def, f"Parameter '{param}' must specify location"
            assert param_def["in"] == "query", f"Pagination parameter '{param}' must be in query"
    
    def test_app_uses_custom_openapi_spec(self):
        """Test that the app correctly loads and uses the custom OpenAPI specification."""
        # This test validates that load_openapi_spec returns our custom spec
        # and that it would be used by the app
        spec = load_openapi_spec()
        
        # Verify it's our custom specification
        assert spec["openapi"] == "3.1.0"
        assert spec["info"]["title"] == "GPT Object Store API"
        assert spec["info"]["version"] == "1.0.0"
        
        # Verify key components are present
        assert "components" in spec
        assert "securitySchemes" in spec["components"]
        assert "bearerApiKey" in spec["components"]["securitySchemes"]
        # oauth2 removed for GPT Actions compatibility
        
        # Verify paths are present (updated for v1 prefix)
        assert "paths" in spec
        assert "/v1/gpts/{gpt_id}/collections" in spec["paths"]
        assert "/v1/objects/{object_id}" in spec["paths"]
    
    def test_openapi_spec_has_correct_structure_for_gpt_actions(self):
        """Test that the OpenAPI spec is structured correctly for GPT Actions."""
        spec = load_openapi_spec()
        
        # GPT Actions compatibility checks
        assert spec["openapi"].startswith("3."), "GPT Actions require OpenAPI 3.x"
        
        # Check required metadata
        info = spec["info"]
        assert len(info["title"]) > 0, "Title must not be empty"
        assert len(info["description"]) > 0, "Description must not be empty"
        assert len(info["version"]) > 0, "Version must not be empty"
        
        # Check servers (GPT Actions use server URLs)
        assert "servers" in spec, "Servers must be defined for GPT Actions"
        assert len(spec["servers"]) > 0, "At least one server must be defined"
        
        # Check that each server has a URL
        for server in spec["servers"]:
            assert "url" in server, "Each server must have a URL"
            assert len(server["url"]) > 0, "Server URL must not be empty"
    
    def test_server_url_structure_for_gpt_actions(self):
        """Test that server URL is structured correctly for GPT Actions."""
        spec = load_openapi_spec()
        
        # Check servers configuration
        assert "servers" in spec, "Servers must be defined"
        assert len(spec["servers"]) == 1, "Should have exactly one server for GPT Actions compatibility"
        
        server = spec["servers"][0]
        server_url = server["url"]
        
        # Server URL should NOT include /v1 (paths include it instead)
        assert not server_url.endswith("/v1"), \
            "Server URL should not end with /v1 - paths should include the version prefix instead"
        assert "/v1" not in server_url, \
            "Server URL should not contain /v1 anywhere - version prefix moved to individual paths"
        
        # Should be a valid URL format
        assert server_url.startswith(("http://", "https://")), \
            "Server URL should start with http:// or https://"
    
    def test_operation_ids_unique(self):
        """Test that all operation IDs are unique across the specification."""
        spec = load_openapi_spec()
        
        operation_ids = []
        paths = spec["paths"]
        
        for path, methods in paths.items():
            for method, operation in methods.items():
                if isinstance(operation, dict) and "operationId" in operation:
                    operation_ids.append(operation["operationId"])
        
        # Check for duplicates
        unique_operation_ids = set(operation_ids)
        assert len(operation_ids) == len(unique_operation_ids), \
            f"Operation IDs must be unique. Duplicates found: {[oid for oid in operation_ids if operation_ids.count(oid) > 1]}"
    
    def test_gpt_actions_compatibility(self):
        """Test that the specification is compatible with GPT Actions requirements."""
        spec = load_openapi_spec()
        
        # GPT Actions require OpenAPI 3.0+ 
        openapi_version = spec["openapi"]
        major_version = int(openapi_version.split('.')[0])
        assert major_version >= 3, "GPT Actions require OpenAPI 3.0 or higher"
        
        # Must have security schemes defined
        assert "components" in spec
        assert "securitySchemes" in spec["components"]
        
        # Should have API key security scheme for GPT Actions (oauth2 removed for compatibility)
        security_schemes = spec["components"]["securitySchemes"]
        assert "bearerApiKey" in security_schemes, \
            "Must have bearerApiKey security scheme for GPT Actions"
        assert "oauth2" not in security_schemes, \
            "oauth2 security scheme should be removed for GPT Actions single-scheme requirement"
        
        # All protected endpoints should specify security requirements
        paths = spec["paths"]
        for path, methods in paths.items():
            for method, operation in methods.items():
                if isinstance(operation, dict):
                    # Health endpoints and root can be public
                    if path in ["/", "/health", "/ready", "/live"]:
                        continue
                    
                    # All other endpoints should have security or inherit from global security
                    has_security = "security" in operation or "security" in spec
                    assert has_security, f"Endpoint {method.upper()} {path} should specify security requirements"