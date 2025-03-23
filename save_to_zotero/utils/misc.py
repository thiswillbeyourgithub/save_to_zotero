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

# Get user's home directory for storing logs in a platform-appropriate location
def get_app_log_dir() -> Path:
    """
    Get an appropriate directory for storing application logs.
    Creates the directory if it doesn't exist.
    
    Returns:
        Path object for the log directory
    """
    # Use platform-specific locations
    if sys.platform == "win32":
        # Windows: Use %APPDATA%\save_to_zotero\logs
        base_dir = Path(os.environ.get("APPDATA", "~")) / "save_to_zotero" / "logs"
    elif sys.platform == "darwin":
        # macOS: Use ~/Library/Logs/save_to_zotero
        base_dir = Path("~").expanduser() / "Library" / "Logs" / "save_to_zotero"
    else:
        # Linux/Unix: Use ~/.local/share/save_to_zotero/logs (XDG Base Directory)
        xdg_data_home = os.environ.get("XDG_DATA_HOME", "~/.local/share")
        base_dir = Path(xdg_data_home).expanduser() / "save_to_zotero" / "logs"
    
    # Ensure directory exists
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir

# Default log file location - platform-appropriate user directory
DEFAULT_LOG_FILE = str(get_app_log_dir() / "zotero_uploader.log")


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


def ensure_zotero_running(
    connector_host: str = "http://127.0.0.1", 
    connector_port: int = 23119
) -> bool:
    """
    Check if Zotero is running and raise an exception if not.

    Args:
        connector_host: Zotero connector host address
        connector_port: Zotero connector port number

    Returns:
        bool: True if Zotero is running

    Raises:
        RuntimeError: If Zotero is not running
    """
    try:
        # Try to contact the Zotero connector API
        response = requests.post(f"{connector_host}:{connector_port}/connector/ping", timeout=2)
        if response.status_code == 200:
            logger.info("Zotero is already running")
            return True
    except requests.exceptions.RequestException:
        error_msg = "Zotero is not running. Please start Zotero manually before continuing."
        logger.error(error_msg)
        raise RuntimeError(error_msg)

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
