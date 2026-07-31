"""
Main Pipeline for the Reddit Engineering Students Scraper
Orchestrates the scraping and cleaning phases.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

import config
from cleaner import TextCleaner
from logging_setup import configure_logging
from scraper import RedditScraper

logger = logging.getLogger(__name__)


class Pipeline:
    """Runs the scrape and clean phases end to end."""

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        user_agent: str = "",
        subreddit: Optional[str] = None,
    ):
        """
        Initialize the pipeline.

        Credentials are only needed for the scraping phase; the cleaning phase
        works offline on whatever is already in the raw directory.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.subreddit = subreddit or config.TARGET_SUBREDDIT
        self.scraper: Optional[RedditScraper] = None
        self.cleaner: Optional[TextCleaner] = None

    def get_scraper(self) -> RedditScraper:
        """Build the scraper on first use."""
        if self.scraper is None:
            if not self.client_id or not self.client_secret:
                raise ValueError(
                    "Reddit credentials are required for scraping. Set "
                    "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (see .env.example)."
                )
            self.scraper = RedditScraper(
                self.client_id,
                self.client_secret,
                self.user_agent,
                subreddit=self.subreddit,
            )
            logger.info("Scraper initialized for r/%s", self.subreddit)
        return self.scraper

    def get_cleaner(self) -> TextCleaner:
        """Build the cleaner on first use."""
        if self.cleaner is None:
            self.cleaner = TextCleaner()
            logger.info("Cleaner initialized")
        return self.cleaner

    def run_scraping(self, limit: int = 0, batch_size: int = 50) -> None:
        """Run the scraping phase."""
        logger.info("Starting scraping phase")
        self.get_scraper().scrape_posts(limit=limit, batch_size=batch_size)
        logger.info("Scraping phase completed")

    def run_cleaning(self) -> None:
        """Run the cleaning phase."""
        logger.info("Starting cleaning phase")
        self.get_cleaner().process_posts()
        logger.info("Cleaning phase completed")

    def run_full_pipeline(
        self, limit: int = 0, batch_size: int = 50, skip_scraping: bool = False
    ) -> None:
        """Run scraping (unless skipped) followed by cleaning."""
        start_time = datetime.now()
        logger.info("Starting full pipeline at %s", start_time.isoformat(timespec="seconds"))

        if skip_scraping:
            logger.info("Skipping scraping phase")
        else:
            self.run_scraping(limit=limit, batch_size=batch_size)

        self.run_cleaning()

        duration = datetime.now() - start_time
        logger.info("Pipeline completed in %s", duration)
        self.print_summary()

    def scraper_stats(self) -> Dict[str, Any]:
        """Read the scraper progress file without needing a live client."""
        progress_file = os.path.join(config.RAW_DATA_DIR, "scraping_progress.json")
        if not os.path.exists(progress_file):
            return {}
        try:
            import json

            with open(progress_file, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            return stored if isinstance(stored, dict) else {}
        except Exception as exc:
            logger.warning("Could not read scraper progress: %s", exc)
            return {}

    def print_summary(self) -> None:
        """Print a summary of what is on disk after the run."""
        try:
            scraper_stats = self.scraper_stats()
            cleaner_stats = self.get_cleaner().get_cleaning_stats()

            print("\n" + "=" * 60)
            print("PIPELINE SUMMARY")
            print("=" * 60)
            print("Subreddit:            r/{}".format(self.subreddit))
            print("Total posts scraped:  {}".format(scraper_stats.get("total_posts", 0)))
            print("Raw JSON files:       {}".format(cleaner_stats["raw_files"]))
            print("Processed files:      {}".format(cleaner_stats["processed_files"]))
            print("Output text files:    {}".format(cleaner_stats["output_files"]))
            print(
                "Total output size:    {:.2f} MB".format(
                    cleaner_stats["total_output_size"] / (1024 * 1024)
                )
            )
            print("Last run:             {}".format(scraper_stats.get("last_run", "unknown")))
            print("=" * 60)
        except Exception as exc:
            logger.error("Could not generate summary: %s", exc)


def prompt_for_credentials() -> tuple:
    """Ask for Reddit credentials interactively."""
    print("Reddit API Credentials Setup")
    print("=" * 40)
    print("To get your credentials:")
    print("1. Go to https://www.reddit.com/prefs/apps")
    print("2. Click 'Create App' or 'Create Another App'")
    print("3. Choose 'script' as the app type")
    print("4. Paste the client id and secret below")
    print()

    client_id = input("Reddit client id: ").strip()
    client_secret = input("Reddit client secret: ").strip()
    username = input("Reddit username (for the user agent): ").strip()

    user_agent = (
        "EngineeringStudents Scraper v1.0 by /u/{}".format(username)
        if username
        else "EngineeringStudents Scraper v1.0"
    )
    return client_id, client_secret, user_agent


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        description="Reddit Engineering Students scraper pipeline",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=config.DEFAULT_LIMIT,
        help="Maximum posts to scrape, 0 for unlimited (default: %(default)s)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=config.DEFAULT_BATCH_SIZE,
        help="Posts saved per JSON batch (default: %(default)s)",
    )
    parser.add_argument(
        "--subreddit",
        default=config.TARGET_SUBREDDIT,
        help="Subreddit to scrape (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        help="Skip the scraping phase and only run cleaning",
    )
    parser.add_argument("--clean-only", action="store_true", help="Only run the cleaning phase")
    parser.add_argument("--scrape-only", action="store_true", help="Only run the scraping phase")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting when credentials are missing",
    )
    return parser


def resolve_credentials(non_interactive: bool) -> tuple:
    """Resolve credentials from the environment, prompting only as a fallback."""
    client_id, client_secret, user_agent = config.credentials()
    if client_id and client_secret:
        return client_id, client_secret, user_agent

    logger.info("Reddit credentials not found in the environment")
    if non_interactive or not sys.stdin.isatty():
        return "", "", user_agent

    return prompt_for_credentials()


def main(argv: Optional[list] = None) -> int:
    """Entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    configure_logging("pipeline.log")

    if args.batch_size < 1:
        print("Error: --batch-size must be at least 1")
        return 2

    needs_credentials = not (args.clean_only or args.skip_scraping)
    client_id = client_secret = ""
    user_agent = config.REDDIT_USER_AGENT

    if needs_credentials:
        client_id, client_secret, user_agent = resolve_credentials(args.non_interactive)
        if not client_id or not client_secret:
            logger.error("Reddit credentials are required for scraping")
            print("\nError: Reddit credentials are required to scrape.")
            print("Copy .env.example to .env and fill in REDDIT_CLIENT_ID and")
            print("REDDIT_CLIENT_SECRET, or export them in your shell.")
            print("Cleaning existing raw files needs no credentials: python main.py --clean-only")
            return 1

    pipeline = Pipeline(client_id, client_secret, user_agent, subreddit=args.subreddit)

    try:
        if args.clean_only:
            pipeline.run_cleaning()
            pipeline.print_summary()
        elif args.scrape_only:
            pipeline.run_scraping(limit=args.limit, batch_size=args.batch_size)
        else:
            pipeline.run_full_pipeline(
                limit=args.limit,
                batch_size=args.batch_size,
                skip_scraping=args.skip_scraping,
            )
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        print("\nPipeline interrupted. Progress has been saved.")
        return 130
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        print("\nPipeline failed: {}".format(exc))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
