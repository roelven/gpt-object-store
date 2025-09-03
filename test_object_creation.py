#!/usr/bin/env python3
"""Test script for object creation endpoint."""

import json
import requests

# Use the API key we created earlier for diary-gpt
API_KEY = "6JDwEejvlf4tRzMqTbv7PTPwJkZo0xaLOsj705FvYWw"
BASE_URL = "http://localhost:8000"  # Local test first

def test_object_creation():
    """Test creating an object in the diary_entries collection."""
    
    # Test data - valid ObjectCreate format
    test_data = {
        "body": {
            "title": "Test Diary Entry",
            "content": "This is a test entry from the API test script",
            "date": "2025-09-03",
            "mood": "testing"
        }
    }
    
    # Headers
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # URL for diary-gpt collection
    url = f"{BASE_URL}/v1/gpts/diary-gpt/collections/diary_entries/objects"
    
    print(f"Testing POST to: {url}")
    print(f"Headers: {headers}")
    print(f"Body: {json.dumps(test_data, indent=2)}")
    
    try:
        response = requests.post(url, json=test_data, headers=headers)
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.content:
            try:
                response_data = response.json()
                print(f"Response Body: {json.dumps(response_data, indent=2)}")
            except json.JSONDecodeError:
                print(f"Response Body (raw): {response.text}")
        else:
            print("Response Body: (empty)")
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_object_creation()