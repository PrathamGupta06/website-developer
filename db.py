import csv
import os
import logging
from typing import Optional, Dict
from threading import Lock

logger = logging.getLogger(__name__)


class TaskRepository:
    """
    Simple CSV-based storage for task-repository mappings.
    Thread-safe for concurrent access.
    """

    def __init__(self, csv_file: str = "task_repos.csv"):
        self.csv_file = csv_file
        self.lock = Lock()
        self._initialize_csv()

    def _initialize_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.csv_file):
            with self.lock:
                with open(self.csv_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "task",
                            "email",
                            "repo_name",
                            "repo_url",
                            "latest_commit_sha",
                            "pages_url",
                            "latest_round",
                            "created_at",
                            "updated_at",
                        ],
                    )
                    writer.writeheader()
            logger.info(f"Initialized CSV database: {self.csv_file}")

    def save_task_repo(
        self,
        task: str,
        email: str,
        repo_name: str,
        repo_url: str,
        commit_sha: str,
        pages_url: str,
        round_num: int,
    ) -> bool:
        """
        Save or update task-repository mapping.

        Args:
            task: Unique task ID
            email: Student email
            repo_name: GitHub repository name
            repo_url: GitHub repository URL
            commit_sha: Latest commit SHA
            pages_url: GitHub Pages URL
            round_num: Round number (1, 2, etc.)

        Returns:
            True if successful, False otherwise
        """
        import time

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        with self.lock:
            try:
                # Read existing data
                existing_tasks = {}
                if os.path.exists(self.csv_file):
                    with open(self.csv_file, "r", newline="", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            existing_tasks[row["task"]] = row

                # Update or create new entry
                if task in existing_tasks:
                    # Update existing task
                    existing_tasks[task].update(
                        {
                            "latest_commit_sha": commit_sha,
                            "latest_round": str(round_num),
                            "updated_at": timestamp,
                        }
                    )
                    logger.info(
                        f"Updated task {task} to round {round_num}, commit {commit_sha}"
                    )
                else:
                    # Create new entry
                    existing_tasks[task] = {
                        "task": task,
                        "email": email,
                        "repo_name": repo_name,
                        "repo_url": repo_url,
                        "latest_commit_sha": commit_sha,
                        "pages_url": pages_url,
                        "latest_round": str(round_num),
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                    logger.info(
                        f"Created new task {task} with repo {repo_name}, round {round_num}"
                    )

                # Write back to CSV
                with open(self.csv_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "task",
                            "email",
                            "repo_name",
                            "repo_url",
                            "latest_commit_sha",
                            "pages_url",
                            "latest_round",
                            "created_at",
                            "updated_at",
                        ],
                    )
                    writer.writeheader()
                    for row in existing_tasks.values():
                        writer.writerow(row)

                return True

            except Exception as e:
                logger.error(f"Error saving task-repo mapping: {str(e)}")
                return False

    def get_repo_by_task(self, task: str) -> Optional[Dict[str, str]]:
        """
        Get repository information by task ID.

        Args:
            task: Unique task ID

        Returns:
            Dictionary with repo info or None if not found
        """
        with self.lock:
            try:
                if not os.path.exists(self.csv_file):
                    return None

                with open(self.csv_file, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["task"] == task:
                            logger.info(
                                f"Found repository for task {task}: {row['repo_name']}"
                            )
                            return row

                logger.warning(f"No repository found for task {task}")
                return None

            except Exception as e:
                logger.error(f"Error reading task-repo mapping: {str(e)}")
                return None

    def get_all_tasks(self) -> list:
        """
        Get all task-repository mappings.

        Returns:
            List of dictionaries with all task-repo mappings
        """
        with self.lock:
            try:
                if not os.path.exists(self.csv_file):
                    return []

                with open(self.csv_file, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    return list(reader)

            except Exception as e:
                logger.error(f"Error reading all tasks: {str(e)}")
                return []

    def delete_task(self, task: str) -> bool:
        """
        Delete a task-repository mapping.

        Args:
            task: Unique task ID

        Returns:
            True if successful, False otherwise
        """
        with self.lock:
            try:
                if not os.path.exists(self.csv_file):
                    return False

                # Read all tasks except the one to delete
                remaining_tasks = {}
                with open(self.csv_file, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["task"] != task:
                            remaining_tasks[row["task"]] = row

                # Write back to CSV
                with open(self.csv_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "task",
                            "email",
                            "repo_name",
                            "repo_url",
                            "latest_commit_sha",
                            "pages_url",
                            "latest_round",
                            "created_at",
                            "updated_at",
                        ],
                    )
                    writer.writeheader()
                    for row in remaining_tasks.values():
                        writer.writerow(row)

                logger.info(f"Deleted task {task}")
                return True

            except Exception as e:
                logger.error(f"Error deleting task: {str(e)}")
                return False
