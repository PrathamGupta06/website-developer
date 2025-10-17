import os
import asyncio
import httpx
import logging
from github import Github
from models import BuildRequest
from agent import AgentTools, WebsiteAgent
from db import TaskRepository
import base64


logger = logging.getLogger(__name__)


class AppBuilder:
    """
    Main class responsible for building web applications based on requests.
    Implements the complete 6-phase application flow.
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
        Complete 6-phase application flow.

        Phase 1: Request Processing & Validation ✓
        Phase 2: Repository Setup (Round 1 Only)
        Phase 3: Context Gathering (All Rounds)
        Phase 4: LLM Agent Execution
        Phase 5: Repository Updates
        Phase 6: Deployment & Evaluation
        """
        try:
            logger.info(
                f"Starting build process for {request.task}, round {request.round}"
            )

            # Phase 1: Request Processing & Validation (already done in endpoint)
            attachments_data = await self.process_attachments(request.attachments)

            # Phase 2: Repository Setup (Round 1 Only)
            repo = None
            if request.round == 1:
                repo = await self.setup_repository(request.task, attachments_data)
            else:
                repo = await self.get_existing_repository(request.task)

            # Phase 3: Context Gathering (All Rounds)
            context = await self.gather_context(request, attachments_data, repo)

            # Phase 4: LLM Agent Execution
            agent_result = await self.execute_agent(context, repo)

            # Phase 5: Repository Updates
            await self.update_repository_with_changes(repo, agent_result)

            # Phase 6: Deployment & Evaluation
            await self.deploy_and_evaluate(request, repo)

            logger.info(
                f"Successfully completed build for {request.task}, round {request.round}"
            )

        except Exception as e:
            logger.error(f"Error in build process: {str(e)}")
            raise

    # Phase 2: Repository Setup Methods
    async def setup_repository(self, task_name: str, attachments_data: list):
        """Create new repository with starter template for round 1."""
        if not self.github_client:
            logger.warning("GitHub token not configured, skipping repo creation")
            return None

        try:
            # Create unique repo name using task ID
            repo_name = f"generated-{task_name}"
            logger.info(f"Creating repository: {repo_name}")

            # Create repository
            user = self.github_client.get_user()
            repo = user.create_repo(
                repo_name,
                description=f"Auto-generated web application for {task_name}",
                private=False,
                auto_init=False,  # We'll add our own files
            )

            # Upload starter template files
            await self.upload_starter_template(repo)

            # Upload attachments to attachments/ folder
            if attachments_data:
                await self.upload_attachments(repo, attachments_data)

            # Enable GitHub Pages
            await self.enable_github_pages(repo)

            logger.info(f"Repository created successfully: {repo.html_url}")
            return repo

        except Exception as e:
            logger.error(f"Error creating GitHub repository: {str(e)}")
            raise

    async def get_existing_repository(self, task_name: str):
        """Get existing repository for round 2+ using task ID from CSV database."""
        if not self.github_client:
            logger.warning("GitHub token not configured")
            return None

        try:
            # Look up repository by task ID in CSV database
            task_info = self.task_db.get_repo_by_task(task_name)

            if not task_info:
                logger.error(f"No existing repository found for task: {task_name}")
                raise Exception(f"No existing repository found for task: {task_name}")

            # Get the repository object from GitHub
            user = self.github_client.get_user()
            repo = self.github_client.get_repo(f"{user.login}/{task_info['repo_name']}")

            logger.info(
                f"Found existing repository: {repo.name} (Round {task_info['latest_round']})"
            )
            return repo

        except Exception as e:
            logger.error(f"Error finding existing repository: {str(e)}")
            raise

    async def upload_starter_template(self, repo):
        """Upload starter template files to repository."""
        template_files = {
            "index.html": self.load_starter_file("index.html"),
            "style.css": self.load_starter_file("style.css"),
            "script.js": self.load_starter_file("script.js"),
            "README.md": self.load_starter_file("README.md"),
            "LICENSE": self.load_starter_file("LICENSE"),
        }

        for filename, content in template_files.items():
            if content:
                repo.create_file(
                    path=filename, message=f"Add {filename}", content=content
                )
                logger.info(f"Uploaded starter file: {filename}")

    def load_starter_file(self, filename: str) -> str:
        """Load starter template file content."""
        try:
            starter_path = os.path.join("repository_starter", filename)
            with open(starter_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading starter file {filename}: {str(e)}")
            return ""

    async def upload_attachments(self, repo, attachments_data: list):
        """Upload attachments to attachments/ folder."""
        for attachment in attachments_data:
            try:
                file_path = f"attachments/{attachment['name']}"
                repo.create_file(
                    path=file_path,
                    message=f"Add attachment {attachment['name']}",
                    content=attachment["data"],
                )
                logger.info(f"Uploaded attachment: {attachment['name']}")
            except Exception as e:
                logger.error(
                    f"Error uploading attachment {attachment['name']}: {str(e)}"
                )

    # Phase 3: Context Gathering Methods
    async def gather_context(
        self, request: BuildRequest, attachments_data: list, repo
    ) -> dict:
        """Gather all context needed for LLM agent."""
        context = {
            "task": request.task,
            "round": request.round,
            "brief": request.brief,
            "checks": request.checks,
            "attachments": attachments_data,
            "repo_name": repo.name if repo else None,
            "repo_url": repo.html_url if repo else None,
        }

        if request.round > 1 and repo:
            # For round 2+, get current repository state
            context["current_repo_state"] = await self.get_repository_state(repo)

        return context

    async def get_repository_state(self, repo) -> dict:
        """Get current repository structure and content."""
        try:
            # Get repository tree
            contents = repo.get_contents("")

            repo_state = {"files": [], "directories": [], "file_contents": {}}

            def process_contents(contents_list, path=""):
                for item in contents_list:
                    if item.type == "file":
                        repo_state["files"].append(
                            {"name": item.name, "path": item.path, "size": item.size}
                        )

                        # Get content for key files
                        if item.name.endswith((".html", ".js", ".css", ".md")):
                            try:
                                content = item.decoded_content.decode("utf-8")
                                repo_state["file_contents"][item.path] = content
                            except Exception as e:
                                logger.warning(
                                    f"Could not decode {item.path}: {str(e)}"
                                )

                    elif item.type == "dir":
                        repo_state["directories"].append(
                            {"name": item.name, "path": item.path}
                        )
                        # Recursively get directory contents
                        try:
                            dir_contents = repo.get_contents(item.path)
                            process_contents(dir_contents, item.path)
                        except Exception as e:
                            logger.warning(
                                f"Could not access directory {item.path}: {str(e)}"
                            )

            if isinstance(contents, list):
                process_contents(contents)
            else:
                process_contents([contents])

            return repo_state

        except Exception as e:
            logger.error(f"Error getting repository state: {str(e)}")
            return {"error": str(e)}

    # Phase 4: Agent Execution Methods
    async def execute_agent(self, context: dict, repo) -> dict:
        """Execute LLM agent with tools."""
        if not repo:
            logger.warning("No repository available for agent execution")
            return {"success": False, "error": "No repository available"}

        try:
            # Initialize agent tools
            tools = AgentTools(repo)
            agent = WebsiteAgent(tools)

            # Execute agent
            result = await agent.generate_website(context)

            logger.info(f"Agent execution completed: {result.get('success', False)}")
            return result

        except Exception as e:
            logger.error(f"Error executing agent: {str(e)}")
            return {"success": False, "error": str(e)}

    # Phase 5: Repository Updates Methods
    async def update_repository_with_changes(self, repo, agent_result: dict):
        """Commit any changes made by the agent."""
        if not repo or not agent_result.get("success"):
            logger.warning(
                "Skipping repository update - no repo or failed agent execution"
            )
            return

        try:
            # The agent tools already handle individual file commits
            # This method could be used for batch operations or cleanup
            logger.info("Repository updates completed by agent tools")

        except Exception as e:
            logger.error(f"Error updating repository: {str(e)}")
            raise

    # Phase 6: Deployment & Evaluation Methods
    async def deploy_and_evaluate(self, request: BuildRequest, repo):
        """Deploy to GitHub Pages and save task-repo mapping to CSV."""
        if not repo:
            logger.warning("No repository available for deployment")
            return

        try:
            # Wait for Pages to be ready
            pages_url = await self.wait_for_pages_deployment(repo)

            # Get latest commit SHA
            commit_sha = repo.get_commits()[0].sha

            # Save task-repository mapping to CSV database
            self.task_db.save_task_repo(
                task=request.task,
                email=request.email,
                repo_name=repo.name,
                repo_url=repo.html_url,
                commit_sha=commit_sha,
                pages_url=pages_url,
                round_num=request.round,
            )
            logger.info(
                f"Saved task-repo mapping for {request.task}, round {request.round}"
            )

            # Skip evaluation as per requirements
            logger.info(f"Skipping evaluation for task {request.task}")

        except Exception as e:
            logger.error(f"Error in deployment: {str(e)}")
            raise

    async def wait_for_pages_deployment(self, repo) -> str:
        """Wait for GitHub Actions workflow to complete and Pages to be ready."""
        if not self.github_client:
            return f"https://user.github.io/{repo.name}/"

        user_login = self.github_client.get_user().login
        pages_url = f"https://{user_login}.github.io/{repo.name}/"

        logger.info("Waiting for GitHub Actions workflow to complete...")

        # Step 1: Wait for workflow to complete
        workflow_completed = await self.wait_for_workflow_completion(repo)

        if not workflow_completed:
            logger.warning(
                "Workflow did not complete in time, but will try to access Pages"
            )
        else:
            logger.info("GitHub Actions workflow completed successfully")

        # Step 2: Wait for Pages to be accessible
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

    async def wait_for_workflow_completion(self, repo, timeout: int = 300) -> bool:
        """
        Wait for the GitHub Actions workflow to complete.

        Args:
            repo: GitHub repository object
            timeout: Maximum time to wait in seconds (default: 5 minutes)

        Returns:
            True if workflow completed successfully, False otherwise
        """
        try:
            import time as time_module

            start_time = time_module.time()

            # Get the latest workflow run
            logger.info(f"Checking workflow runs for repository: {repo.name}")

            # Wait a bit for the workflow to start
            await asyncio.sleep(5)

            while time_module.time() - start_time < timeout:
                try:
                    # Get workflow runs for the repository
                    workflows = repo.get_workflow_runs()

                    if workflows.totalCount > 0:
                        latest_run = workflows[0]  # Get the most recent workflow run

                        logger.info(
                            f"Workflow status: {latest_run.status}, "
                            f"conclusion: {latest_run.conclusion}"
                        )

                        # Check if workflow is completed
                        if latest_run.status == "completed":
                            if latest_run.conclusion == "success":
                                logger.info("Workflow completed successfully!")
                                return True
                            else:
                                logger.warning(
                                    f"Workflow completed with conclusion: {latest_run.conclusion}"
                                )
                                return False

                        # Workflow is still in progress
                        logger.info(f"Workflow still {latest_run.status}, waiting...")
                    else:
                        logger.info("No workflow runs found yet, waiting...")

                except Exception as e:
                    logger.debug(f"Error checking workflow status: {str(e)}")

                # Wait before checking again
                await asyncio.sleep(10)

            logger.warning(f"Workflow did not complete within {timeout} seconds")
            return False

        except Exception as e:
            logger.error(f"Error waiting for workflow completion: {str(e)}")
            return False

    # NOTE: Evaluation methods kept for future use but currently skipped
    # async def post_evaluation_results_with_retry(
    #     self, evaluation_url, payload: EvaluationPayload
    # ):
    #     """Post results to evaluation URL with retry logic."""
    #     max_retries = 5
    #     delay = 1
    #
    #     for attempt in range(max_retries):
    #         try:
    #             async with httpx.AsyncClient() as client:
    #                 response = await client.post(
    #                     str(evaluation_url),
    #                     json=payload.dict(),
    #                     headers={"Content-Type": "application/json"},
    #                     timeout=30.0,
    #                 )
    #
    #                 if response.status_code == 200:
    #                     logger.info(
    #                         f"Successfully posted evaluation results (attempt {attempt + 1})"
    #                     )
    #                     return
    #                 else:
    #                     logger.warning(
    #                         f"Evaluation URL returned {response.status_code}, retrying..."
    #                     )
    #
    #         except Exception as e:
    #             logger.error(
    #                 f"Error posting to evaluation URL (attempt {attempt + 1}): {str(e)}"
    #             )
    #
    #         if attempt < max_retries - 1:
    #             await asyncio.sleep(delay)
    #             delay *= 2  # Exponential backoff
    #
    #     logger.error("Failed to post evaluation results after all retries")

    # Helper Methods for Processing
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

    async def enable_github_pages(self, repo):
        """Enable GitHub Pages for the repository."""
        try:
            # Note: GitHub API doesn't have direct Pages creation in PyGithub
            # Pages can be enabled through repository settings or Actions
            # For now, we'll log and assume it will be set up manually or via Actions
            logger.info(f"GitHub Pages should be enabled for {repo.name}")

            # You can enable Pages via the web interface or GitHub CLI
            # The repository is public and has an index.html, so Pages will work

        except Exception as e:
            logger.error(f"Error enabling GitHub Pages: {str(e)}")
            # Don't raise here as this might not be critical
