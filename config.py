"""
Configuration file for Reddit Scraper
Set your Reddit API credentials here or use environment variables.
"""

import os

# Reddit API Configuration
# You can set these directly or use environment variables
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID', 'UKikfU3DNd-BYgfGeOOPww')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET', '4g45HQVPzpp4yEYz-D_VE3OasXfruQ')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'EngineeringStudents Scraper v1.0 by /u/Top-Independence8001')

# Scraping Configuration
DEFAULT_LIMIT = 1000  # Maximum posts to scrape
DEFAULT_BATCH_SIZE = 100  # Posts per batch
RATE_LIMIT_DELAY = 0.1  # Seconds between requests

# File Configuration
MAX_OUTPUT_FILE_SIZE = 400 * 1024 * 1024  # 400MB in bytes
RAW_DATA_DIR = "data/raw"
CLEAN_DATA_DIR = "data/clean"

# Subreddit Configuration
TARGET_SUBREDDIT = "EngineeringStudents"
