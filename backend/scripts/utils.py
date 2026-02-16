"""
Shared utilities for NBA data collection scripts.

Provides rate limiting, retry logic, checkpointing, and logging
used across all collection and processing scripts.
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path

import requests

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "backend" / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"

# Default delay between NBA API calls (seconds)
DEFAULT_API_DELAY = 2.5


def setup_logging(script_name: str) -> logging.Logger:
    """Configure logging to both console and a log file.

    Args:
        script_name: Name of the calling script, used for the logger name
                     and log file path.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(script_name)
    logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = CHECKPOINT_DIR / f"{script_name}.log"
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def load_checkpoint(filepath: str) -> dict:
    """Load a JSON checkpoint file.

    Args:
        filepath: Path to the checkpoint JSON file.

    Returns:
        The checkpoint state dict, or an empty dict if the file doesn't exist.
    """
    path = Path(filepath)
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}


def save_checkpoint(filepath: str, state: dict) -> None:
    """Save checkpoint state to a JSON file atomically.

    Writes to a temporary file first, then renames to prevent corruption
    if the process is interrupted mid-write.

    Args:
        filepath: Path to the checkpoint JSON file.
        state: The checkpoint state dict to save.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in the same directory, then atomic rename
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file if rename fails
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def rate_limited_api_call(endpoint_class, max_retries: int = 3, delay: float = DEFAULT_API_DELAY, **kwargs):
    """Call an nba_api endpoint with rate limiting and retry logic.

    Adds a delay before each call to respect NBA API rate limits,
    and retries on transient failures with exponential backoff.

    Args:
        endpoint_class: The nba_api endpoint class to instantiate
                        (e.g., PlayerGameLogs, CommonTeamRoster).
        max_retries: Maximum number of retry attempts on failure.
        delay: Seconds to sleep before the API call.
        **kwargs: Keyword arguments passed to the endpoint class constructor.

    Returns:
        The instantiated endpoint object. Call .get_data_frames() on it
        to extract DataFrames.

    Raises:
        Exception: If all retries are exhausted.
    """
    time.sleep(delay)

    last_exception = None
    for attempt in range(max_retries):
        try:
            result = endpoint_class(**kwargs)
            return result
        except (requests.exceptions.RequestException,
                json.JSONDecodeError,
                ConnectionError,
                Exception) as e:
            last_exception = e
            # Don't retry on unexpected errors that aren't network-related
            if not isinstance(e, (requests.exceptions.RequestException,
                                   json.JSONDecodeError,
                                   ConnectionError)):
                # Check if it looks like a rate limit or network error
                error_msg = str(e).lower()
                if not any(keyword in error_msg for keyword in
                           ["timeout", "connection", "rate", "429", "503", "json"]):
                    raise

            backoff = delay * (2 ** attempt)
            logging.getLogger("utils").warning(
                f"API call failed (attempt {attempt + 1}/{max_retries}): {e}. "
                f"Retrying in {backoff:.1f}s..."
            )
            time.sleep(backoff)

    raise last_exception
