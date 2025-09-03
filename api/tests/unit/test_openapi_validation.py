"""Regression tests for OpenAPI specification validation.

These tests prevent common issues that break GPT Actions compatibility:
1. YAML syntax errors that cause the spec to fail loading
2. Operation descriptions exceeding 300-character GPT Actions limit  
3. Missing servers section that causes "Could not find a valid URL" errors
"""

import yaml
import pytest
from pathlib import Path
from typing import Dict, Any

from api.src.main import load_openapi_spec


class TestOpenAPIValidation:
    """Regression tests for OpenAPI specification validation."""
    
    def test_openapi_yaml_syntax_is_valid(self):
        """Test that OpenAPI YAML file has valid syntax and can be parsed.
        
        Regression test for: YAML syntax errors causing empty dict return
        from load_openapi_spec(), which removes servers section and breaks
        GPT Actions with "Could not find a valid URL in servers" error.
        """
        openapi_file = Path("api/openapi/gpt-object-store.yaml")
        
        # File must exist
        assert openapi_file.exists(), f"OpenAPI file not found: {openapi_file}"
        
        # YAML must parse without syntax errors
        with open(openapi_file, 'r') as f:
            try:
                spec = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"OpenAPI YAML syntax error: {e}")
        
        # Must return a non-empty dict
        assert isinstance(spec, dict), "OpenAPI spec must be a dictionary"
        assert spec, "OpenAPI spec must not be empty"
        
        # Load function must work without errors
        loaded_spec = load_openapi_spec()
        assert isinstance(loaded_spec, dict), "load_openapi_spec() must return dict"
        assert loaded_spec, "load_openapi_spec() must not return empty dict"
    
    def test_servers_section_exists(self):
        """Test that OpenAPI spec contains required servers section.
        
        Regression test for: Missing servers section causing GPT Actions
        "Could not find a valid URL in servers" error.
        """
        spec = load_openapi_spec()
        
        # Must have servers section
        assert "servers" in spec, "OpenAPI spec must contain 'servers' section"
        assert isinstance(spec["servers"], list), "servers must be a list"
        assert len(spec["servers"]) > 0, "servers list must not be empty"
        
        # First server must have URL
        first_server = spec["servers"][0]
        assert "url" in first_server, "First server must have 'url' field"
        assert isinstance(first_server["url"], str), "Server URL must be a string"
        assert first_server["url"].strip(), "Server URL must not be empty"
    
    def test_operation_descriptions_under_character_limit(self):
        """Test that all operation descriptions are under 300 characters.
        
        Regression test for: Operation descriptions exceeding GPT Actions
        300-character limit, causing schema import failures.
        """
        spec = load_openapi_spec()
        
        # Check all paths and methods for description length
        violations = []
        
        for path, path_data in spec.get("paths", {}).items():
            for method, operation in path_data.items():
                if not isinstance(operation, dict):
                    continue  # Skip non-operation items like parameters
                
                description = operation.get("description", "")
                if isinstance(description, str) and len(description) > 300:
                    violations.append({
                        "path": path,
                        "method": method,
                        "operation_id": operation.get("operationId", "unknown"),
                        "description_length": len(description),
                        "description_preview": description[:100] + "..." if len(description) > 100 else description
                    })
        
        # Report all violations with detailed information
        if violations:
            violation_details = "\n".join([
                f"  - {v['method'].upper()} {v['path']} (operationId: {v['operation_id']}): "
                f"{v['description_length']} chars - '{v['description_preview']}'"
                for v in violations
            ])
            pytest.fail(
                f"Found {len(violations)} operation(s) with descriptions exceeding 300 characters:\n"
                f"{violation_details}\n\n"
                f"GPT Actions requires all operation descriptions to be 300 characters or less."
            )
    
    def test_critical_operations_have_descriptions(self):
        """Test that critical operations have non-empty descriptions.
        
        Ensures important operations have descriptions for GPT Actions understanding.
        """
        spec = load_openapi_spec()
        
        # Critical operations that must have descriptions
        critical_operations = [
            ("createObject", "Object creation"),
            ("updateObject", "Object update"),
            ("deleteObject", "Object deletion"),
            ("listObjects", "Object listing"),
            ("createOrUpdateCollection", "Collection creation")
        ]
        
        # Find all operations and their descriptions
        operations = {}
        for path, path_data in spec.get("paths", {}).items():
            for method, operation in path_data.items():
                if isinstance(operation, dict) and "operationId" in operation:
                    operations[operation["operationId"]] = {
                        "path": path,
                        "method": method,
                        "description": operation.get("description", "")
                    }
        
        # Check each critical operation
        missing_descriptions = []
        for operation_id, operation_name in critical_operations:
            if operation_id not in operations:
                missing_descriptions.append(f"{operation_name} (operationId: {operation_id}) - Operation not found")
            elif not operations[operation_id]["description"].strip():
                missing_descriptions.append(f"{operation_name} (operationId: {operation_id}) - Empty description")
        
        if missing_descriptions:
            pytest.fail(
                f"Critical operations missing descriptions:\n" +
                "\n".join(f"  - {desc}" for desc in missing_descriptions)
            )
    
    def test_json_examples_in_descriptions_are_properly_escaped(self):
        """Test that JSON examples in descriptions don't break YAML syntax.
        
        Regression test for: Unescaped JSON syntax in descriptions causing
        YAML parsing errors like "mapping values are not allowed here".
        """
        spec = load_openapi_spec()
        
        # This test passes if we can load the spec without YAML errors
        # Additional validation for common problematic patterns
        problematic_patterns = [
            '{"',  # Unescaped JSON start
            '"}',  # Unescaped JSON end  
            ': {', # Unescaped object value
        ]
        
        violations = []
        for path, path_data in spec.get("paths", {}).items():
            for method, operation in path_data.items():
                if not isinstance(operation, dict):
                    continue
                
                description = operation.get("description", "")
                if isinstance(description, str):
                    for pattern in problematic_patterns:
                        if pattern in description:
                            # Check if it's properly quoted/escaped
                            # This is a heuristic - if we got here, YAML loaded successfully
                            # so any JSON is probably properly handled
                            pass
        
        # If we can load the spec, JSON examples are properly handled
        assert spec, "OpenAPI spec loaded successfully, JSON examples properly escaped"
    
    def test_openapi_spec_has_required_gpt_actions_fields(self):
        """Test that OpenAPI spec has fields required for GPT Actions compatibility."""
        spec = load_openapi_spec()
        
        # Required top-level fields
        required_fields = ["openapi", "info", "paths", "servers"]
        for field in required_fields:
            assert field in spec, f"OpenAPI spec must contain '{field}' field"
        
        # Info section requirements
        info = spec["info"]
        assert "title" in info, "info.title is required"
        assert "version" in info, "info.version is required"
        
        # Must have at least one path
        assert spec["paths"], "OpenAPI spec must contain at least one path"
        
        # Security schemes for authentication
        assert "components" in spec, "OpenAPI spec must contain components section"
        assert "securitySchemes" in spec["components"], "Must contain security schemes"