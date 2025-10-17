#!/usr/bin/env python3
"""
Comprehensive test script for the Website Developer API
Tests both Round 1 and Round 2 using YAML test configurations
"""

import requests
import base64
import yaml
import os
import time
import uuid
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Any
import re

# Load environment variables
load_dotenv(override=True)


class APITester:
    def __init__(self):
        self.api_url = os.getenv("API_URL", "http://localhost:8000")
        self.callback_url = os.getenv("CALLBACK_URL", "http://localhost:9000")
        self.api_secret = os.getenv("API_SECRET", "default-secret")
        self.email = os.getenv("TEST_EMAIL", "test@example.com")
        self.test_results = []

    def preprocess_yaml_file(self, yaml_path: Path) -> str:
        """Preprocess YAML to quote strings containing ${...} in URLs only."""
        with open(yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1️⃣ Quote URLs containing ${...} if not already quoted
        url_pattern = re.compile(r'^(url:\s*)([^\s"].*\$\{[^}]+\}.*)$', re.MULTILINE)
        content = url_pattern.sub(r'\1"\2"', content)

        # 2️⃣ Remove leading !! from js: lines
        js_pattern = re.compile(r"^(\s*-\s*js:\s*)!!", re.MULTILINE)
        content = js_pattern.sub(r"\1", content)

        return content

    def load_yaml_tests(self) -> List[Dict]:
        """Load all YAML test files from sample_tests folder."""
        tests = []
        test_dir = Path("sample_tests")

        for yaml_file in test_dir.glob("*.yaml"):
            yaml_content = self.preprocess_yaml_file(yaml_file)
            test_config = yaml.safe_load(yaml_content)
            tests.append(test_config)
            print(f"✓ Loaded test: {test_config['id']}")

        return tests

    def create_test_data(self, test_id: str) -> Dict[str, str]:
        """Create test data based on test ID."""
        if "sum-of-sales" in test_id:
            # Create CSV data
            csv_content = "product,region,sales\nProduct A,North,100.50\nProduct B,South,250.75\nProduct C,North,150.25"
            csv_encoded = base64.b64encode(csv_content.encode()).decode()
            return {"csv": csv_encoded, "result": "501.50", "seed": "test-seed-123"}

        elif "markdown" in test_id:
            # Create Markdown data
            md_content = "# Test Header\n\nThis is a test markdown file.\n\n```python\nprint('Hello World')\n```"
            md_encoded = base64.b64encode(md_content.encode()).decode()
            return {"md": md_encoded, "seed": "test-seed-456"}

        elif "github" in test_id:
            return {"seed": "test-seed-789"}

        return {"seed": "default-seed"}

    def process_attachments(
        self, attachments_config: List[Dict], test_data: Dict
    ) -> List[Dict]:
        """Process attachment configurations and substitute variables."""
        attachments = []

        for att_config in attachments_config:
            url_template = att_config.get("url", "")

            # Substitute ${seed} and other variables
            if "${seed}" in url_template:
                if "csv" in att_config["name"]:
                    url_template = url_template.replace(
                        "${seed}", test_data.get("csv", "")
                    )
                elif "md" in att_config["name"]:
                    url_template = url_template.replace(
                        "${seed}", test_data.get("md", "")
                    )
                else:
                    url_template = url_template.replace(
                        "${seed}", test_data.get("seed", "")
                    )

            attachments.append({"name": att_config["name"], "url": url_template})

        return attachments

    def poll_for_verification(
        self, task_id: str, round_num: int, timeout: int = 300
    ) -> Dict:
        """Poll callback server to check if verification has completed."""
        start_time = time.time()
        check_interval = 5  # Check every 5 seconds

        print(f"   Checking for verification results every {check_interval} seconds...")

        while time.time() - start_time < timeout:
            try:
                # Query callback server for results
                response = requests.get(f"{self.callback_url}/", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    callbacks = data.get("callbacks", [])

                    # Look for matching callback with verification results
                    for callback in reversed(callbacks):  # Check most recent first
                        callback_data = callback.get("data", {})
                        if (
                            callback_data.get("task") == task_id
                            and callback_data.get("round") == round_num
                            and "verification" in callback
                        ):
                            verification = callback["verification"]
                            print(
                                f"\n✓ Verification found: {verification['passed']}/{verification['total']} checks passed"
                            )
                            return verification

                # Show progress
                elapsed = int(time.time() - start_time)
                print(".", end="", flush=True)
                if elapsed % 30 == 0 and elapsed > 0:
                    print(f" {elapsed}s", flush=True)

            except Exception as e:
                print(f"⚠ Error polling callback server: {str(e)}")

            time.sleep(check_interval)

        print(f"\n⏱ Timeout after {timeout}s - verification may still be in progress")
        return None

    def process_checks(self, checks_config: List[Any], test_data: Dict) -> List[str]:
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

    def send_build_request(
        self, test_config: Dict, round_num: int, test_data: Dict
    ) -> Dict:
        """Send build request to the API."""
        task_id = test_config["id"]  # Use the test ID directly
        nonce = str(uuid.uuid4())

        # Prepare attachments
        attachments = []
        if round_num == 1:
            if "attachments" in test_config:
                attachments = self.process_attachments(
                    test_config["attachments"], test_data
                )
        else:
            # Round 2 - get attachments from round2 config
            round2_config = test_config.get("round2", [{}])[0]
            if "attachments" in round2_config:
                attachments = self.process_attachments(
                    round2_config["attachments"], test_data
                )

        # Prepare brief and checks
        if round_num == 1:
            brief = test_config["brief"]
            checks = self.process_checks(test_config["checks"], test_data)
        else:
            round2_config = test_config.get("round2", [{}])[0]
            brief = round2_config.get("brief", "")
            checks = self.process_checks(round2_config.get("checks", []), test_data)

        request_payload = {
            "email": self.email,
            "secret": self.api_secret,
            "task": task_id,
            "round": round_num,
            "nonce": nonce,
            "brief": brief,
            "checks": checks,
            "evaluation_url": self.callback_url,
            "attachments": attachments,
        }

        print(f"\n{'=' * 60}")
        print(f"📤 Sending Round {round_num} Request")
        print(f"{'=' * 60}")
        print(f"Task ID: {task_id}")
        print(f"Brief: {brief[:100]}...")
        print(f"Checks: {len(checks)} checks")
        print(f"Attachments: {len(attachments)} files")

        try:
            # Increased timeout to 120 seconds (2 minutes) to allow for:
            # - Code generation with LLM
            # - GitHub repo creation
            # - File uploads
            # - GitHub Pages enablement
            response = requests.post(
                f"{self.api_url}/build",
                json=request_payload,
                headers={"Content-Type": "application/json"},
                timeout=120,  # 2 minutes timeout
            )

            print(f"\n✓ Response Status: {response.status_code}")
            response_data = response.json()
            print(f"✓ Response: {response_data}")

            return {
                "success": response.status_code == 200,
                "task_id": task_id,
                "response": response_data,
                "payload": request_payload,
            }

        except Exception as e:
            print(f"\n✗ Request failed: {str(e)}")
            return {
                "success": False,
                "task_id": task_id,
                "error": str(e),
                "payload": request_payload,
            }

    def run_test(self, test_config: Dict):
        """Run complete test cycle for a test configuration."""
        print(f"\n{'#' * 60}")
        print(f"# Testing: {test_config['id']}")
        print(f"{'#' * 60}")

        # Generate test data
        test_data = self.create_test_data(test_config["id"])

        # ROUND 1
        print(f"\n🚀 Starting Round 1...")
        round1_result = self.send_build_request(test_config, 1, test_data)

        if not round1_result["success"]:
            print(f"✗ Round 1 failed, skipping Round 2")
            self.test_results.append(
                {"test_id": test_config["id"], "round1": round1_result, "round2": None}
            )
            return

        # Wait for deployment and verification by callback server
        print("\n⏳ Waiting for build and deployment...")
        print("   The callback server will verify the deployment automatically...")
        print("   During this time:")
        print("     - AI agent is generating optimized code")
        print("     - GitHub repository is being created/updated")
        print("     - GitHub Actions workflow is building the site")
        print("     - GitHub Pages is deploying the site")
        print("     - Callback server will run Playwright tests when ready")
        print()
        print("   Polling callback server for verification results...")

        # Poll callback server for verification results
        task_id = round1_result["task_id"]
        verification_result = self.poll_for_verification(
            task_id, round_num=1, timeout=300
        )

        if verification_result:
            round1_result["verification"] = verification_result

        # Get deployment URL from response
        pages_url = round1_result["response"].get("pages_url", "")
        print(f"\n✓ Round 1 deployment URL: {pages_url}")

        if verification_result:
            print(
                f"✓ Verification completed: {verification_result['passed']}/{verification_result['total']} checks passed"
            )
        else:
            print(
                "⚠ Verification results not available yet - check callback server terminal"
            )

        # ROUND 2
        if "round2" in test_config and test_config["round2"]:
            print("\n🚀 Starting Round 2...")
            time.sleep(5)  # Brief pause between rounds

            round2_result = self.send_build_request(test_config, 2, test_data)

            if round2_result["success"]:
                print("\n⏳ Waiting for Round 2 deployment (5 minutes)...")
                print(
                    "   The callback server will verify the deployment automatically..."
                )
                print()

                # Show progress indicator
                for i in range(60):
                    time.sleep(5)
                    print(".", end="", flush=True)
                    if (i + 1) % 20 == 0:
                        print(f" {(i + 1) * 5}s", flush=True)
                print()  # New line after progress

                pages_url = round2_result["response"].get("pages_url", "")
                print(f"\n✓ Round 2 deployment URL: {pages_url}")
                print("   Check the callback server terminal for verification results")
        else:
            round2_result = None

        # Store results
        self.test_results.append(
            {
                "test_id": test_config["id"],
                "round1": round1_result,
                "round2": round2_result,
            }
        )

    def print_summary(self):
        """Print summary of all test results."""
        print(f"\n\n{'=' * 60}")
        print("📋 TEST SUMMARY")
        print(f"{'=' * 60}")

        print(
            "\nNote: Verification results are displayed in the callback server terminal"
        )
        print("Check the other terminal window for Playwright test results\n")

        for result in self.test_results:
            print(f"\n🔸 Test: {result['test_id']}")

            # Round 1
            r1 = result["round1"]
            print(f"  Round 1: {'✓ SUCCESS' if r1['success'] else '✗ FAILED'}")

            # Round 2
            if result["round2"]:
                r2 = result["round2"]
                print(f"  Round 2: {'✓ SUCCESS' if r2['success'] else '✗ FAILED'}")

    def run_all_tests(self):
        """Run all tests from YAML files."""
        print("Website Developer API - Comprehensive Test Suite")
        print("=" * 60)

        # Check API health
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            print(f"✓ API Health Check: {response.status_code}")
        except Exception as e:
            print(f"✗ API Health Check Failed: {str(e)}")
            print("Please ensure the API is running!")
            return

        # Load tests
        tests = self.load_yaml_tests()
        print(f"\n✓ Loaded {len(tests)} test configurations")

        # Run each test
        for test_config in tests:
            try:
                self.run_test(test_config)
            except Exception as e:
                print(f"\n✗ Test {test_config['id']} failed with error: {str(e)}")
                import traceback

                traceback.print_exc()

        # Print summary
        self.print_summary()


if __name__ == "__main__":
    tester = APITester()
    tester.run_all_tests()
