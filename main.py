import os
import asyncio
import httpx
import logging
import base64
import time
from fastapi import FastAPI, HTTPException, BackgroundTasks
from github import Github
from models import BuildRequest, BuildResponse, EvaluationPayload
from dotenv import load_dotenv
from agent import WebsiteAgent, AgentTools
from db import TaskRepository
from logger import telegram_logger

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
        # Generate unique session ID for tracking
        session_id = f"build_{request.task}_{request.round}_{int(time.time())}"

        # Start session tracking
        telegram_logger.start_session(
            session_id,
            request.task,
            {
                "round": request.round,
                "email": request.email,
                "task": request.task,
                "has_attachments": len(request.attachments) > 0,
                "num_attachments": len(request.attachments),
                "evaluation_url": request.evaluation_url,
            },
        )

        try:
            logger.info(
                f"Starting build process for {request.task}, round {request.round}"
            )

            # Step 1: Parse attachments and save them
            attachments_data = await self.process_attachments(request.attachments)

            # Step 2: Generate initial application code based on brief (only for round 1)
            app_code = {}
            if request.round == 1:
                app_code = await self.generate_application_code(
                    request.brief, request.checks, attachments_data
                )
                logger.info("Generated skeleton application code for round 1")
            else:
                # For round 2+, only add attachment files if any
                for attachment in attachments_data:
                    if isinstance(attachment["data"], bytes):
                        app_code[attachment["name"]] = attachment["data"]
                    else:
                        app_code[attachment["name"]] = attachment["data"]
                logger.info(
                    f"Round {request.round}: Skipping skeleton generation, only processing attachments"
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

            # Log complete success details to main logger
            logger.info(
                f"Successfully completed build for {request.task}, round {request.round}"
            )
            logger.info(f"Final repository info: {repo_info}")
            logger.info(f"Attachments processed: {len(attachments_data)}")
            logger.info(
                f"Evaluation sent: {bool(self.github_client and request.evaluation_url)}"
            )
            if attachments_data:
                logger.info(
                    f"Processed attachments: {[att.get('name', 'unnamed') for att in attachments_data]}"
                )

            # Log successful completion to Telegram (summary)
            telegram_logger.end_session(
                session_id,
                request.task,
                True,
                {
                    "repo_url": repo_info.get("repo_url"),
                    "pages_url": repo_info.get("pages_url"),
                    "commit_sha": repo_info.get("commit_sha"),
                    "attachments_processed": len(attachments_data),
                    "attachment_names": [
                        att.get("name", "unnamed") for att in attachments_data
                    ],
                    "evaluation_sent": bool(
                        self.github_client and request.evaluation_url
                    ),
                },
            )

        except Exception as e:
            # Log complete error details to main logger
            logger.error(f"Error in build process: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(
                f"Request details: {request.model_dump_json(exclude={'secret'})}"
            )
            logger.error(f"Session ID: {session_id}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")

            # Log error summary to Telegram
            telegram_logger.log_error(
                f"Build process failed for {request.task}",
                context={
                    "task": request.task,
                    "round": request.round,
                    "email": request.email,
                    "brief_preview": request.brief[:100] + "..."
                    if len(request.brief) > 100
                    else request.brief,
                    "num_checks": len(request.checks),
                    "num_attachments": len(request.attachments),
                    "error_type": type(e).__name__,
                },
                exception=e,
            )

            telegram_logger.end_session(
                session_id,
                request.task,
                False,
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "session_id": session_id,
                },
            )

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
                telegram_logger.log_warning(
                    f"⚠️ GitHub client not available for {repo_name}",
                    {"repo_name": repo_name, "round": round_num},
                )
                return {"success": False, "error": "GitHub client not available"}

            logger.info(f"Enhancing repository {repo_name} with AI agent...")

            telegram_logger.log_info(
                f"🤖 Starting AI agent enhancement for {repo_name}",
                {
                    "repo_name": repo_name,
                    "round": round_num,
                    "brief_length": len(brief),
                    "num_checks": len(checks),
                    "num_attachments": len(attachments_data),
                },
            )

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
                telegram_logger.log_info(
                    f"✅ AI agent successfully enhanced {repo_name}",
                    {
                        "repo_name": repo_name,
                        "round": round_num,
                        "files_modified": result.get("files_modified", []),
                        "files_created": result.get("files_created", []),
                        "files_deleted": result.get("files_deleted", []),
                    },
                )
            else:
                logger.warning(
                    f"AI agent completed with issues: {result.get('message', 'Unknown error')}"
                )
                telegram_logger.log_warning(
                    f"⚠️ AI agent completed with issues for {repo_name}",
                    {
                        "repo_name": repo_name,
                        "round": round_num,
                        "error": result.get("error"),
                        "message": result.get("message"),
                    },
                )

            return result

        except Exception as e:
            logger.error(f"Error enhancing repository with agent: {str(e)}")
            telegram_logger.log_error(
                f"AI agent enhancement failed for {repo_name}",
                context={
                    "repo_name": repo_name,
                    "round": round_num,
                    "operation": "enhance_with_agent",
                },
                exception=e,
            )
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

    async def upload_files_single_commit(
        self, repo, app_files: dict, is_first_round: bool
    ):
        """Upload all files in a single commit using Git API."""
        try:
            # Get the main branch
            default_branch = repo.default_branch or "main"

            # Get the latest commit SHA and base tree
            try:
                ref = repo.get_git_ref(f"heads/{default_branch}")
                latest_commit_sha = ref.object.sha
                base_tree = repo.get_git_commit(latest_commit_sha).tree
            except Exception:
                # Empty repo or no base tree
                latest_commit_sha = None
                base_tree = None

            # Prepare all files to upload
            files_to_upload = []

            # 1. Add app files
            for filename, content in app_files.items():
                # Determine if content is binary or text
                if isinstance(content, bytes):
                    files_to_upload.append(
                        {"path": filename, "content": content, "encoding": "base64"}
                    )
                else:
                    files_to_upload.append(
                        {"path": filename, "content": content, "encoding": "utf-8"}
                    )

            # 2. Add GitHub Actions workflow for Pages (only on first round)
            if is_first_round:
                workflow_content = self.get_github_pages_workflow()
                files_to_upload.append(
                    {
                        "path": ".github/workflows/pages.yml",
                        "content": workflow_content,
                        "encoding": "utf-8",
                    }
                )

            # Create blobs for all files
            element_list = []
            for file_info in files_to_upload:
                # Handle different content types properly
                if file_info["encoding"] == "base64":
                    # For binary content, encode as base64
                    content_b64 = base64.b64encode(file_info["content"]).decode("utf-8")
                    blob = repo.create_git_blob(content_b64, "base64")
                else:
                    # For text content, use UTF-8
                    blob = repo.create_git_blob(file_info["content"], "utf-8")

                element = {
                    "path": file_info["path"],
                    "mode": "100644",  # File mode
                    "type": "blob",
                    "sha": blob.sha,
                }
                element_list.append(element)
                logger.info(
                    f"Prepared file: {file_info['path']} ({file_info['encoding']})"
                )

            # Create tree
            if base_tree:
                tree = repo.create_git_tree(element_list, base_tree)
            else:
                tree = repo.create_git_tree(element_list)

            # Create commit
            commit_message = f"{'Initial commit' if is_first_round else 'Update'}: Add application files{'and workflow' if is_first_round else ''}"
            if latest_commit_sha:
                parent = repo.get_git_commit(latest_commit_sha)
                commit = repo.create_git_commit(commit_message, tree, [parent])
            else:
                commit = repo.create_git_commit(commit_message, tree, [])

            # Update reference
            try:
                ref = repo.get_git_ref(f"heads/{default_branch}")
                ref.edit(commit.sha)
            except Exception:
                # Create the reference if it doesn't exist
                repo.create_git_ref(f"refs/heads/{default_branch}", commit.sha)

            logger.info(
                f"Successfully uploaded {len(files_to_upload)} files in a single commit"
            )

        except Exception as e:
            logger.error(f"Error uploading files in single commit: {str(e)}")
            raise

    async def upload_files_individually(
        self, repo, app_files: dict, is_first_round: bool
    ):
        """Upload files one by one to ensure they work."""
        try:
            logger.info("Uploading files individually...")

            # Upload app files
            for filename, content in app_files.items():
                try:
                    # Check if file already exists
                    file_exists = False
                    file_sha = None
                    try:
                        file_obj = repo.get_contents(filename)
                        if file_obj and hasattr(file_obj, "sha"):
                            file_exists = True
                            file_sha = file_obj.sha
                            logger.info(f"File {filename} already exists, will update")
                        else:
                            logger.info(
                                f"File {filename} exists but no SHA found, will create"
                            )
                    except Exception:
                        file_exists = False
                        logger.info(f"File {filename} doesn't exist, will create")

                    # Prepare content based on type
                    final_content = None
                    if isinstance(content, bytes):
                        # Handle binary files (like CSV) - convert to text first
                        try:
                            # Try to decode as UTF-8 first
                            final_content = content.decode("utf-8")
                        except UnicodeDecodeError:
                            # If UTF-8 fails, use base64 encoding
                            final_content = base64.b64encode(content).decode("utf-8")
                    else:
                        # Handle text files
                        final_content = content

                    # Create or update file
                    if file_exists and file_sha:
                        repo.update_file(
                            filename, f"Update {filename}", final_content, file_sha
                        )
                        logger.info(f"Updated file: {filename}")
                    else:
                        repo.create_file(filename, f"Add {filename}", final_content)
                        logger.info(f"Created file: {filename}")

                except Exception as file_error:
                    logger.error(f"Error handling {filename}: {str(file_error)}")
                    raise

            # Add GitHub Actions workflow for Pages (only on first round)
            if is_first_round:
                workflow_content = self.get_github_pages_workflow()
                workflow_path = ".github/workflows/pages.yml"
                try:
                    repo.create_file(
                        workflow_path, "Add GitHub Pages workflow", workflow_content
                    )
                    logger.info(f"Added workflow file: {workflow_path}")
                except Exception as workflow_error:
                    if "already exists" in str(workflow_error):
                        # Update existing workflow
                        file_obj = repo.get_contents(workflow_path)
                        repo.update_file(
                            workflow_path,
                            "Update GitHub Pages workflow",
                            workflow_content,
                            file_obj.sha,
                        )
                        logger.info(f"Updated workflow file: {workflow_path}")
                    else:
                        logger.error(f"Error creating workflow: {str(workflow_error)}")
                        raise

            logger.info("Successfully uploaded all files individually")

        except Exception as e:
            logger.error(f"Error uploading files individually: {str(e)}")
            raise

    def get_github_pages_workflow(self) -> str:
        """Get the GitHub Pages workflow YAML content."""
        return """name: Deploy to GitHub Pages

on:
  push:
    branches: ["main"]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        
      - name: Setup Pages
        uses: actions/configure-pages@v5
        
      - name: Upload Artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: '.'
          
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
"""

    async def create_github_repository(
        self, task_name: str, app_files: dict, email: str = "", round_num: int = 1
    ):
        if not self.github_client:
            logger.warning("GitHub token not configured, skipping repo creation")
            return {
                "repo_name": f"{task_name}",
                "repo_url": "https://github.com/user/repo",
                "commit_sha": "abc123",
            }

        try:
            # Check if repository already exists for this task
            task_info = self.task_db.get_repo_by_task(task_name)
            user = self.github_client.get_user()
            repo_name = f"{task_name}"

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
                # Create new repository with unique name if needed
                logger.info(f"Creating new repository: {repo_name}")
                repo = None
                attempts = 0
                max_attempts = 5

                while repo is None and attempts < max_attempts:
                    try:
                        repo = user.create_repo(
                            repo_name,
                            description=f"Auto-generated web application for {task_name}",
                            private=False,
                            auto_init=False,  # Don't auto-init to avoid conflicts
                        )
                        logger.info(f"Successfully created repository: {repo_name}")
                    except Exception as create_error:
                        if "already exists" in str(create_error):
                            # Generate unique name with timestamp
                            timestamp = str(int(time.time()))[
                                -6:
                            ]  # Last 6 digits of timestamp
                            repo_name = f"{task_name}-{timestamp}"
                            logger.info(
                                f"Repository exists, trying with unique name: {repo_name}"
                            )
                            attempts += 1
                        else:
                            logger.error(
                                f"Error creating repository: {str(create_error)}"
                            )
                            raise

                if repo is None:
                    raise Exception(
                        f"Failed to create repository after {max_attempts} attempts"
                    )

            # Upload files only if there are files to upload (skip for round 2 without new files)
            if app_files:
                await self.upload_files_individually(repo, app_files, round_num == 1)
                logger.info(f"Uploaded {len(app_files)} files for round {round_num}")
            else:
                logger.info(f"Round {round_num}: No files to upload, repository exists")

            # Enable GitHub Pages for the repository (only for round 1)
            if round_num == 1:
                await self.enable_github_pages_api(repo)

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

    async def enable_github_pages_api(self, repo):
        """Enable GitHub Pages using GitHub API."""
        try:
            logger.info(f"Enabling GitHub Pages for repository: {repo.name}")

            # Use GitHub API to enable Pages
            # We need to use the raw API since PyGithub doesn't have direct Pages support

            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            # Enable Pages with GitHub Actions as source
            pages_config = {
                "source": {"branch": "main", "path": "/"},
                "build_type": "workflow",  # Use GitHub Actions workflow
            }

            url = f"https://api.github.com/repos/{repo.full_name}/pages"

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=pages_config, headers=headers)

                if response.status_code == 201:
                    logger.info("GitHub Pages enabled successfully")
                elif response.status_code == 409:
                    logger.info("GitHub Pages already enabled")
                else:
                    logger.warning(
                        f"Pages enablement returned status: {response.status_code}"
                    )
                    logger.debug(f"Response: {response.text}")

        except Exception as e:
            logger.warning(f"Could not enable GitHub Pages via API: {str(e)}")
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

        # Log complete payload to main logger
        logger.info(
            f"Posting evaluation results: {evaluation_payload.model_dump_json()}"
        )

        # Log summary to Telegram
        telegram_logger.log_info(
            f"📤 Posting evaluation results for {request.task}",
            {
                "task": request.task,
                "round": request.round,
                "email": request.email,
                "repo_url": repo_info["repo_url"],
                "commit_sha": repo_info["commit_sha"],
                "pages_url": pages_url,
                "evaluation_url": str(request.evaluation_url),
                "nonce": request.nonce,
            },
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
                        # Log complete response to main logger
                        logger.info(
                            f"Successfully posted evaluation results (attempt {attempt + 1})"
                        )
                        logger.info(f"Response status: {response.status_code}")
                        logger.info(f"Response headers: {dict(response.headers)}")
                        logger.info(f"Response body: {response.text}")

                        # Log summary to Telegram
                        telegram_logger.log_info(
                            f"✅ Successfully posted evaluation results for {request.task}",
                            {
                                "task": request.task,
                                "attempt": attempt + 1,
                                "status_code": response.status_code,
                                "response_body": response.text[:500] + "..."
                                if len(response.text) > 500
                                else response.text,
                                "evaluation_payload": evaluation_payload.model_dump(),
                            },
                        )
                        return
                    else:
                        # Log failed response to main logger
                        logger.warning(
                            f"Evaluation URL returned {response.status_code}, retrying..."
                        )
                        logger.warning(f"Response body: {response.text}")
                        logger.warning(f"Response headers: {dict(response.headers)}")

            except Exception as e:
                # Log complete error to main logger
                logger.error(
                    f"Error posting to evaluation URL (attempt {attempt + 1}): {str(e)}"
                )
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(
                    f"Evaluation payload: {evaluation_payload.model_dump_json()}"
                )
                logger.error(f"Target URL: {request.evaluation_url}")

                if attempt < max_retries - 1:
                    telegram_logger.log_retry(
                        attempt + 1,
                        max_retries,
                        f"posting evaluation results for {request.task}",
                        str(e),
                    )

            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay *= 2  # Exponential backoff

        # Log complete failure details to main logger
        logger.error("Failed to post evaluation results after all retries")
        logger.error(
            f"Final payload that failed: {evaluation_payload.model_dump_json()}"
        )
        logger.error(f"Target URL: {request.evaluation_url}")
        logger.error(f"Max retries attempted: {max_retries}")

        # Log summary to Telegram
        telegram_logger.log_error(
            f"Failed to post evaluation results for {request.task} after {max_retries} attempts",
            {
                "task": request.task,
                "round": request.round,
                "max_retries": max_retries,
                "evaluation_url": str(request.evaluation_url),
                "final_payload": evaluation_payload.model_dump(),
            },
        )


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
        # Log complete request details to main logger
        logger.info(
            f"Received build request for task: {request.task}, round: {request.round}"
        )
        logger.info(
            f"Complete request details: {request.model_dump_json(exclude={'secret'})}"
        )

        # Prepare attachment summary for Telegram
        attachment_names = (
            [att.name for att in request.attachments] if request.attachments else []
        )

        # Log API request to Telegram (summary version)
        telegram_logger.log_info(
            f"🚀 New build request: {request.task}",
            {
                "task": request.task,
                "round": request.round,
                "email": request.email,
                "brief": request.brief,
                "checks": request.checks,
                "attachment_names": attachment_names,
                "num_attachments": len(request.attachments),
                "evaluation_url": str(request.evaluation_url)
                if request.evaluation_url
                else None,
                "nonce": request.nonce,
            },
        )

        # Validate secret
        if not app_builder.validate_secret(request.secret):
            telegram_logger.log_warning(
                f"🔐 Invalid secret provided for task: {request.task}",
                {"task": request.task, "round": request.round, "email": request.email},
            )
            raise HTTPException(status_code=401, detail="Invalid secret")

        # Add the build process to background tasks
        background_tasks.add_task(app_builder.process_build_request, request)

        return BuildResponse(
            status="accepted",
            message="Build request accepted and processing started",
            task=request.task,
            round=request.round,
        )

    except HTTPException as he:
        # Re-raise HTTP exceptions as-is
        raise he
    except Exception as e:
        logger.error(f"Error processing build request: {str(e)}")
        telegram_logger.log_error(
            f"API endpoint error for task: {request.task}",
            context={
                "task": request.task,
                "round": request.round,
                "endpoint": "/build",
            },
            exception=e,
        )
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    import signal
    import sys

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

    # Graceful shutdown handler
    def signal_handler(sig, frame):
        print("\nShutting down gracefully...")
        telegram_logger.log_info("🛑 Website Developer API shutting down")
        telegram_logger.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"Starting Website Developer API on {host}:{port}")

    # Log startup
    telegram_logger.log_info(
        "🚀 Website Developer API starting up",
        {
            "host": host,
            "port": port,
            "github_token_configured": bool(github_token),
            "api_secret_configured": bool(api_secret),
        },
    )

    try:
        uvicorn.run("main:app", host=host, port=port)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    finally:
        telegram_logger.shutdown()
