#!/usr/bin/env python3
"""Test script for collection creation and object saving with correct schema."""

import json
import subprocess
import sys

def run_curl_command(description, command):
    """Run a curl command and display results."""
    print(f"\n{'='*60}")
    print(f"TEST: {description}")
    print(f"{'='*60}")
    print(f"Command: {command}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        print(f"Exit Code: {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        print(f"Error running command: {e}")
        return False, "", str(e)

def main():
    # Configuration
    API_KEY = "y8DdqMVDC9Z9yNCxLcpnAy4tjB3g8Tt-fS8xGNcxYrE"
    BASE_URL = "https://gpt-backend.w22.io"
    GPT_ID = "diary-gpt"
    
    print("Testing Collection Creation and Object Saving Flow")
    print(f"Base URL: {BASE_URL}")
    print(f"GPT ID: {GPT_ID}")
    
    # Test 1: Create collection with correct field name
    collection_data = {
        "name": "diary_entries",
        "schema": {  # Using "schema" not "collection_schema"
            "type": "object",
            "properties": {
                "date": {"type": "string", "format": "date"},
                "entry": {"type": "string"},
                "mood": {"type": "string", "enum": ["happy", "sad", "neutral", "excited", "anxious"]},
                "tags": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["date", "entry"]
        }
    }
    
    create_collection_cmd = f'''curl -X POST "{BASE_URL}/v1/gpts/{GPT_ID}/collections" \\
  -H "Authorization: Bearer {API_KEY}" \\
  -H "Content-Type: application/json" \\
  -d '{json.dumps(collection_data, separators=(",", ":"))}'  \\
  -w "\\nHTTP_CODE: %{{http_code}}\\n"'''
    
    success, stdout, stderr = run_curl_command("Create Collection with Correct Schema Field", create_collection_cmd)
    
    # Test 2: List collections to verify creation
    list_collections_cmd = f'''curl -X GET "{BASE_URL}/v1/gpts/{GPT_ID}/collections" \\
  -H "Authorization: Bearer {API_KEY}" \\
  -w "\\nHTTP_CODE: %{{http_code}}\\n"'''
    
    run_curl_command("List Collections", list_collections_cmd)
    
    # Test 3: Create object with proper body wrapper
    object_data = {
        "body": {  # Proper body wrapper
            "date": "2025-09-03",
            "entry": "This is a test diary entry to verify the API works correctly",
            "mood": "neutral",
            "tags": ["testing", "api", "debugging"]
        }
    }
    
    create_object_cmd = f'''curl -X POST "{BASE_URL}/v1/gpts/{GPT_ID}/collections/diary_entries/objects" \\
  -H "Authorization: Bearer {API_KEY}" \\
  -H "Content-Type: application/json" \\
  -d '{json.dumps(object_data, separators=(",", ":"))}'  \\
  -w "\\nHTTP_CODE: %{{http_code}}\\n"'''
    
    run_curl_command("Create Object with Body Wrapper", create_object_cmd)
    
    # Test 4: Test what happens with incorrect structure (no body wrapper)
    incorrect_object_data = {
        "date": "2025-09-03",
        "entry": "This should fail - no body wrapper",
        "mood": "neutral",
        "tags": ["testing", "failure"]
    }
    
    create_incorrect_object_cmd = f'''curl -X POST "{BASE_URL}/v1/gpts/{GPT_ID}/collections/diary_entries/objects" \\
  -H "Authorization: Bearer {API_KEY}" \\
  -H "Content-Type: application/json" \\
  -d '{json.dumps(incorrect_object_data, separators=(",", ":"))}'  \\
  -w "\\nHTTP_CODE: %{{http_code}}\\n"'''
    
    run_curl_command("Create Object WITHOUT Body Wrapper (Should Fail)", create_incorrect_object_cmd)
    
    # Test 5: List objects to see what was created
    list_objects_cmd = f'''curl -X GET "{BASE_URL}/v1/gpts/{GPT_ID}/collections/diary_entries/objects" \\
  -H "Authorization: Bearer {API_KEY}" \\
  -w "\\nHTTP_CODE: %{{http_code}}\\n"'''
    
    run_curl_command("List Objects", list_objects_cmd)

if __name__ == "__main__":
    main()