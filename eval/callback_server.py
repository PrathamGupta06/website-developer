#!/usr/bin/env python3
"""
Enhanced callback server to receive evaluation results and run Playwright tests
Run this to simulate the evaluation endpoint
"""

from fastapi import FastAPI, Request
import uvicorn
import os
from dotenv import load_dotenv
import json
from datetime import datetime
from playwright.async_api import async_playwright
from pathlib import Path
import yaml
import base64
import re
import asyncio

load_dotenv()

app = FastAPI(title="Callback Server")

# Store received callbacks
callbacks = []

# Store test configurations mapped by task ID
test_configs = {}
test_data_cache = {}


def load_test_configs():
    """Load all test configurations from YAML files."""
    test_dir = Path("sample_tests")
    if not test_dir.exists():
        print("⚠ sample_tests directory not found!")
        return

    for yaml_file in test_dir.glob("*.yaml"):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Preprocess YAML
            url_pattern = re.compile(
                r'^(url:\s*)([^\s"].*\$\{[^}]+\}.*)$', re.MULTILINE
            )
            content = url_pattern.sub(r'\1"\2"', content)
            js_pattern = re.compile(r"^(\s*-\s*js:\s*)!!", re.MULTILINE)
            content = js_pattern.sub(r"\1", content)

            test_config = yaml.safe_load(content)
            test_configs[test_config["id"]] = test_config

            # Create test data for this test
            if "sum-of-sales" in test_config["id"]:
                csv_content = "product,region,sales\nProduct A,North,100.50\nProduct B,South,250.75\nProduct C,North,150.25"
                csv_encoded = base64.b64encode(csv_content.encode()).decode()
                test_data_cache[test_config["id"]] = {
                    "csv": csv_encoded,
                    "result": "501.50",
                    "seed": "test-seed-123",
                }
            elif "markdown" in test_config["id"]:
                md_content = "# Test Header\n\nThis is a test markdown file.\n\n```python\nprint('Hello World')\n```"
                md_encoded = base64.b64encode(md_content.encode()).decode()
                test_data_cache[test_config["id"]] = {
                    "md": md_encoded,
                    "seed": "test-seed-456",
                }
            elif "github" in test_config["id"]:
                test_data_cache[test_config["id"]] = {"seed": "test-seed-789"}

            print(f"✓ Loaded test config: {test_config['id']}")
        except Exception as e:
            print(f"✗ Error loading {yaml_file}: {str(e)}")


def process_checks(checks_config, test_data):
    """Process check configurations and substitute variables."""
    checks = []
    for check in checks_config:
        if isinstance(check, dict) and "js" in check:
            check_str = check["js"]
        else:
            check_str = str(check)

        # Substitute variables
        for key, value in test_data.items():
            check_str = check_str.replace(f"${{{key}}}", str(value))

        checks.append(check_str)
    return checks


async def verify_with_playwright(
    pages_url: str, checks: list, task_id: str, round_num: int
):
    """Verify the deployment using Playwright."""
    print(f"\n{'=' * 60}")
    print("🔍 Running Playwright Verification")
    print(f"{'=' * 60}")
    print(f"Task: {task_id} | Round: {round_num}")
    print(f"URL: {pages_url}")
    print(f"Checks: {len(checks)} tests")

    results = {"total": len(checks), "passed": 0, "failed": 0, "details": []}

    try:
        # Wait a bit for deployment to stabilize
        # print("\n⏳ Waiting 30 seconds for deployment to stabilize...")
        # await asyncio.sleep(30)

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            print(f"🌐 Loading page: {pages_url}")
            await page.goto(pages_url, timeout=30000)
            await page.wait_for_load_state("networkidle")
            print("✓ Page loaded successfully")

            print(f"\n{'─' * 60}")
            print("Running Checks:")
            print(f"{'─' * 60}")

            for i, check in enumerate(checks, 1):
                try:
                    result = await page.evaluate(check)

                    if result:
                        print(f"  ✓ Check {i}/{len(checks)}: PASSED")
                        results["passed"] += 1
                        results["details"].append({"check": check, "passed": True})
                    else:
                        print(f"  ✗ Check {i}/{len(checks)}: FAILED (returned false)")
                        results["failed"] += 1
                        results["details"].append(
                            {
                                "check": check,
                                "passed": False,
                                "reason": "Returned false",
                            }
                        )

                except Exception as e:
                    print(f"  ✗ Check {i}/{len(checks)}: ERROR - {str(e)}")
                    results["failed"] += 1
                    results["details"].append(
                        {"check": check, "passed": False, "reason": str(e)}
                    )

            await browser.close()

        print(f"\n{'─' * 60}")
        print("📊 Verification Results:")
        print(f"  Total: {results['total']}")
        print(f"  ✓ Passed: {results['passed']}")
        print(f"  ✗ Failed: {results['failed']}")
        print(f"  Success Rate: {(results['passed'] / results['total'] * 100):.1f}%")
        print(f"{'=' * 60}\n")

    except Exception as e:
        print(f"\n✗ Playwright verification failed: {str(e)}")
        results["error"] = str(e)
        print(f"{'=' * 60}\n")

    return results


# Load test configs on startup
print("Loading test configurations...")
load_test_configs()
print(f"✓ Loaded {len(test_configs)} test configurations\n")


@app.post("/")
async def receive_callback(request: Request):
    """Receive evaluation callbacks from the API and run verification."""
    try:
        data = await request.json()

        callback_info = {"timestamp": datetime.now().isoformat(), "data": data}

        callbacks.append(callback_info)

        print("\n" + "=" * 60)
        print("📨 RECEIVED EVALUATION CALLBACK")
        print("=" * 60)
        print(json.dumps(data, indent=2))
        print(f"\nTotal callbacks received: {len(callbacks)}")
        print("=" * 60 + "\n")

        # Extract callback data
        task_id = data.get("task")
        round_num = data.get("round", 1)
        pages_url = data.get("pages_url")

        # Run Playwright verification if we have the test config
        if task_id in test_configs and pages_url:
            test_config = test_configs[task_id]
            test_data = test_data_cache.get(task_id, {})

            # Get checks for the appropriate round
            if round_num == 1:
                checks_config = test_config.get("checks", [])
            else:
                round2_config = test_config.get("round2", [{}])[0]
                checks_config = round2_config.get("checks", [])

            # Process and run checks
            checks = process_checks(checks_config, test_data)
            verification_result = await verify_with_playwright(
                pages_url, checks, task_id, round_num
            )

            # Store verification result with callback
            callback_info["verification"] = verification_result
        else:
            if task_id not in test_configs:
                print(f"⚠ No test config found for task: {task_id}")
            if not pages_url:
                print(f"⚠ No pages_url provided in callback")

        return {"status": "success", "message": "Callback received and verified"}

    except Exception as e:
        print(f"Error processing callback: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/")
async def root():
    """Show all received callbacks."""
    return {
        "message": "Callback Server",
        "total_callbacks": len(callbacks),
        "callbacks": callbacks,
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    port = int(os.getenv("CALLBACK_PORT", 9000))
    print(f"Starting Callback Server on port {port}")
    print(f"Endpoint: http://localhost:{port}/")
    print("Waiting for callbacks...\n")

    uvicorn.run("callback_server:app", host="0.0.0.0", port=port, reload=False)
