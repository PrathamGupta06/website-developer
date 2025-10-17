import os
import asyncio
import httpx
import logging
import base64
from fastapi import FastAPI, HTTPException, BackgroundTasks
from github import Github
from models import BuildRequest, BuildResponse, EvaluationPayload
from dotenv import load_dotenv
from agent import WebsiteAgent, AgentTools
from db import TaskRepository

# Load environment variables from .env file
load_dotenv(override=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Website Developer API",
    description="Automated web application builder API",
    version="1.0.0",
)


class AppBuilder:
    """
    Main class responsible for building web applications based on requests.
    """

    def __init__(self):
        # These should be set via environment variables in production
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.valid_secret = os.getenv("API_SECRET", "default-secret")
        self.github_client = Github(self.github_token) if self.github_token else None
        self.task_db = TaskRepository()  # Initialize CSV-based storage

    def validate_secret(self, provided_secret: str) -> bool:
        """Validate the provided secret against the expected secret."""
        return provided_secret == self.valid_secret

    async def process_build_request(self, request: BuildRequest):
        """
        Process the build request in the background.
        This is the main orchestration method.
        """
        try:
            logger.info(
                f"Starting build process for {request.task}, round {request.round}"
            )

            # Step 1: Parse attachments and save them
            attachments_data = await self.process_attachments(request.attachments)

            # Step 2: Generate initial application code based on brief
            app_code = await self.generate_application_code(
                request.brief, request.checks, attachments_data
            )

            # Step 3: Create or update GitHub repository (handles both round 1 and 2+)
            repo_info = await self.create_github_repository(
                request.task, app_code, request.email, request.round
            )

            if not repo_info:
                logger.error("Failed to create/update repository")
                return

            # Step 4: Enable GitHub Pages (only needed for round 1, handled in create_github_repository)
            # await self.enable_github_pages(repo_info["repo_name"])

            # Step 5: Enhance with AI agent (this is where the actual AI generation happens)
            if self.github_client:
                await self.enhance_with_agent(
                    repo_info["repo_name"],
                    request.brief,
                    request.checks,
                    attachments_data,
                    request.round,
                )

            # Step 6: Wait for GitHub Actions workflow and Pages deployment
            if self.github_client and request.evaluation_url:
                await self.wait_and_post_results(request, repo_info)
            else:
                logger.info(f"Skipping evaluation for task {request.task}")

            logger.info(
                f"Successfully completed build for {request.task}, round {request.round}"
            )

        except Exception as e:
            logger.error(f"Error in build process: {str(e)}")
            # In a production system, you might want to retry or send error notifications

    async def process_attachments(self, attachments):
        """Process and decode data URI attachments."""
        processed_attachments = []

        for attachment in attachments:
            try:
                # Parse data URI (format: data:mime/type;base64,data)
                if attachment.url.startswith("data:"):
                    header, data = attachment.url.split(",", 1)
                    mime_type = header.split(";")[0].replace("data:", "")

                    # Decode base64 data
                    decoded_data = base64.b64decode(data)

                    processed_attachments.append(
                        {
                            "name": attachment.name,
                            "mime_type": mime_type,
                            "data": decoded_data,
                        }
                    )

                    logger.info(f"Processed attachment: {attachment.name}")

            except Exception as e:
                logger.error(f"Error processing attachment {attachment.name}: {str(e)}")

        return processed_attachments

    async def generate_application_code(
        self, brief: str, checks: list, attachments_data: list
    ):
        """
        Generate application code based on the brief and requirements.
        Now uses the actual WebsiteAgent for AI-powered code generation.
        """
        logger.info("Generating application code using AI agent...")

        # Create a temporary repository or use existing logic
        # For now, we'll use the skeleton approach but this should be replaced
        # with actual agent integration after repository creation

        # Skeleton implementation - this will be replaced by agent after repo creation
        app_files = {
            "index.html": self.generate_html_template(brief),
            "script.js": self.generate_js_template(brief),
            "style.css": self.generate_css_template(),
            "README.md": self.generate_readme(brief, checks),
            "LICENSE": self.generate_mit_license(),
        }

        # Save attachment files
        for attachment in attachments_data:
            if isinstance(attachment["data"], bytes):
                # For binary data, we'll need to handle differently
                app_files[attachment["name"]] = attachment["data"]
            else:
                app_files[attachment["name"]] = attachment["data"]

        return app_files

    async def enhance_with_agent(
        self,
        repo_name: str,
        brief: str,
        checks: list,
        attachments_data: list,
        round_num: int = 1,
    ):
        """
        Use the WebsiteAgent to enhance the repository after initial creation.
        """
        try:
            if not self.github_client:
                logger.warning(
                    "GitHub client not available, skipping agent enhancement"
                )
                return {"success": False, "error": "GitHub client not available"}

            logger.info(f"Enhancing repository {repo_name} with AI agent...")

            # Get the repository object
            user = self.github_client.get_user()
            repo = self.github_client.get_repo(f"{user.login}/{repo_name}")

            # Initialize agent tools and agent
            agent_tools = AgentTools(repo)
            agent = WebsiteAgent(agent_tools)

            # Prepare context for the agent
            context = {
                "brief": brief,
                "checks": checks,
                "round": round_num,  # Pass the actual round number
                "attachments": attachments_data,
                "task": repo_name,
                "current_repo_state": None,  # Agent will read current state
            }

            # Generate website using the agent
            result = await agent.generate_website(context)

            if result.get("success"):
                logger.info("AI agent successfully enhanced the repository")
            else:
                logger.warning(
                    f"AI agent completed with issues: {result.get('message', 'Unknown error')}"
                )

            return result

        except Exception as e:
            logger.error(f"Error enhancing repository with agent: {str(e)}")
            return {"success": False, "error": str(e)}

    def generate_html_template(self, brief: str) -> str:
        """Generate basic HTML template."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generated Web App</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <h1>Generated Web Application</h1>
        <p>Brief: {brief}</p>
        <div id="app-content">
            <!-- Application content will be generated here -->
        </div>
    </div>
    <script src="script.js"></script>
</body>
</html>"""

    def generate_js_template(self, brief: str) -> str:
        """Generate basic JavaScript template."""
        return f"""// Generated JavaScript for: {brief}
document.addEventListener('DOMContentLoaded', function() {{
    console.log('Application loaded');
    
    // Get URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const url = urlParams.get('url');
    
    if (url) {{
        console.log('URL parameter found:', url);
        // Process the URL parameter
        handleUrlParameter(url);
    }} else {{
        console.log('No URL parameter, using default');
        handleDefault();
    }}
}});

function handleUrlParameter(url) {{
    // Skeleton function to handle URL parameter
    console.log('Processing URL:', url);
}}

function handleDefault() {{
    // Skeleton function for default behavior
    console.log('Using default behavior');
}}"""

    def generate_css_template(self) -> str:
        """Generate basic CSS template."""
        return """/* Generated CSS */
body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
    background-color: #f5f5f5;
}

.container {
    max-width: 800px;
    margin: 0 auto;
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

h1 {
    color: #333;
    text-align: center;
}

#app-content {
    margin-top: 20px;
    padding: 20px;
    border: 1px solid #ddd;
    border-radius: 4px;
}"""

    def generate_readme(self, brief: str, checks: list) -> str:
        """Generate README.md file."""
        checks_md = "\\n".join([f"- {check}" for check in checks])

        return f"""# Generated Web Application

## Description
{brief}

## Requirements
{checks_md}

## Setup
1. Clone this repository
2. Open `index.html` in a web browser
3. For URL parameter testing, use: `index.html?url=your-image-url`

## Usage
This application was automatically generated based on the provided brief and requirements.

## License
MIT License - see LICENSE file for details
"""

    def generate_mit_license(self) -> str:
        """Generate MIT license text."""
        return """MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

    async def create_github_repository(
        self, task_name: str, app_files: dict, email: str = "", round_num: int = 1
    ):
        if not self.github_client:
            logger.warning("GitHub token not configured, skipping repo creation")
            return {
                "repo_name": f"generated-{task_name}",
                "repo_url": "https://github.com/user/repo",
                "commit_sha": "abc123",
            }

        try:
            # Check if repository already exists for this task
            task_info = self.task_db.get_repo_by_task(task_name)
            user = self.github_client.get_user()
            repo_name = f"generated-{task_name}"

            if task_info:
                # Repository exists, update it instead of creating new one
                logger.info(
                    f"Repository already exists for task {task_name}, updating it"
                )
                try:
                    repo = self.github_client.get_repo(
                        f"{user.login}/{task_info['repo_name']}"
                    )
                    repo_name = task_info["repo_name"]
                except Exception as e:
                    logger.warning(
                        f"Could not find existing repo: {str(e)}, will create new one"
                    )
                    task_info = None  # Reset to create new repo

            if not task_info:
                # Create new repository
                logger.info(f"Creating new repository: {repo_name}")
                try:
                    repo = user.create_repo(
                        repo_name,
                        description=f"Auto-generated web application for {task_name}",
                        private=False,
                        auto_init=True,
                    )
                except Exception as create_error:
                    # Repository might already exist on GitHub but not in our CSV
                    if "already exists" in str(create_error):
                        logger.info(
                            f"Repository exists on GitHub, fetching it: {repo_name}"
                        )
                        repo = self.github_client.get_repo(f"{user.login}/{repo_name}")
                    else:
                        raise

            # Push files to repository
            for filename, content in app_files.items():
                try:
                    repo.create_file(
                        filename, f"Add {filename}", content, branch="main"
                    )
                except Exception:
                    try:
                        existing_file = repo.get_contents(filename)
                        if isinstance(existing_file, list):
                            existing_file = existing_file[0]
                        repo.update_file(
                            filename,
                            f"Update {filename}",
                            content,
                            existing_file.sha,
                            branch="main",
                        )
                    except Exception:
                        logger.warning(f"Could not create or update {filename}")
                        continue

            # Enable GitHub Pages using REST API (only for new repos)
            if not task_info or round_num == 1:
                import requests

                token = self.github_token
                api_url = f"https://api.github.com/repos/{user.login}/{repo_name}/pages"
                headers = {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                }
                data = {
                    "build_type": "workflow",
                    "source": {"branch": "main", "path": "/"},
                }
                response = requests.post(api_url, headers=headers, json=data)
                if response.status_code == 201:
                    logger.info(f"GitHub Pages enabled for {repo_name}")
                else:
                    logger.warning(
                        f"Failed to enable GitHub Pages: {response.status_code} {response.text}"
                    )

            # Get the latest commit SHA
            commits = repo.get_commits()
            latest_commit_sha = commits[0].sha

            # Prepare Pages URL
            pages_url = f"https://{user.login}.github.io/{repo_name}/"

            # Save to CSV database
            self.task_db.save_task_repo(
                task=task_name,
                email=email,
                repo_name=repo_name,
                repo_url=repo.html_url,
                commit_sha=latest_commit_sha,
                pages_url=pages_url,
                round_num=round_num,
            )

            logger.info(
                f"Repository {'updated' if task_info else 'created'} successfully: {repo.html_url}"
            )

            return {
                "repo_name": repo_name,
                "repo_url": repo.html_url,
                "commit_sha": latest_commit_sha,
                "pages_url": pages_url,
            }

        except Exception as e:
            logger.error(f"Error creating GitHub repository: {str(e)}")
            return None

    async def enable_github_pages(self, repo_name: str):
        """Enable GitHub Pages for the repository."""
        if not self.github_client:
            logger.warning("GitHub token not configured, skipping Pages setup")
            return

        try:
            user = self.github_client.get_user()
            repo = user.get_repo(repo_name)

            # GitHub Pages will automatically enable when there's an index.html in the main branch
            # We can also try to enable it via GitHub's REST API if needed
            logger.info(f"Repository ready for GitHub Pages: {repo.html_url}")
            pages_url = f"https://{user.login}.github.io/{repo_name}"
            logger.info(f"Expected Pages URL: {pages_url}")

        except Exception as e:
            logger.error(f"Error setting up GitHub Pages: {str(e)}")
            # Don't raise here as this might not be critical

    async def wait_and_post_results(self, request: BuildRequest, repo_info: dict):
        """Wait for workflow completion and Pages deployment, then post results."""
        try:
            # Get the repository object
            user = self.github_client.get_user()
            repo = self.github_client.get_repo(f"{user.login}/{repo_info['repo_name']}")

            # Wait for workflow to complete
            logger.info("Waiting for GitHub Actions workflow to complete...")
            workflow_completed = await self.wait_for_workflow_completion(repo)

            if workflow_completed:
                logger.info("Workflow completed successfully")
            else:
                logger.warning("Workflow did not complete in time")

            # Wait for Pages to be accessible
            pages_url = await self.wait_for_pages_deployment(
                repo, repo_info["pages_url"]
            )

            # Post evaluation results
            await self.post_evaluation_results(request, repo_info, pages_url)

        except Exception as e:
            logger.error(f"Error in wait and post results: {str(e)}")

    async def wait_for_workflow_completion(self, repo, timeout: int = 300) -> bool:
        """Wait for GitHub Actions workflow to complete."""
        try:
            import time as time_module

            start_time = time_module.time()

            logger.info(f"Checking workflow runs for repository: {repo.name}")
            await asyncio.sleep(5)  # Wait for workflow to start

            while time_module.time() - start_time < timeout:
                try:
                    workflows = repo.get_workflow_runs()

                    if workflows.totalCount > 0:
                        latest_run = workflows[0]

                        logger.info(
                            f"Workflow status: {latest_run.status}, "
                            f"conclusion: {latest_run.conclusion}"
                        )

                        if latest_run.status == "completed":
                            if latest_run.conclusion == "success":
                                logger.info("Workflow completed successfully!")
                                return True
                            else:
                                logger.warning(
                                    f"Workflow completed with conclusion: {latest_run.conclusion}"
                                )
                                return False

                        logger.info(f"Workflow still {latest_run.status}, waiting...")
                    else:
                        logger.info("No workflow runs found yet, waiting...")

                except Exception as e:
                    logger.debug(f"Error checking workflow status: {str(e)}")

                await asyncio.sleep(10)

            logger.warning(f"Workflow did not complete within {timeout} seconds")
            return False

        except Exception as e:
            logger.error(f"Error waiting for workflow completion: {str(e)}")
            return False

    async def wait_for_pages_deployment(self, repo, pages_url: str) -> str:
        """Wait for GitHub Pages to be accessible."""
        logger.info("Waiting for GitHub Pages to be accessible...")
        max_attempts = 30  # 5 minutes with 10-second intervals

        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(pages_url, timeout=10.0)
                    if response.status_code == 200:
                        logger.info(f"GitHub Pages is ready: {pages_url}")
                        return pages_url
            except Exception as e:
                logger.debug(f"Pages not ready yet (attempt {attempt + 1}): {str(e)}")

            if attempt < max_attempts - 1:
                await asyncio.sleep(10)

        logger.warning(f"GitHub Pages may not be ready yet: {pages_url}")
        return pages_url

    async def post_evaluation_results(
        self, request: BuildRequest, repo_info: dict, pages_url: str
    ):
        """Post results to the evaluation URL with retry logic."""
        evaluation_payload = EvaluationPayload(
            email=request.email,
            task=request.task,
            round=request.round,
            nonce=request.nonce,
            repo_url=repo_info["repo_url"],
            commit_sha=repo_info["commit_sha"],
            pages_url=pages_url,
        )

        logger.info(
            f"Posting evaluation results: {evaluation_payload.model_dump_json()}"
        )

        # Retry logic with exponential backoff
        max_retries = 5
        delay = 1

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        str(request.evaluation_url),
                        json=evaluation_payload.dict(),
                        headers={"Content-Type": "application/json"},
                        timeout=30.0,
                    )

                    if response.status_code == 200:
                        logger.info(
                            f"Successfully posted evaluation results (attempt {attempt + 1})"
                        )
                        return
                    else:
                        logger.warning(
                            f"Evaluation URL returned {response.status_code}, retrying..."
                        )

            except Exception as e:
                logger.error(
                    f"Error posting to evaluation URL (attempt {attempt + 1}): {str(e)}"
                )

            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay *= 2  # Exponential backoff

        logger.error("Failed to post evaluation results after all retries")


# Initialize the app builder
app_builder = AppBuilder()


@app.get("/")
async def root():
    return {"message": "Website Developer API is running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/build", response_model=BuildResponse)
async def build_application(request: BuildRequest, background_tasks: BackgroundTasks):
    """
    Main endpoint to build web applications based on the provided brief.

    This endpoint:
    1. Validates the secret
    2. Parses the request and attachments
    3. Generates the application code
    4. Creates GitHub repo and enables Pages
    5. Posts results to evaluation URL
    """
    try:
        logger.info(
            f"Received build request for task: {request.task}, round: {request.round}"
        )

        # Validate secret
        if not app_builder.validate_secret(request.secret):
            raise HTTPException(status_code=401, detail="Invalid secret")

        # Add the build process to background tasks
        background_tasks.add_task(app_builder.process_build_request, request)

        return BuildResponse(
            status="accepted",
            message="Build request accepted and processing started",
            task=request.task,
            round=request.round,
        )

    except Exception as e:
        logger.error(f"Error processing build request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    # Load environment variables for configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))

    # Check for required environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    api_secret = os.getenv("API_SECRET")

    if not github_token:
        print("Warning: GITHUB_TOKEN not set. Repository creation will be skipped.")

    if not api_secret:
        print(
            "Warning: API_SECRET not set. Using default secret (not secure for production)."
        )

    print(f"Starting Website Developer API on {host}:{port}")

    uvicorn.run("main:app", host=host, port=port)
