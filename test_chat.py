#!/usr/bin/env python3
"""
Simple test script for Butler chat functionality.
This script demonstrates how to interact with Butler's chat API endpoints.
"""

import json
import requests
import uuid
import sys
from typing import Dict, Any, Optional

# Configuration
BASE_URL = "http://localhost:8000"
API_V1_PREFIX = "/api/v1"

def test_synchronous_chat():
    """Test the synchronous chat endpoint."""
    print("=== Testing Synchronous Chat ===")
    
    url = f"{BASE_URL}{API_V1_PREFIX}/chat"
    
    # Generate a unique session ID for this test
    session_id = str(uuid.uuid4())
    
    payload = {
        "message": "Hello Butler! This is a test message.",
        "session_id": session_id,
        "stream": False,
        "attachments": [],
        "location": None,
        "mode": "auto"
    }
    
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            return data
        else:
            print(f"Error: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Butler backend. Make sure it's running on localhost:8000")
        return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def test_streaming_chat():
    """Test the streaming chat endpoint using Server-Sent Events."""
    print("\n=== Testing Streaming Chat (SSE) ===")
    
    url = f"{BASE_URL}{API_V1_PREFIX}/chat/stream"
    
    session_id = str(uuid.uuid4())
    
    payload = {
        "message": "Hello Butler! Please give me a short streaming response.",
        "session_id": session_id,
        "stream": True,
        "attachments": [],
        "location": None,
        "mode": "auto"
    }
    
    try:
        response = requests.post(url, json=payload, stream=True)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("Streaming response:")
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    print(f"  {decoded_line}")
                    
                    # Break when we see the done event
                    if "event: done" in decoded_line:
                        break
        else:
            print(f"Error: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Butler backend. Make sure it's running on localhost:8000")
    except Exception as e:
        print(f"Error: {str(e)}")

def test_health_endpoints():
    """Test the health check endpoints."""
    print("\n=== Testing Health Endpoints ===")
    
    endpoints = [
        "/health/live",
        "/health/ready", 
        "/health/startup"
    ]
    
    for endpoint in endpoints:
        url = f"{BASE_URL}{endpoint}"
        try:
            response = requests.get(url)
            print(f"{endpoint}: {response.status_code}")
            if response.status_code == 200:
                print(f"  Response: {response.json()}")
        except Exception as e:
            print(f"{endpoint}: Error - {str(e)}")

def main():
    """Main test function."""
    print("Butler Chat Test Script")
    print("=" * 50)
    
    # Test health endpoints first
    test_health_endpoints()
    
    # Test synchronous chat
    result = test_synchronous_chat()
    
    # Test streaming chat if sync worked
    if result:
        test_streaming_chat()
    else:
        print("\nSkipping streaming test due to connection error")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    main()