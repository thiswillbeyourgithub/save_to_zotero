"""
Utility functions for common operations.
"""

from typing import Optional, Dict, Any, Union, List
import sys
import os
import subprocess
import time
import requests
from pathlib import Path
from loguru import logger

# Default log file location
DEFAULT_LOG_FILE = str(Path(__file__).parent.parent / "zotero_uploader.log")


def configure_logger(
    logger_name: Optional[str] = None,
    log_level: str = "INFO",
    log_file: Optional[str] = DEFAULT_LOG_FILE,
    console: bool = True,
) -> logger:
    """
    Configure loguru logger with consistent formatting.

    Args:
        logger_name: Name of the logger (ignored in loguru, kept for compatibility)
        log_level: Logging level (default: "INFO")
        log_file: Path to log file (optional)
        console: Whether to log to console (default: True)

    Returns:
        Configured loguru logger
    """
    # Remove any existing handlers
    logger.remove()

    # Add console handler if requested
    if console:
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - {message}",
            level=log_level,
        )

    # Add file handler if specified
    if log_file:
        # Ensure directory exists
        log_path = Path(log_file)
        log_dir = log_path.parent
        if str(log_dir) != "" and not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - {message}",
            level=log_level,
            rotation="10 MB",
            compression="zip",
        )

        logger.info(f"Logging to file: {log_file}")

    return logger


# Configure module logger
configure_logger()


def ensure_zotero_running() -> bool:
    """
    Check if Zotero is running and try to start it if not.

    Returns:
        bool: True if Zotero is running or was successfully started
    """
    try:
        # Try to contact the Zotero connector API
        response = requests.post("http://127.0.0.1:23119/connector/ping", timeout=2)
        if response.status_code == 200:
            logger.info("Zotero is already running")
            return True
    except requests.exceptions.RequestException:
        logger.warning("Zotero doesn't appear to be running")

        # Try to start Zotero (platform-dependent)
        try:
            if os.name == "nt":  # Windows
                subprocess.Popen(["start", "zotero"], shell=True)
            elif os.name == "posix":  # Linux/macOS
                if Path("/Applications/Zotero.app").exists():  # macOS
                    subprocess.Popen(["open", "/Applications/Zotero.app"])
                else:  # Linux
                    subprocess.Popen(["zotero"])

            # Wait for Zotero to start
            logger.info("Waiting for Zotero to start...")
            for _ in range(15):  # Try for 15 seconds
                time.sleep(1)
                try:
                    response = requests.post(
                        "http://127.0.0.1:23119/connector/ping", timeout=2
                    )
                    if response.status_code == 200:
                        logger.info("Zotero started successfully")
                        return True
                except requests.exceptions.RequestException:
                    pass

            logger.warning("Timed out waiting for Zotero to start")
            return False

        except Exception as e:
            logger.error(f"Failed to start Zotero: {e}")
            return False

    return True


def find_available_port(start_port: int = 25852, max_attempts: int = 100) -> int:
    """
    Find an available port starting from the given port number.

    Args:
        start_port: Port number to start checking from
        max_attempts: Maximum number of ports to check

    Returns:
        An available port number
    """
    import socket

    logger.debug(f"Searching for available port starting from {start_port}")
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                logger.debug(f"Found available port: {port}")
                return port
        except OSError:
            logger.debug(f"Port {port} is not available")
            continue

    error_msg = f"Could not find an available port after {max_attempts} attempts"
    logger.error(error_msg)
    raise RuntimeError(error_msg)
