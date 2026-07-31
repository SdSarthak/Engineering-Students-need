"""
Reddit Scraper for r/EngineeringStudents
Scrapes posts and their full comment trees using PRAW (Python Reddit API
Wrapper) with free client credentials. Respects rate limits and Reddit's
terms of service.
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple
import logging

from tqdm import tqdm

import config

logger = logging.getLogger(__name__)

PROGRESS_FILENAME = "scraping_progress.json"


class RedditScraper:
    """Reddit scraper for a single subreddit using PRAW."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        subreddit: Optional[str] = None,
        data_dir: Optional[str] = None,
        rate_limit_delay: Optional[float] = None,
        max_comment_depth: Optional[int] = None,
        reddit: Any = None,
    ):
        """
        Initialize the scraper.

        Args:
            client_id: Reddit app client ID (free).
            client_secret: Reddit app client secret (free).
            user_agent: User agent string for API requests.
            subreddit: Subreddit to scrape (defaults to config.TARGET_SUBREDDIT).
            data_dir: Directory for raw JSON batches (defaults to config.RAW_DATA_DIR).
            rate_limit_delay: Seconds to sleep between submissions.
            max_comment_depth: Maximum reply nesting depth to follow.
            reddit: Pre-built Reddit client. Mainly a test seam - when omitted a
                PRAW client is created from the credentials above.
        """
        if reddit is not None:
            self.reddit = reddit
        else:
            if not client_id or not client_secret:
                raise ValueError(
                    "Reddit credentials are required. Set REDDIT_CLIENT_ID and "
                    "REDDIT_CLIENT_SECRET (see .env.example)."
                )
            import praw  # imported lazily so the module can be used without network deps

            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )

        self.subreddit_name = subreddit or config.TARGET_SUBREDDIT
        self.data_dir = data_dir or config.RAW_DATA_DIR
        self.rate_limit_delay = (
            config.RATE_LIMIT_DELAY if rate_limit_delay is None else rate_limit_delay
        )
        self.max_comment_depth = (
            config.MAX_COMMENT_DEPTH if max_comment_depth is None else max_comment_depth
        )
        self.ensure_data_directory()

    # ------------------------------------------------------------------
    # Progress tracking
    # ------------------------------------------------------------------

    def ensure_data_directory(self) -> None:
        """Ensure the raw data directory exists."""
        os.makedirs(self.data_dir, exist_ok=True)

    def get_progress_file(self) -> str:
        """Path to the progress tracking file."""
        return os.path.join(self.data_dir, PROGRESS_FILENAME)

    def load_progress(self) -> Dict[str, Any]:
        """
        Load scraping progress from disk.

        Returns a dict with `seen_ids` (list of post IDs already saved),
        `total_posts` and `last_run`. Progress files written by older versions
        only recorded `last_processed_id`; that value is folded into `seen_ids`.
        """
        default = {"seen_ids": [], "total_posts": 0, "last_run": None}
        progress_file = self.get_progress_file()

        if not os.path.exists(progress_file):
            return default

        try:
            with open(progress_file, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
        except (json.JSONDecodeError, IOError, OSError) as exc:
            logger.warning("Could not load progress file: %s", exc)
            return default

        if not isinstance(stored, dict):
            logger.warning("Progress file has unexpected format, starting fresh")
            return default

        seen_ids = stored.get("seen_ids")
        if not isinstance(seen_ids, list):
            seen_ids = []
        legacy_id = stored.get("last_processed_id")
        if legacy_id and legacy_id not in seen_ids:
            seen_ids.append(legacy_id)

        total_posts = stored.get("total_posts", 0)
        if not isinstance(total_posts, int) or total_posts < 0:
            total_posts = 0

        return {
            "seen_ids": seen_ids,
            "total_posts": total_posts,
            "last_run": stored.get("last_run"),
        }

    def save_progress(self, progress: Dict[str, Any]) -> None:
        """Save scraping progress to disk."""
        progress_file = self.get_progress_file()
        try:
            with open(progress_file, "w", encoding="utf-8") as handle:
                json.dump(progress, handle, indent=2, default=str)
        except (IOError, OSError) as exc:
            logger.error("Could not save progress file: %s", exc)

    def next_batch_number(self) -> int:
        """
        Return the next unused batch number.

        Derived from the files already on disk so a resumed run never
        overwrites an earlier batch.
        """
        highest = 0
        try:
            entries = os.listdir(self.data_dir)
        except (IOError, OSError):
            return 1

        for filename in entries:
            if not (filename.startswith("posts_batch_") and filename.endswith(".json")):
                continue
            stem = filename[len("posts_batch_") : -len(".json")]
            if stem.isdigit():
                highest = max(highest, int(stem))
        return highest + 1

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract_comment_data(self, comment: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
        """
        Extract a comment and its direct replies recursively.

        Only *direct* replies are followed at each level. PRAW's `replies.list()`
        flattens the whole subtree, so recursing over it would store every
        descendant once per ancestor and blow the output up exponentially.

        Args:
            comment: PRAW comment object.
            depth: Current nesting depth.

        Returns:
            Dictionary of comment data, or None when the comment is unusable.
        """
        comment_id = getattr(comment, "id", None)
        try:
            author = str(comment.author) if comment.author else "[deleted]"
            body = comment.body or ""
            if body in ("[deleted]", "[removed]"):
                body = ""

            created_utc = comment.created_utc
            comment_data = {
                "id": comment_id,
                "author": author,
                "body": body,
                "created_utc": created_utc,
                "created_date": _iso_from_utc(created_utc),
                "upvotes": getattr(comment, "score", 0),
                "depth": depth,
                "permalink": _permalink(comment),
                "is_submitter": bool(getattr(comment, "is_submitter", False)),
                "scraped_at": datetime.now().isoformat(),
                "replies": [],
            }
        except AttributeError as exc:
            # MoreComments placeholders and deleted stubs land here.
            logger.debug("Skipping comment %s: %s", comment_id, exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive against PRAW errors
            logger.error("Error extracting data from comment %s: %s", comment_id, exc)
            return None

        if depth >= self.max_comment_depth:
            return comment_data

        for reply in self._direct_replies(comment):
            reply_data = self.extract_comment_data(reply, depth + 1)
            if reply_data:
                comment_data["replies"].append(reply_data)

        return comment_data

    def _direct_replies(self, comment: Any) -> List[Any]:
        """Return the direct replies of a comment, expanding `MoreComments`."""
        replies = getattr(comment, "replies", None)
        if not replies:
            return []

        replace_more = getattr(replies, "replace_more", None)
        if callable(replace_more):
            try:
                replace_more(limit=None)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning(
                    "Could not expand replies for comment %s: %s",
                    getattr(comment, "id", "?"),
                    exc,
                )

        try:
            return list(replies)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning(
                "Could not read replies for comment %s: %s", getattr(comment, "id", "?"), exc
            )
            return []

    def extract_post_data(self, submission: Any) -> Optional[Dict[str, Any]]:
        """
        Extract a submission and its full comment tree.

        Args:
            submission: PRAW submission object.

        Returns:
            Dictionary containing post data and nested comments, or None.
        """
        submission_id = getattr(submission, "id", None)
        try:
            author = str(submission.author) if submission.author else "[deleted]"
            title = submission.title or "[no title]"
            selftext = submission.selftext or ""
            if selftext in ("[deleted]", "[removed]"):
                selftext = ""

            created_utc = submission.created_utc
            post_data = {
                "id": submission_id,
                "title": title,
                "text": selftext,
                "author": author,
                "created_utc": created_utc,
                "created_date": _iso_from_utc(created_utc),
                "upvotes": getattr(submission, "score", 0),
                "num_comments": getattr(submission, "num_comments", 0),
                "url": getattr(submission, "url", ""),
                "permalink": _permalink(submission),
                "is_self": bool(getattr(submission, "is_self", False)),
                "over_18": bool(getattr(submission, "over_18", False)),
                "stickied": bool(getattr(submission, "stickied", False)),
                "subreddit": str(getattr(submission, "subreddit", self.subreddit_name)),
                "scraped_at": datetime.now().isoformat(),
                "comments": [],
            }
        except AttributeError as exc:
            logger.error("Skipping malformed submission %s: %s", submission_id, exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive against PRAW errors
            logger.error("Error extracting data from post %s: %s", submission_id, exc)
            return None

        post_data["comments"] = self._extract_top_level_comments(submission)
        return post_data

    def _extract_top_level_comments(self, submission: Any) -> List[Dict[str, Any]]:
        """Extract the top-level comments of a submission, replies nested inside."""
        comments = getattr(submission, "comments", None)
        if not comments:
            return []

        replace_more = getattr(comments, "replace_more", None)
        if callable(replace_more):
            try:
                replace_more(limit=None)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning(
                    "Could not expand comments for post %s: %s",
                    getattr(submission, "id", "?"),
                    exc,
                )

        try:
            top_level = list(comments)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.error(
                "Could not read comments for post %s: %s", getattr(submission, "id", "?"), exc
            )
            return []

        extracted = []
        for comment in top_level:
            comment_data = self.extract_comment_data(comment, depth=0)
            if comment_data:
                extracted.append(comment_data)

        logger.debug(
            "Extracted %d top-level comments for post %s",
            len(extracted),
            getattr(submission, "id", "?"),
        )
        return extracted

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_posts_batch(self, posts: List[Dict[str, Any]], batch_num: int) -> Optional[str]:
        """
        Save a batch of posts to a JSON file.

        Args:
            posts: List of post dictionaries.
            batch_num: Batch number used in the filename.

        Returns:
            Path to the written file, or None when nothing was written.
        """
        if not posts:
            return None

        filename = "posts_batch_{:04d}.json".format(batch_num)
        filepath = os.path.join(self.data_dir, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as handle:
                json.dump(posts, handle, indent=2, ensure_ascii=False)
        except (IOError, OSError) as exc:
            logger.error("Could not save batch %d: %s", batch_num, exc)
            return None

        logger.info("Saved %d posts to %s", len(posts), filename)
        return filepath

    # ------------------------------------------------------------------
    # Listing traversal
    # ------------------------------------------------------------------

    def iter_listings(self, subreddit: Any) -> Iterator[Tuple[str, Any]]:
        """
        Yield `(label, submissions)` pairs for every configured listing.

        Reddit caps a single listing at roughly 1000 items, so several sorts and
        time filters are walked in turn to reach a wider slice of the subreddit.
        Duplicates across listings are filtered out by post ID in `scrape_posts`.
        """
        for sort_method in config.SORT_METHODS:
            if sort_method == "top":
                for time_filter in config.TOP_TIME_FILTERS:
                    yield (
                        "top/{}".format(time_filter),
                        subreddit.top(limit=None, time_filter=time_filter),
                    )
            else:
                listing = getattr(subreddit, sort_method, None)
                if listing is None:
                    logger.warning("Unknown sort method %s, skipping", sort_method)
                    continue
                yield sort_method, listing(limit=None)

    def scrape_posts(self, limit: int = 0, batch_size: int = 50) -> Dict[str, Any]:
        """
        Scrape posts from the target subreddit.

        Walks each configured listing to exhaustion, skipping posts already
        recorded in the progress file, and writes batches of `batch_size` posts
        to `data_dir`.

        Args:
            limit: Maximum posts to scrape this run (0 means no limit).
            batch_size: Posts saved per JSON batch file.

        Returns:
            The final progress dictionary.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        logger.info("Starting to scrape r/%s", self.subreddit_name)
        if limit <= 0:
            logger.info("No limit set - walking every configured listing to exhaustion")

        progress = self.load_progress()
        seen_ids = set(progress["seen_ids"])
        total_posts = progress["total_posts"]

        subreddit = self.reddit.subreddit(self.subreddit_name)

        current_batch: List[Dict[str, Any]] = []
        batch_num = self.next_batch_number()
        processed_count = 0
        skipped_count = 0

        progress_bar = tqdm(
            desc="Scraping posts",
            unit="post",
            total=limit if limit > 0 else None,
            dynamic_ncols=True,
        )

        def flush_batch() -> None:
            """Write the pending batch and persist progress."""
            nonlocal current_batch, batch_num, total_posts
            if not current_batch:
                return
            if self.save_posts_batch(current_batch, batch_num):
                batch_num += 1
                total_posts += len(current_batch)
            current_batch = []
            progress["seen_ids"] = sorted(seen_ids)
            progress["total_posts"] = total_posts
            progress["last_run"] = datetime.now().isoformat()
            self.save_progress(progress)

        try:
            for label, submissions in self.iter_listings(subreddit):
                if limit > 0 and processed_count >= limit:
                    break

                logger.info("Scraping listing: %s", label)
                try:
                    submission_iter = iter(submissions)
                except TypeError:  # pragma: no cover - defensive
                    logger.warning("Listing %s is not iterable, skipping", label)
                    continue

                while True:
                    try:
                        submission = next(submission_iter)
                    except StopIteration:
                        break
                    except Exception as exc:
                        logger.warning("Listing %s failed mid-iteration: %s", label, exc)
                        break

                    submission_id = getattr(submission, "id", None)
                    if submission_id is None or submission_id in seen_ids:
                        skipped_count += 1
                        continue

                    post_data = self.extract_post_data(submission)
                    if post_data:
                        seen_ids.add(submission_id)
                        current_batch.append(post_data)
                        processed_count += 1

                        progress_bar.update(1)
                        progress_bar.set_postfix(
                            {
                                "listing": label,
                                "skipped": skipped_count,
                                "comments": len(post_data["comments"]),
                            }
                        )

                        if len(current_batch) >= batch_size:
                            flush_batch()

                    if self.rate_limit_delay > 0:
                        time.sleep(self.rate_limit_delay)

                    if limit > 0 and processed_count >= limit:
                        break
        finally:
            flush_batch()
            progress_bar.close()
            progress["seen_ids"] = sorted(seen_ids)
            progress["total_posts"] = total_posts
            progress["last_run"] = datetime.now().isoformat()
            self.save_progress(progress)

        logger.info(
            "Scraping completed. New posts: %d, duplicates skipped: %d, total on disk: %d",
            processed_count,
            skipped_count,
            total_posts,
        )
        return progress

    def get_subreddit_info(self) -> Dict[str, Any]:
        """Get basic information about the target subreddit."""
        try:
            subreddit = self.reddit.subreddit(self.subreddit_name)
            return {
                "name": subreddit.display_name,
                "title": subreddit.title,
                "description": subreddit.description,
                "subscribers": subreddit.subscribers,
                "created_utc": subreddit.created_utc,
                "public_description": subreddit.public_description,
            }
        except Exception as exc:
            logger.error("Error getting subreddit info: %s", exc)
            return {}


def _iso_from_utc(created_utc: Any) -> str:
    """Convert a Reddit UTC timestamp to an ISO 8601 string."""
    try:
        return datetime.utcfromtimestamp(float(created_utc)).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _permalink(item: Any) -> str:
    """Build an absolute permalink for a submission or comment."""
    permalink = getattr(item, "permalink", "") or ""
    if permalink.startswith("http"):
        return permalink
    if permalink:
        return "https://reddit.com{}".format(permalink)
    return ""


def main() -> int:
    """Run the scraper standalone using credentials from the environment."""
    from logging_setup import configure_logging

    configure_logging("scraper.log")

    if not config.has_credentials():
        logger.error("Reddit credentials are not set")
        logger.info("1. Go to https://www.reddit.com/prefs/apps")
        logger.info("2. Click 'Create App' and choose the 'script' type")
        logger.info("3. Copy .env.example to .env and fill in the client id and secret")
        return 1

    client_id, client_secret, user_agent = config.credentials()

    try:
        scraper = RedditScraper(client_id, client_secret, user_agent)
        info = scraper.get_subreddit_info()
        logger.info("Scraping r/%s", info.get("name", config.TARGET_SUBREDDIT))
        logger.info("Subscribers: %s", info.get("subscribers", "unknown"))
        scraper.scrape_posts(limit=config.DEFAULT_LIMIT, batch_size=config.DEFAULT_BATCH_SIZE)
    except Exception as exc:
        logger.error("Scraping failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
