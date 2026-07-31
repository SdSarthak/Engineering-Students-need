"""
Configuration for the Reddit Engineering Students scraper.

Every value can be overridden through an environment variable. Credentials are
never stored in this file - copy `.env.example` to `.env` and fill it in, or
export the variables in your shell before running the pipeline.
"""

import os


def _get_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to `default`."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back to `default`."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_dotenv(path: str = ".env") -> None:
    """
    Load `KEY=value` pairs from a dotenv file into os.environ.

    Existing environment variables always win, so an exported value overrides
    the file. Missing files are ignored - the file is optional.
    """
    if not os.path.exists(path):
        return

    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except IOError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Load .env before reading any settings so a dotenv file works out of the box.
load_dotenv()

# Reddit API credentials - required for scraping, unused for cleaning.
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "")
REDDIT_USER_AGENT = os.getenv(
    "REDDIT_USER_AGENT",
    "EngineeringStudents Scraper v1.0 by /u/{}".format(REDDIT_USERNAME or "anonymous"),
)

# Scraping configuration
TARGET_SUBREDDIT = os.getenv("TARGET_SUBREDDIT", "EngineeringStudents")
DEFAULT_LIMIT = _get_int("DEFAULT_LIMIT", 500)
DEFAULT_BATCH_SIZE = _get_int("DEFAULT_BATCH_SIZE", 50)
RATE_LIMIT_DELAY = _get_float("RATE_LIMIT_DELAY", 0.2)
MAX_COMMENT_DEPTH = _get_int("MAX_COMMENT_DEPTH", 10)
# Sort/time-filter listings the scraper walks through, in order.
SORT_METHODS = ("hot", "new", "top")
TOP_TIME_FILTERS = ("day", "week", "month", "year", "all")

# Output configuration
RAW_DATA_DIR = os.getenv("RAW_DATA_DIR", os.path.join("data", "raw"))
CLEAN_DATA_DIR = os.getenv("CLEAN_DATA_DIR", os.path.join("data", "clean"))
LOG_DIR = os.getenv("LOG_DIR", "logs")
MAX_OUTPUT_FILE_SIZE = _get_int("MAX_OUTPUT_FILE_SIZE", 200 * 1024 * 1024)
MAX_OUTPUT_WORDS = _get_int("MAX_OUTPUT_WORDS", 500_000)


def credentials() -> tuple:
    """Return the (client_id, client_secret, user_agent) triple."""
    return REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT


def has_credentials() -> bool:
    """True when both the client id and secret are present."""
    return bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)
