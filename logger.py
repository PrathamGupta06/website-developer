import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional
import httpx
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)


class TelegramLogger:
    """
    Asynchronous Telegram logger that sends messages to a Telegram chat
    without blocking the main application thread.
    """

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_LOGGING_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_LOGGING_CHAT_ID")
        self.enabled = bool(self.bot_token and self.chat_id)
        self.session_start_times = {}

        # Thread pool for non-blocking operations
        self.executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="telegram_logger"
        )

        if not self.enabled:
            logging.warning(
                "Telegram logging disabled: Missing TELEGRAM_LOGGING_BOT_TOKEN or TELEGRAM_LOGGING_CHAT_ID"
            )

    def _format_message(
        self, level: str, message: str, data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format message for Telegram with proper escaping."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Simple escape function for text content only
        def escape_text(text: str) -> str:
            # Only escape the most problematic characters for MarkdownV2
            # Don't escape characters that are part of our formatting
            replacements = {
                '_': '\\_',
                '*': '\\*',
                '[': '\\[',
                ']': '\\]',
                '(': '\\(',
                ')': '\\)',
                '~': '\\~',
                '`': '\\`',
                '>': '\\>',
                '#': '\\#',
                '+': '\\+',
                '-': '\\-',
                '=': '\\=',
                '|': '\\|',
                '{': '\\{',
                '}': '\\}',
                '.': '\\.',
                '!': '\\!'
            }
            
            for char, escaped in replacements.items():
                text = text.replace(char, escaped)
            return text

        # Use simple text formatting to avoid markdown issues
        formatted_msg = "🔧 Website Developer API\n"
        formatted_msg += f"⏰ {timestamp}\n"
        formatted_msg += f"📊 {level.upper()}\n"
        formatted_msg += f"💬 {escape_text(message)}\n"

        if data:
            # Format data as JSON with pretty printing
            json_data = json.dumps(data, indent=2, default=str)
            # Limit length to avoid Telegram message limits
            if len(json_data) > 2000:
                json_data = json_data[:2000] + "...[truncated]"
            formatted_msg += f"\n📋 Data:\n{json_data}"

        return formatted_msg

    async def _send_message_async(self, message: str) -> bool:
        """Send message to Telegram asynchronously."""
        if not self.enabled:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

            # Split long messages
            max_length = 4000  # Telegram's limit is 4096, leave some buffer
            if len(message) > max_length:
                chunks = [
                    message[i : i + max_length]
                    for i in range(0, len(message), max_length)
                ]
            else:
                chunks = [message]

            async with httpx.AsyncClient(timeout=10.0) as client:
                for i, chunk in enumerate(chunks):
                    if len(chunks) > 1:
                        chunk = f"📄 Part {i + 1}/{len(chunks)}\n\n{chunk}"

                    payload = {
                        "chat_id": self.chat_id,
                        "text": chunk,
                    }

                    response = await client.post(url, json=payload)

                    if not response.is_success:
                        logging.error(
                            f"Failed to send Telegram message: {response.status_code} - {response.text}"
                        )
                        return False

                    # Small delay between chunks to avoid rate limiting
                    if i < len(chunks) - 1:
                        await asyncio.sleep(0.5)

            return True

        except Exception as e:
            logging.error(f"Error sending Telegram message: {str(e)}")
            return False

    def _send_message_sync(self, message: str):
        """Synchronous wrapper for sending messages in thread pool."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._send_message_async(message))
        finally:
            loop.close()

    def log_async(
        self, level: str, message: str, data: Optional[Dict[str, Any]] = None
    ):
        """
        Log message asynchronously without blocking the main thread.

        Args:
            level: Log level (info, error, warning, debug)
            message: Main message to log
            data: Optional dictionary with additional data
        """
        if not self.enabled:
            return

        formatted_message = self._format_message(level, message, data)

        # Submit to thread pool to avoid blocking
        self.executor.submit(self._send_message_sync, formatted_message)

    def start_session(
        self, session_id: str, task_name: str, request_data: Dict[str, Any]
    ):
        """Start timing a session."""
        self.session_start_times[session_id] = time.time()

        self.log_async(
            "info",
            f"🚀 Session Started: {task_name}",
            {
                "session_id": session_id,
                "task": task_name,
                "round": request_data.get("round", 1),
                "email": request_data.get("email", "unknown"),
                "timestamp": datetime.now().isoformat(),
            },
        )

    def end_session(
        self,
        session_id: str,
        task_name: str,
        success: bool,
        result_data: Optional[Dict[str, Any]] = None,
    ):
        """End timing a session and log results."""
        start_time = self.session_start_times.get(session_id)
        if start_time:
            duration_seconds = time.time() - start_time
            duration_minutes = duration_seconds / 60
            del self.session_start_times[session_id]
        else:
            duration_seconds = 0
            duration_minutes = 0

        status_emoji = "✅" if success else "❌"

        log_data = {
            "session_id": session_id,
            "task": task_name,
            "success": success,
            "duration_minutes": round(duration_minutes, 2),
            "duration_seconds": round(duration_seconds, 2),
            "timestamp": datetime.now().isoformat(),
        }

        if result_data:
            log_data.update(result_data)

        self.log_async(
            "info" if success else "error",
            f"{status_emoji} Session Completed: {task_name} (⏱️ {duration_minutes:.2f} minutes)",
            log_data,
        )

    def log_error(
        self,
        error_message: str,
        context: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None,
    ):
        """Log an error with context."""
        error_data: Dict[str, Any] = {"error": error_message, "timestamp": datetime.now().isoformat()}

        if context:
            error_data.update(context)

        if exception:
            error_data["exception_type"] = type(exception).__name__
            error_data["exception_details"] = str(exception)

        self.log_async("error", f"❌ Error: {error_message}", error_data)

    def log_retry(self, attempt: int, max_attempts: int, operation: str, error: str):
        """Log retry attempts."""
        self.log_async(
            "warning",
            f"🔄 Retry {attempt}/{max_attempts}: {operation}",
            {
                "operation": operation,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def log_info(self, message: str, data: Optional[Dict[str, Any]] = None):
        """Log informational message."""
        self.log_async("info", message, data)

    def log_warning(self, message: str, data: Optional[Dict[str, Any]] = None):
        """Log warning message."""
        self.log_async("warning", message, data)

    def shutdown(self):
        """Gracefully shutdown the logger."""
        try:
            # Wait for pending tasks to complete
            self.executor.shutdown(wait=True)
        except Exception as e:
            logging.error(f"Error shutting down Telegram logger: {str(e)}")


# Global instance
telegram_logger = TelegramLogger()
