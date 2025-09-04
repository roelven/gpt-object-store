#!/usr/bin/env python3
"""Local test script for collection creation and object saving."""

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
    # Configuration for local testing
    API_KEY = "vQXfBFLSjRBxtX1m1UgdtyefTSUMuXhhwDWj-gacuao"
    BASE_URL = "http://localhost:8000"
    GPT_ID = "diary-gpt"
    
    print("Testing Collection Creation and Object Saving Flow (LOCAL)")
    print(f"Base URL: {BASE_URL}")
    print(f"GPT ID: {GPT_ID}")
    
    # Test 1: Create collection with correct schema field
    collection_data = {
        "name": "diary_entries_local",
        "schema": {
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
  -d '{json.dumps(collection_data, separators=(",", ":"))}' \\
  -w "\\nHTTP_CODE: %{{http_code}}\\n"'''
    
    success, stdout, stderr = run_curl_command("Create Collection with Correct Schema Field (LOCAL)", create_collection_cmd)
    
    # Test 2: Create object with direct fields (new GPT Actions format)
    object_data = {
        "date": "2025-09-03",
        "entry": "Local test diary entry to verify the API works correctly",
        "mood": "neutral",
        "tags": ["testing", "api", "debugging", "local"]
    }
    
    create_object_cmd = f'''curl -X POST "{BASE_URL}/v1/gpts/{GPT_ID}/collections/diary_entries_local/objects" \\
  -H "Authorization: Bearer {API_KEY}" \\
  -H "Content-Type: application/json" \\
  -d '{json.dumps(object_data, separators=(",", ":"))}' \\
  -w "\\nHTTP_CODE: %{{http_code}}\\n"'''
    
    success, stdout, stderr = run_curl_command("Create Object with Direct Fields (LOCAL)", create_object_cmd)
    
    # Extract object ID from create response for update test
    object_id = None
    if success and "HTTP_CODE: 201" in stdout:
        try:
            # Find the JSON response before HTTP_CODE
            json_start = stdout.find('{"id"')
            json_end = stdout.find('\nHTTP_CODE:')
            if json_start != -1 and json_end != -1:
                json_str = stdout[json_start:json_end].strip()
                response_data = json.loads(json_str)
                object_id = response_data.get("id")
                print(f"Created object with ID: {object_id}")
        except Exception as e:
            print(f"Could not extract object ID: {e}")
    
    # Test 3: Update object entry field (the main test for GPT Actions compatibility)
    if object_id:
        update_data = {
            "entry": "UPDATED: Local test diary entry with new content to verify entry updates work",
            "mood": "excited",
            "tags": ["testing", "api", "debugging", "local", "updated"]
        }
        
        update_object_cmd = f'''curl -X PATCH "{BASE_URL}/v1/objects/{object_id}" \\
  -H "Authorization: Bearer {API_KEY}" \\
  -H "Content-Type: application/json" \\
  -d '{json.dumps(update_data, separators=(",", ":"))}' \\
  -w "\\nHTTP_CODE: %{{http_code}}\\n"'''
        
        run_curl_command("Update Object Entry Field (LOCAL)", update_object_cmd)
    else:
        print("Skipping update test - could not extract object ID from create response")
    
    # Test 4: List objects to see what was created and updated
    list_objects_cmd = f'''curl -X GET "{BASE_URL}/v1/gpts/{GPT_ID}/collections/diary_entries_local/objects" \\
  -H "Authorization: Bearer {API_KEY}" \\
  -w "\\nHTTP_CODE: %{{http_code}}\\n"'''
    
    run_curl_command("List Objects After Update (LOCAL)", list_objects_cmd)

if __name__ == "__main__":
    main()