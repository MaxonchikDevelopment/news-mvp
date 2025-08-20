"""Centralized logging module for the project."""

import logging
import os
from datetime import datetime


def get_logger(name: str) -> logging.Logger:
    """Create and configure a logger instance.

    Args:
        name (str): Name of the logger (e.g., module name).

    Returns:
        logging.Logger: Configured logger object.
    """
    # Ensure logs directory exists
    log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)

    # Log file named by date
    log_file = os.path.join(log_dir, f"{datetime.now().date()}.log")

    # Configure logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # File handler (append mode)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Attach handlers (avoid duplicates)
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
