"""
Utility functions for common operations.
"""

from typing import Optional, List
import sys
import os
import platform
import subprocess
import time
import requests
from pathlib import Path
from loguru import logger
import platformdirs

# Use platformdirs for standard platform-specific directories
APP_NAME = "save_to_zotero"
APP_AUTHOR = "save_to_zotero"

# Default log file location - platform-appropriate user directory
DEFAULT_LOG_FILE = str(
    Path(platformdirs.user_log_dir(APP_NAME, APP_AUTHOR)) / "save_to_zotero.log"
)


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

        logger.debug(f"Log file location: {Path(log_file).absolute()}")

    return logger


# Configure module logger
configure_logger()


def _get_zotero_paths() -> List[Path]:
    """
    Get possible paths to the Zotero executable based on the operating system.

    Returns:
        List of possible paths to the Zotero executable
    """
    system = platform.system()
    paths = []

    if system == "Windows":
        # Common Windows installation paths
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        
        paths = [
            Path(program_files) / "Zotero" / "zotero.exe",
            Path(program_files_x86) / "Zotero" / "zotero.exe",
            # User might have installed in a different location
            Path(os.environ.get("APPDATA", "")) / "Zotero" / "Zotero" / "zotero.exe",
        ]
    elif system == "Darwin":  # macOS
        paths = [
            Path("/Applications/Zotero.app/Contents/MacOS/zotero"),
            Path(os.path.expanduser("~/Applications/Zotero.app/Contents/MacOS/zotero")),
        ]
    else:  # Linux
        paths = [
            Path("/usr/bin/zotero"),
            Path("/usr/local/bin/zotero"),
            Path(os.path.expanduser("~/.local/bin/zotero")),
            Path("/opt/zotero/zotero"),
        ]

    # Add path from environment variable if it exists
    zotero_path_env = os.environ.get("ZOTERO_PATH")
    if zotero_path_env:
        paths.insert(0, Path(zotero_path_env))

    # Return only paths that exist
    return [p for p in paths if p.exists()]


def ensure_zotero_running(
    connector_host: str = "http://127.0.0.1", connector_port: int = 23119
) -> bool:
    """
    Check if Zotero is running and try to launch it if not.

    Args:
        connector_host: Zotero connector host address
        connector_port: Zotero connector port number

    Returns:
        bool: True if Zotero is running

    Raises:
        RuntimeError: If Zotero couldn't be started
    """
    def is_zotero_running():
        try:
            response = requests.get(
                f"{connector_host}:{connector_port}/connector/ping", timeout=2
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    # First check if Zotero is already running
    if is_zotero_running():
        logger.info("Zotero is already running")
        return True

    # If not running, try to launch it
    logger.info("Zotero is not running. Attempting to launch it...")
    
    zotero_paths = _get_zotero_paths()
    
    if not zotero_paths:
        error_msg = (
            "Zotero executable not found. Please specify its location with ZOTERO_PATH "
            "environment variable or start Zotero manually."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    # Try each possible path
    for zotero_path in zotero_paths:
        try:
            logger.info(f"Attempting to launch Zotero from: {zotero_path}")
            
            # Launch Zotero and don't wait for it to exit
            if platform.system() == "Windows":
                subprocess.Popen([str(zotero_path)], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen([str(zotero_path)], start_new_session=True)
            
            # Wait for Zotero to start (up to 20 seconds)
            logger.info("Waiting for Zotero to start...")
            for _ in range(20):
                time.sleep(1)
                if is_zotero_running():
                    logger.info("Zotero started successfully")
                    return True
            
            logger.warning(f"Zotero didn't start from {zotero_path} within timeout")
        except Exception as e:
            logger.warning(f"Failed to launch Zotero from {zotero_path}: {e}")
    
    # If we get here, we couldn't start Zotero
    error_msg = (
        "Could not launch Zotero automatically. Please start Zotero manually."
    )
    logger.error(error_msg)
    raise RuntimeError(error_msg)


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
