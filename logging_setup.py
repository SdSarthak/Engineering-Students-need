"""
Shared logging configuration.

Logging is configured explicitly by the command line entry points rather than
at import time, so importing `scraper` or `cleaner` from a test or a notebook
never creates stray log files.
"""

import logging
import os

import config

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def configure_logging(filename: str, level: int = logging.INFO) -> None:
    """
    Send log records to both `LOG_DIR/filename` and the console.

    Args:
        filename: Log file name, created inside `config.LOG_DIR`.
        level: Logging level for the root logger.
    """
    handlers = [logging.StreamHandler()]

    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        handlers.insert(0, logging.FileHandler(os.path.join(config.LOG_DIR, filename), encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - depends on filesystem permissions
        logging.getLogger(__name__).warning("Could not open log file %s: %s", filename, exc)

    logging.basicConfig(level=level, format=_LOG_FORMAT, handlers=handlers, force=True)
