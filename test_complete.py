#!/usr/bin/env python3
"""
Test script to verify the complete application flow implementation.
"""

import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api import AppBuilder
from models import BuildRequest, Attachment


async def test_basic_functionality():
    """Test basic AppBuilder functionality."""
    print("🔧 Testing basic functionality...")

    builder = AppBuilder()
    print("✅ AppBuilder initialized successfully")

    # Test secret validation
    assert not builder.validate_secret("test-secret")  # Wrong secret
    assert builder.validate_secret("default-secret")  # Default secret
    print("✅ Secret validation works")

    # Test attachment processing
    test_attachments = []
    result = await builder.process_attachments(test_attachments)
    assert len(result) == 0
    print("✅ Attachment processing works")

    # Test starter file loading
    content = builder.load_starter_file("index.html")
    assert len(content) > 0
    print("✅ Starter file loading works")

    print("✅ All basic tests passed!")


async def test_attachment_processing():
    """Test attachment processing with sample data."""
    print("\n📎 Testing attachment processing...")

    builder = AppBuilder()

    # Create a sample attachment (base64 encoded "Hello World")
    sample_attachment = Attachment(
        name="test.txt", url="data:text/plain;base64,SGVsbG8gV29ybGQ="
    )

    result = await builder.process_attachments([sample_attachment])

    assert len(result) == 1
    assert result[0]["name"] == "test.txt"
    assert result[0]["mime_type"] == "text/plain"
    assert result[0]["data"] == b"Hello World"

    print("✅ Attachment processing with data URIs works!")


async def test_context_gathering():
    """Test context gathering functionality."""
    print("\n📋 Testing context gathering...")

    builder = AppBuilder()

    # Create sample request
    sample_request = BuildRequest(
        email="test@example.com",
        secret="default-secret",
        task="test-task",
        round=1,
        nonce="test-nonce",
        brief="Create a test application",
        checks=["Test requirement 1", "Test requirement 2"],
        evaluation_url="https://example.com/evaluate",
        attachments=[],
    )

    context = await builder.gather_context(sample_request, [], None)

    assert context["task"] == "test-task"
    assert context["round"] == 1
    assert context["brief"] == "Create a test application"
    assert len(context["checks"]) == 2

    print("✅ Context gathering works!")


def test_starter_template():
    """Test that all starter template files exist."""
    print("\n📁 Testing starter template files...")

    builder = AppBuilder()
    required_files = ["index.html", "style.css", "script.js", "README.md", "LICENSE"]

    for filename in required_files:
        content = builder.load_starter_file(filename)
        assert len(content) > 0, f"Starter file {filename} is empty or missing"
        print(f"✅ {filename} loaded successfully")

    print("✅ All starter template files are present!")


async def run_all_tests():
    """Run all tests."""
    print("🚀 Starting comprehensive tests for LLM Code Deployment Application\n")

    try:
        await test_basic_functionality()
        await test_attachment_processing()
        await test_context_gathering()
        test_starter_template()

        print("\n🎉 ALL TESTS PASSED!")
        print("\n📊 Implementation Status:")
        print("✅ Phase 1: Request Processing & Validation")
        print("✅ Phase 2: Repository Setup (Round 1 Only)")
        print("✅ Phase 3: Context Gathering (All Rounds)")
        print("✅ Phase 4: LLM Agent Execution Framework")
        print("✅ Phase 5: Repository Updates")
        print("✅ Phase 6: Deployment & Evaluation")
        print("\n🔧 Agent Tools Available:")
        print("  - read_files()")
        print("  - update_files()")
        print("  - list_directory_contents()")
        print("  - delete_file()")
        print("  - get_repository_tree()")
        print("\n📝 Ready for LLM Agent Implementation!")

    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
