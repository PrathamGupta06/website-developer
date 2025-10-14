import logging
from typing import List, Dict, Any
from github.Repository import Repository

logger = logging.getLogger(__name__)


class AgentTools:
    """
    Tools available to the LLM agent for repository manipulation.
    These tools allow the agent to read, update, create, and delete files in the repository.
    """

    def __init__(self, repo: Repository):
        self.repo = repo
        self.logger = logging.getLogger(__name__)

    def read_files(self, file_names: List[str]) -> Dict[str, str]:
        """
        Read the contents of specified files from the repository.

        Args:
            file_names: List of file paths to read

        Returns:
            Dictionary mapping file names to their contents
        """
        file_contents = {}

        for file_name in file_names:
            try:
                # Get file content from repository
                file_content = self.repo.get_contents(file_name)

                # Handle single file case (get_contents can return list or single item)
                if isinstance(file_content, list):
                    if len(file_content) > 0:
                        file_content = file_content[0]
                    else:
                        file_contents[file_name] = f"Error: {file_name} not found"
                        continue

                if file_content.type == "file":
                    content = file_content.decoded_content.decode("utf-8")
                    file_contents[file_name] = content
                    self.logger.info(f"Successfully read file: {file_name}")
                else:
                    file_contents[file_name] = f"Error: {file_name} is not a file"
                    self.logger.warning(f"Attempted to read non-file: {file_name}")

            except Exception as e:
                file_contents[file_name] = f"Error reading file: {str(e)}"
                self.logger.error(f"Error reading file {file_name}: {str(e)}")

        return file_contents

    def update_files(self, file_updates: List[Dict[str, str]]) -> Dict[str, bool]:
        """
        Update or create files in the repository with new content.

        Args:
            file_updates: List of dictionaries with 'file_name' and 'content' keys

        Returns:
            Dictionary mapping file names to success status
        """
        results = {}

        for update in file_updates:
            file_name = update.get("file_name")
            content = update.get("content", "")

            if not file_name:
                results[str(update)] = False
                self.logger.error("Update missing file_name")
                continue

            try:
                # Check if file exists
                try:
                    existing_file = self.repo.get_contents(file_name)

                    # Handle list case
                    if isinstance(existing_file, list):
                        if len(existing_file) > 0:
                            existing_file = existing_file[0]
                        else:
                            raise Exception("File not found")

                    # File exists, update it
                    self.repo.update_file(
                        path=file_name,
                        message=f"Update {file_name}",
                        content=content,
                        sha=existing_file.sha,
                    )
                    self.logger.info(f"Successfully updated file: {file_name}")

                except Exception:
                    # File doesn't exist, create it
                    self.repo.create_file(
                        path=file_name, message=f"Create {file_name}", content=content
                    )
                    self.logger.info(f"Successfully created file: {file_name}")

                results[file_name] = True

            except Exception as e:
                results[file_name] = False
                self.logger.error(f"Error updating file {file_name}: {str(e)}")

        return results

    def list_directory_contents(self, path: str = "") -> Dict[str, Any]:
        """
        List the contents of a directory in the repository.

        Args:
            path: Directory path to list (empty string for root)

        Returns:
            Dictionary with files and directories information
        """
        try:
            contents = self.repo.get_contents(path)

            # Handle single file case
            if not isinstance(contents, list):
                contents = [contents]

            files = []
            directories = []

            for item in contents:
                if item.type == "file":
                    files.append(
                        {
                            "name": item.name,
                            "path": item.path,
                            "size": item.size,
                            "sha": item.sha,
                        }
                    )
                elif item.type == "dir":
                    directories.append({"name": item.name, "path": item.path})

            result = {
                "path": path,
                "files": files,
                "directories": directories,
                "total_files": len(files),
                "total_directories": len(directories),
            }

            self.logger.info(f"Successfully listed directory: {path}")
            return result

        except Exception as e:
            self.logger.error(f"Error listing directory {path}: {str(e)}")
            return {"path": path, "error": str(e), "files": [], "directories": []}

    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from the repository.

        Args:
            file_path: Path to the file to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get file to get its SHA
            file_content = self.repo.get_contents(file_path)

            # Handle list case
            if isinstance(file_content, list):
                if len(file_content) > 0:
                    file_content = file_content[0]
                else:
                    raise Exception("File not found")

            # Delete the file
            self.repo.delete_file(
                path=file_path, message=f"Delete {file_path}", sha=file_content.sha
            )

            self.logger.info(f"Successfully deleted file: {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"Error deleting file {file_path}: {str(e)}")
            return False

    def get_repository_tree(self) -> Dict[str, Any]:
        """
        Get the complete directory tree structure of the repository.

        Returns:
            Nested dictionary representing the repository structure
        """
        try:
            # Get all contents recursively
            def build_tree(path=""):
                try:
                    contents = self.repo.get_contents(path)
                    if not isinstance(contents, list):
                        contents = [contents]

                    tree = {"files": [], "directories": {}}

                    for item in contents:
                        if item.type == "file":
                            tree["files"].append(
                                {
                                    "name": item.name,
                                    "path": item.path,
                                    "size": item.size,
                                }
                            )
                        elif item.type == "dir":
                            tree["directories"][item.name] = build_tree(item.path)

                    return tree

                except Exception as e:
                    return {"error": str(e), "files": [], "directories": {}}

            full_tree = build_tree()
            self.logger.info("Successfully built repository tree")
            return full_tree

        except Exception as e:
            self.logger.error(f"Error building repository tree: {str(e)}")
            return {"error": str(e), "files": [], "directories": {}}


class WebsiteAgent:
    """
    Main agent class that orchestrates website generation using LLM.
    This class will be expanded with actual LLM integration.
    """

    def __init__(self, tools: AgentTools):
        self.tools = tools
        self.logger = logging.getLogger(__name__)

    async def generate_website(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate or update website based on the provided context.

        Args:
            context: Dictionary containing all necessary information:
                - brief: Task description
                - checks: Evaluation criteria
                - round: Round number
                - attachments: List of attachment data
                - current_repo_state: Current repository structure (for round 2+)
                - task: Task identifier

        Returns:
            Dictionary with generation results and any errors
        """
        # This function will be implemented by the student with actual LLM integration
        # For now, it's a placeholder that demonstrates the expected interface

        self.logger.info(
            f"Starting website generation for round {context.get('round', 1)}"
        )

        # TODO: Implement actual LLM agent logic here
        # The agent should:
        # 1. Analyze the brief and requirements
        # 2. Use the tools to read current repository state
        # 3. Generate/update appropriate files
        # 4. Use tools to update the repository

        # Placeholder return - replace with actual implementation
        return {
            "success": True,
            "message": "Website generation placeholder - implement LLM integration here",
            "files_modified": [],
            "files_created": [],
            "files_deleted": [],
        }

    def _prepare_context_for_llm(self, context: Dict[str, Any]) -> str:
        """
        Prepare context information for LLM consumption.

        Args:
            context: Raw context dictionary

        Returns:
            Formatted context string for LLM
        """
        # TODO: Format context appropriately for your chosen LLM

        formatted_context = f"""
Task: {context.get("task", "Unknown")}
Round: {context.get("round", 1)}
Brief: {context.get("brief", "")}

Requirements to fulfill:
"""

        for i, check in enumerate(context.get("checks", []), 1):
            formatted_context += f"{i}. {check}\n"

        if context.get("attachments"):
            formatted_context += (
                f"\nAttachments available: {len(context['attachments'])} files\n"
            )
            for att in context["attachments"]:
                formatted_context += f"- {att['name']}\n"

        if context.get("current_repo_state"):
            formatted_context += "\nCurrent repository structure:\n"
            formatted_context += str(context["current_repo_state"])

        return formatted_context

    def _extract_tool_calls_from_response(
        self, llm_response: str
    ) -> List[Dict[str, Any]]:
        """
        Extract tool calls from LLM response.

        Args:
            llm_response: Raw response from LLM

        Returns:
            List of tool calls to execute
        """
        # TODO: Implement parsing logic based on your LLM's output format
        # This should extract structured tool calls from the LLM response

        return []

    async def _execute_tool_calls(
        self, tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute a list of tool calls using the available tools.

        Args:
            tool_calls: List of tool call dictionaries

        Returns:
            List of tool execution results
        """
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call.get("tool")
            tool_args = tool_call.get("args", {})

            try:
                if tool_name == "read_files":
                    result = self.tools.read_files(tool_args.get("file_names", []))
                elif tool_name == "update_files":
                    result = self.tools.update_files(tool_args.get("file_updates", []))
                elif tool_name == "list_directory_contents":
                    result = self.tools.list_directory_contents(
                        tool_args.get("path", "")
                    )
                elif tool_name == "delete_file":
                    result = self.tools.delete_file(tool_args.get("file_path", ""))
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}

                results.append({"tool": tool_name, "success": True, "result": result})

            except Exception as e:
                results.append({"tool": tool_name, "success": False, "error": str(e)})
                self.logger.error(f"Error executing tool {tool_name}: {str(e)}")

        return results
