import logging
from typing import List, Dict, Any
from github.Repository import Repository
from langchain.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv(override=True)


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

    def get_repository_context(self, max_chars: int = 2000) -> str:
        """
        Get current repository files content up to max_chars limit.

        Args:
            max_chars: Maximum characters to include in context

        Returns:
            Formatted string with file contents
        """
        try:
            context_parts = []
            char_count = 0

            # Always include README.md first if it exists
            try:
                readme_content = self.repo.get_contents("README.md")
                if hasattr(readme_content, "decoded_content"):
                    content = readme_content.decoded_content.decode("utf-8")
                    file_section = f"## README.md\n```\n{content}\n```\n\n"
                    if char_count + len(file_section) <= max_chars:
                        context_parts.append(file_section)
                        char_count += len(file_section)
            except Exception:
                pass  # README.md doesn't exist

            # Get all files in root directory
            try:
                contents = self.repo.get_contents("")
                if not isinstance(contents, list):
                    contents = [contents]

                # Sort files by priority (common web files first)
                priority_files = ["index.html", "script.js", "style.css"]
                other_files = [
                    item
                    for item in contents
                    if item.type == "file"
                    and item.name not in priority_files
                    and item.name != "README.md"
                ]

                # Process priority files first, then others
                for filename in priority_files:
                    for item in contents:
                        if item.type == "file" and item.name == filename:
                            try:
                                if char_count >= max_chars:
                                    break

                                # Skip binary files entirely
                                if self._is_binary_file(item.name):
                                    self.logger.debug(
                                        f"Skipping binary file: {item.name}"
                                    )
                                    break

                                content = item.decoded_content.decode("utf-8")

                                # Truncate large files to 500 characters
                                if len(content) > 500:
                                    content = content[:500] + "...[truncated]"

                                file_section = (
                                    f"## {item.name}\n```\n{content}\n```\n\n"
                                )
                                if char_count + len(file_section) <= max_chars:
                                    context_parts.append(file_section)
                                    char_count += len(file_section)
                                else:
                                    # Truncate content to fit remaining space
                                    remaining_chars = (
                                        max_chars
                                        - char_count
                                        - len(f"## {item.name}\n```\n...\n```\n\n")
                                    )
                                    if remaining_chars > 50:
                                        truncated_content = (
                                            content[:remaining_chars] + "..."
                                        )
                                        context_parts.append(
                                            f"## {item.name}\n```\n{truncated_content}\n```\n\n"
                                        )
                                        char_count = max_chars
                                    break
                            except Exception as e:
                                self.logger.debug(
                                    f"Could not read {item.name}: {str(e)}"
                                )

                # Process other files if space remains
                for item in other_files:
                    if char_count >= max_chars:
                        break
                    try:
                        # Skip binary files entirely
                        if self._is_binary_file(item.name):
                            self.logger.debug(f"Skipping binary file: {item.name}")
                            continue

                        # Skip extremely large files (probably generated/minified)
                        if item.size > 100000:  # Skip files larger than 100KB
                            self.logger.debug(
                                f"Skipping large file: {item.name} ({item.size} bytes)"
                            )
                            continue

                        content = item.decoded_content.decode("utf-8")

                        # Truncate large files to 500 characters
                        if len(content) > 500:
                            content = content[:500] + "...[truncated]"

                        file_section = f"## {item.name}\n```\n{content}\n```\n\n"
                        if char_count + len(file_section) <= max_chars:
                            context_parts.append(file_section)
                            char_count += len(file_section)
                        else:
                            break
                    except Exception as e:
                        self.logger.debug(f"Could not read {item.name}: {str(e)}")

            except Exception as e:
                self.logger.error(f"Error getting repository contents: {str(e)}")

            return "".join(context_parts)

        except Exception as e:
            self.logger.error(f"Error getting repository context: {str(e)}")
            return "Error reading repository context"

    def _is_binary_file(self, filename: str) -> bool:
        """
        Check if a file is likely to be binary based on its extension.

        Args:
            filename: Name of the file to check

        Returns:
            True if file is likely binary, False otherwise
        """
        binary_extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".ico",
            ".tiff",
            ".webp",  # Images
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",  # Documents
            ".zip",
            ".tar",
            ".gz",
            ".bz2",
            ".7z",
            ".rar",  # Archives
            ".exe",
            ".dll",
            ".so",
            ".dylib",  # Executables
            ".mp3",
            ".mp4",
            ".avi",
            ".mov",
            ".wav",
            ".flac",  # Media
            ".bin",
            ".dat",
            ".db",
            ".sqlite",
            ".sqlite3",  # Data files
            ".woff",
            ".woff2",
            ".ttf",
            ".otf",
            ".eot",  # Fonts
        }

        # Get file extension
        extension = "." + filename.lower().split(".")[-1] if "." in filename else ""
        return extension in binary_extensions

    def get_formatted_directory_tree(self, path: str = "", prefix: str = "") -> str:
        """
        Get repository directory structure as a formatted tree.

        Args:
            path: Directory path to start from
            prefix: Prefix for tree formatting

        Returns:
            Formatted tree string
        """
        try:
            tree_lines = []
            contents = self.repo.get_contents(path)

            if not isinstance(contents, list):
                contents = [contents]

            # Sort contents: directories first, then files
            directories = [item for item in contents if item.type == "dir"]
            files = [item for item in contents if item.type == "file"]

            all_items = directories + files

            for i, item in enumerate(all_items):
                is_last = i == len(all_items) - 1
                connector = "└── " if is_last else "├── "
                tree_lines.append(f"{prefix}{connector}{item.name}")

                if item.type == "dir":
                    # Recursively get subdirectory contents
                    extension = "    " if is_last else "│   "
                    subtree = self.get_formatted_directory_tree(
                        item.path, prefix + extension
                    )
                    if subtree:
                        tree_lines.append(subtree)

            return "\n".join(tree_lines)

        except Exception as e:
            self.logger.error(f"Error getting directory tree: {str(e)}")
            return f"Error reading directory structure: {str(e)}"


