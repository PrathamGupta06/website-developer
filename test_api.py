#!/usr/bin/env python3
"""
Simple test script for the Website Developer API
"""

import requests
import base64


def create_test_attachment():
    """Create a simple test image as base64 data URI."""
    # Simple 1x1 PNG image
    png_data = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\x12IDATx\x9cc```b\x00\x02\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode()
    return f"data:image/png;base64,{png_data}"


def test_api():
    """Test the API with a sample request."""

    test_request = {
        "email": "test@example.com",
        "secret": "default-secret",  # Using default secret
        "task": "test-captcha-solver-123",
        "round": 1,
        "nonce": "test-nonce-abc",
        "brief": "Create a captcha solver that handles ?url=https://.../image.png. Default to attached sample.",
        "checks": [
            "Repo has MIT license",
            "README.md is professional",
            "Page displays captcha URL passed at ?url=...",
            "Page displays solved captcha text within 15 seconds",
        ],
        "evaluation_url": "http://localhost:9000",  # Test endpoint
        "attachments": [{"name": "sample.png", "url": create_test_attachment()}],
    }

    try:
        print("Testing Website Developer API...")
        print("Sending POST request to /build endpoint...")

        response = requests.post(
            "http://localhost:8000/build",
            json=test_request,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {response.json()}")

        if response.status_code == 200:
            print("✅ API test successful!")
        else:
            print("❌ API test failed!")

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Make sure it's running on localhost:8000")
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")


def test_health():
    """Test the health endpoint."""
    try:
        response = requests.get("http://localhost:8000/health")
        print(f"Health check: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"Health check failed: {str(e)}")


if __name__ == "__main__":
    print("Website Developer API Test Suite")
    print("=" * 40)

    test_health()
    print()
    test_api()