class WebsiteAgent:
    """
    Main agent class that orchestrates website generation using LLM.
    This class will be expanded with actual LLM integration.
    """

    def __init__(self, tools: AgentTools):
        self.tools = tools
        self.logger = logging.getLogger(__name__)
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
        agent_tools = [
            tool(self.tools.read_files),
            tool(self.tools.update_files),
            tool(self.tools.list_directory_contents),
            tool(self.tools.delete_file),
            tool(self.tools.get_repository_tree),
            tool(self.tools.get_repository_context),
            tool(self.tools.get_formatted_directory_tree),
        ]

        self.agent = create_react_agent(
            model=self.llm,
            tools=agent_tools,
        )

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

        self.logger.info(
            f"Starting website generation for round {context.get('round', 1)}"
        )

        SYSTEM_PROMPT = """
You will be provided with the repository context and a directory tree. This context is the authoritative current
state of the repository. The human message will include two tagged sections:

1) <current_repository_context>...</current_repository_context>  - contains up to ~2000 characters of key
files (README.md and other important files) in code blocks. Use that to understand existing code.

2) <current_directory_structure>...</current_directory_structure> - a formatted tree of the repo layout.

Your responsibilities (follow exactly, word-for-word):
- Read the brief and all checks carefully and prioritize them above all else.
- Inspect attachment files (CSV or other data files). For CSVs, validate the header and a few example rows
to ensure you understand the data shape before using it.
- Use the provided repository context and directory tree as your working state. Do not assume files not
included in the context exist; use tools to read additional files if needed.
- Only modify repository files necessary to satisfy the brief and checks. Do NOT modify the existing
GitHub Actions workflow at `.github/workflows/pages.yml`.
- Produce clean, well-structured, idiomatic code. Make minimal, focused changes with clear intent.
- After making code changes, update or create a high-quality `README.md` that includes: summary, setup,
usage, code explanation, and license. The README must be detailed and helpful for reviewers and graders.
- When updating files, ensure you include comments where non-obvious logic is added.

Output and tool usage rules:
- Use the provided tools to read or update files. If you need to examine more files than provided in the
<current_repository_context>, call the read_files tool for the exact file path.
- When you finish all changes, create or update `README.md` to document what you changed and why, and how
to run and test the project locally.
- If you encounter CSV or other data attachments, report briefly (1-3 lines) your interpretation of the
schema and any assumptions you make before using them.

Quality gates:
- Code must aim to pass the checks exactly. Pay attention to edge cases, null values, and input formats.
- Keep changes minimal and well-tested. If you add JS/HTML/CSS, make them robust against missing data.

Final README expectations:
- Concise summary of the app and what changed
- Clear setup steps (how to open locally or what the Pages URL will show)
- Usage examples including how to use attachments or URL query params if applicable
- Code explanation (files changed and why)
- License section (MIT)

Follow these instructions exactly. Use the tools to inspect the current repo state when in doubt.
"""

        inputs = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=self._prepare_context_for_llm(context)),
        ]

        for chunk in self.agent.stream({"messages": inputs}, stream_mode="values"):
            chunk["messages"][-1].pretty_print()

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

        # Add current repository context
        try:
            repo_context = self.tools.get_repository_context(10000)
            if repo_context.strip():
                formatted_context += f"\n<current_repository_context>\n{repo_context}</current_repository_context>\n"
        except Exception as e:
            self.logger.warning(f"Could not get repository context: {str(e)}")

        # Add directory structure
        try:
            directory_tree = self.tools.get_formatted_directory_tree()
            if directory_tree.strip():
                formatted_context += f"\n<current_directory_structure>\n{directory_tree}\n</current_directory_structure>\n"
        except Exception as e:
            self.logger.warning(f"Could not get directory structure: {str(e)}")

        return formatted_context

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
