"""
Text Cleaner for Reddit Posts
Processes the raw JSON batches produced by the scraper and converts them into
clean, human-readable text files, rotating output once a size or word budget is
reached.
"""

import html
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from tqdm import tqdm

import config

logger = logging.getLogger(__name__)

PROCESSED_INDEX = "processed_files.txt"
OUTPUT_PREFIX = "cleaned_posts_"

# Substitutions applied in order by `clean_text`.
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL_RE = re.compile(r"https?://\S+")
_USER_MENTION_RE = re.compile(r"(?<![A-Za-z0-9])/?u/[A-Za-z0-9_-]+")
_SUBREDDIT_MENTION_RE = re.compile(r"(?<![A-Za-z0-9])/?r/[A-Za-z0-9_-]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n\s*")
_HORIZONTAL_SPACE_RE = re.compile(r"[ \t]+")
# Leading quote (`>`) and list (`-`, `*`, `+`) markers. A dash only counts as a
# marker when whitespace follows it, so "-5 degrees" keeps its minus sign.
_LINE_MARKER_RE = re.compile(
    r"^[ \t]*(?:>[ \t]*|[-*+](?=[ \t])[ \t]*)+", flags=re.MULTILINE
)
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"\*([^*]+)\*")
_CODE_RE = re.compile(r"`([^`]+)`")
_STRIKE_RE = re.compile(r"~~([^~]+)~~")
_DOTS_RE = re.compile(r"\.{3,}")
_BANGS_RE = re.compile(r"!{2,}")
_QUESTIONS_RE = re.compile(r"\?{2,}")


class TextCleaner:
    """Turns raw scraper JSON into readable, size-bounded text files."""

    def __init__(
        self,
        raw_dir: Optional[str] = None,
        clean_dir: Optional[str] = None,
        max_file_size: Optional[int] = None,
        max_words: Optional[int] = None,
    ):
        """
        Initialize the cleaner.

        Args:
            raw_dir: Directory containing raw JSON batches.
            clean_dir: Directory to write cleaned text files into.
            max_file_size: Maximum output file size in bytes.
            max_words: Maximum word count per output file.
        """
        self.raw_dir = raw_dir or config.RAW_DATA_DIR
        self.clean_dir = clean_dir or config.CLEAN_DATA_DIR
        self.max_file_size = (
            config.MAX_OUTPUT_FILE_SIZE if max_file_size is None else max_file_size
        )
        self.max_words = config.MAX_OUTPUT_WORDS if max_words is None else max_words
        self.ensure_clean_directory()

    def ensure_clean_directory(self) -> None:
        """Ensure the output directory exists."""
        os.makedirs(self.clean_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------------------

    def count_words(self, text: str) -> int:
        """Count whitespace-separated words in `text`."""
        if not text:
            return 0
        return len(text.split())

    def get_file_word_count(self, filepath: str) -> int:
        """Word count of an existing file, or 0 when it cannot be read."""
        if not os.path.exists(filepath):
            return 0
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                return self.count_words(handle.read())
        except (IOError, OSError):
            return 0

    def get_processed_files(self) -> set:
        """Set of raw JSON files already folded into the output."""
        index_path = os.path.join(self.clean_dir, PROCESSED_INDEX)
        if not os.path.exists(index_path):
            return set()
        try:
            with open(index_path, "r", encoding="utf-8") as handle:
                return {line.strip() for line in handle if line.strip()}
        except (IOError, OSError) as exc:
            logger.warning("Could not read processed-file index: %s", exc)
            return set()

    def mark_file_processed(self, filename: str) -> None:
        """Record a raw JSON file as processed."""
        index_path = os.path.join(self.clean_dir, PROCESSED_INDEX)
        try:
            with open(index_path, "a", encoding="utf-8") as handle:
                handle.write("{}\n".format(filename))
        except (IOError, OSError) as exc:
            logger.error("Could not mark %s as processed: %s", filename, exc)

    # ------------------------------------------------------------------
    # Text cleaning
    # ------------------------------------------------------------------

    def clean_text(self, text: str) -> str:
        """
        Strip HTML, markdown and Reddit-specific noise out of `text`.

        Args:
            text: Raw text to clean.

        Returns:
            Cleaned text, or an empty string when nothing survives.
        """
        if not text or not text.strip():
            return ""

        text = html.unescape(text)
        text = _HTML_TAG_RE.sub("", text)
        text = _MARKDOWN_LINK_RE.sub(r"\1", text)
        text = _URL_RE.sub("", text)
        text = _USER_MENTION_RE.sub("", text)
        text = _SUBREDDIT_MENTION_RE.sub("", text)

        # Emphasis is unwrapped before list markers are stripped: doing it the
        # other way round eats the leading asterisks of "**bold**" and leaves
        # the trailing ones stranded.
        text = _BOLD_RE.sub(r"\1", text)
        text = _ITALIC_RE.sub(r"\1", text)
        text = _CODE_RE.sub(r"\1", text)
        text = _STRIKE_RE.sub(r"\1", text)
        text = _LINE_MARKER_RE.sub("", text)

        text = _DOTS_RE.sub("...", text)
        text = _BANGS_RE.sub("!", text)
        text = _QUESTIONS_RE.sub("?", text)

        text = _BLANK_LINES_RE.sub("\n\n", text)
        text = _HORIZONTAL_SPACE_RE.sub(" ", text)

        return text.strip()

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_comment_for_output(self, comment: Dict[str, Any], depth: int = 0) -> str:
        """
        Render a comment and its replies as indented text.

        Args:
            comment: Comment dictionary from a raw JSON batch.
            depth: Nesting depth, used for indentation.

        Returns:
            Formatted text, or an empty string when the comment and all of its
            replies are empty.
        """
        body = self.clean_text(comment.get("body", ""))

        reply_blocks = []
        for reply in comment.get("replies") or []:
            rendered = self.format_comment_for_output(reply, depth + 1)
            if rendered:
                reply_blocks.append(rendered)

        # A deleted comment that still has visible replies is kept as a stub so
        # the reply thread does not lose its structure.
        if not body and not reply_blocks:
            return ""

        indent = "  " * depth
        body_indent = "  " * (depth + 1)

        lines = [
            "{}+- COMMENT ID: {}".format(indent, comment.get("id", "")),
            "{}|  AUTHOR: {}{}".format(
                indent,
                comment.get("author", "[deleted]"),
                " (OP)" if comment.get("is_submitter") else "",
            ),
            "{}|  DATE: {}".format(indent, comment.get("created_date", "")),
            "{}|  UPVOTES: {}".format(indent, comment.get("upvotes", 0)),
            "{}+-".format(indent),
        ]

        if body:
            for line in body.split("\n"):
                lines.append("{}{}".format(body_indent, line) if line.strip() else "")
        else:
            lines.append("{}[removed]".format(body_indent))

        lines.append("")
        lines.extend(reply_blocks)

        return "\n".join(lines)

    def format_post_for_output(self, post: Dict[str, Any]) -> str:
        """
        Render a post and its comment tree as text.

        Args:
            post: Post dictionary from a raw JSON batch.

        Returns:
            Formatted text, or an empty string for posts with no content.
        """
        title = self.clean_text(post.get("title", ""))
        text = self.clean_text(post.get("text", ""))
        comments = post.get("comments") or []

        comment_blocks = []
        for comment in comments:
            rendered = self.format_comment_for_output(comment, depth=0)
            if rendered:
                comment_blocks.append(rendered)

        if not title and not text and not comment_blocks:
            return ""

        rule = "=" * 100
        lines = [
            rule,
            "POST ID: {}".format(post.get("id", "")),
            "AUTHOR: {}".format(post.get("author", "[deleted]")),
            "DATE: {}".format(post.get("created_date", "")),
            "UPVOTES: {}".format(post.get("upvotes", 0)),
            "TOTAL COMMENTS: {}".format(post.get("num_comments", 0)),
            "SCRAPED COMMENTS: {}".format(_count_comments(comments)),
            "-" * 100,
        ]

        if title:
            lines.extend(["TITLE: {}".format(title), ""])

        if text:
            lines.extend(["POST CONTENT:", text, ""])

        if comment_blocks:
            lines.extend(["COMMENTS:", rule])
            lines.extend(comment_blocks)
            lines.append(rule)
        else:
            lines.append("NO COMMENTS SCRAPED")

        lines.extend([rule, ""])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Output files
    # ------------------------------------------------------------------

    def get_json_files(self) -> List[str]:
        """Sorted list of raw JSON batch files awaiting processing."""
        if not os.path.isdir(self.raw_dir):
            logger.error("Raw directory %s does not exist", self.raw_dir)
            return []
        return sorted(
            name
            for name in os.listdir(self.raw_dir)
            if name.endswith(".json") and not name.startswith("scraping_progress")
        )

    def load_json_file(self, filename: str) -> List[Dict[str, Any]]:
        """
        Load posts from a raw JSON batch.

        Args:
            filename: File name inside `raw_dir`.

        Returns:
            List of post dictionaries (empty when the file is unreadable).
        """
        filepath = os.path.join(self.raw_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, IOError, OSError) as exc:
            logger.error("Error loading %s: %s", filename, exc)
            return []

        if isinstance(data, list):
            return [post for post in data if isinstance(post, dict)]
        if isinstance(data, dict):
            return [data]

        logger.warning("Unexpected data format in %s", filename)
        return []

    def get_next_output_filename(self) -> str:
        """Path of the next unused output file."""
        counter = 1
        while True:
            filepath = os.path.join(
                self.clean_dir, "{}{:04d}.txt".format(OUTPUT_PREFIX, counter)
            )
            if not os.path.exists(filepath):
                return filepath
            counter += 1

    def get_current_output_file(self) -> str:
        """
        Path of the output file to append to.

        Reuses the newest file while it is still under both budgets, otherwise
        starts a new one.
        """
        existing = sorted(
            name
            for name in os.listdir(self.clean_dir)
            if name.startswith(OUTPUT_PREFIX) and name.endswith(".txt")
        )
        if not existing:
            return self.get_next_output_filename()

        filepath = os.path.join(self.clean_dir, existing[-1])
        size = os.path.getsize(filepath)
        words = self.get_file_word_count(filepath)

        if size < self.max_file_size and words < self.max_words:
            return filepath

        logger.info(
            "Rotating output. Current file: %.1fMB, %d words",
            size / (1024 * 1024),
            words,
        )
        return self.get_next_output_filename()

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def process_posts(self) -> Dict[str, Any]:
        """
        Convert every unprocessed raw batch into cleaned text.

        Returns:
            Summary dict with `posts_written`, `files_processed` and
            `output_files`.
        """
        logger.info("Starting text cleaning process")

        summary = {"posts_written": 0, "files_processed": 0, "output_files": []}

        processed_files = self.get_processed_files()
        json_files = self.get_json_files()

        if not json_files:
            logger.warning("No JSON files found in %s", self.raw_dir)
            return summary

        pending = [name for name in json_files if name not in processed_files]
        if not pending:
            logger.info("All %d raw files have already been processed", len(json_files))
            return summary

        current_path = self.get_current_output_file()
        # Byte and word budgets are tracked in memory: re-reading a multi-hundred
        # megabyte output file after every post made cleaning quadratic.
        current_size = os.path.getsize(current_path) if os.path.exists(current_path) else 0
        current_words = self.get_file_word_count(current_path)
        summary["output_files"].append(current_path)

        handle = open(current_path, "a", encoding="utf-8")
        try:
            file_progress = tqdm(pending, desc="Processing files", unit="file", dynamic_ncols=True)
            for json_filename in file_progress:
                file_progress.set_postfix({"file": json_filename})
                posts = self.load_json_file(json_filename)

                if not posts:
                    logger.warning("No posts found in %s", json_filename)
                    self.mark_file_processed(json_filename)
                    summary["files_processed"] += 1
                    continue

                for post in posts:
                    formatted = self.format_post_for_output(post)
                    if not formatted:
                        continue

                    post_size = len(formatted.encode("utf-8"))
                    post_words = self.count_words(formatted)

                    rotate = current_size > 0 and (
                        current_size + post_size > self.max_file_size
                        or current_words + post_words > self.max_words
                    )
                    if rotate:
                        handle.close()
                        current_path = self.get_next_output_filename()
                        current_size = 0
                        current_words = 0
                        handle = open(current_path, "a", encoding="utf-8")
                        summary["output_files"].append(current_path)
                        logger.info("Opened new output file: %s", os.path.basename(current_path))

                    handle.write(formatted)
                    current_size += post_size
                    current_words += post_words
                    summary["posts_written"] += 1

                # Flush before recording the file as done so a crash cannot mark
                # a batch processed whose text is still sitting in the buffer.
                handle.flush()
                self.mark_file_processed(json_filename)
                summary["files_processed"] += 1
            file_progress.close()
        finally:
            handle.close()

        logger.info(
            "Text cleaning completed. Posts written: %d, files processed: %d",
            summary["posts_written"],
            summary["files_processed"],
        )
        logger.info("Output written to %s", self.clean_dir)
        return summary

    def get_cleaning_stats(self) -> Dict[str, Any]:
        """Statistics about the raw inputs and cleaned outputs."""
        output_files = [
            name
            for name in os.listdir(self.clean_dir)
            if name.startswith(OUTPUT_PREFIX) and name.endswith(".txt")
        ]
        total_size = sum(
            os.path.getsize(os.path.join(self.clean_dir, name)) for name in output_files
        )
        return {
            "raw_files": len(self.get_json_files()),
            "processed_files": len(self.get_processed_files()),
            "output_files": len(output_files),
            "total_output_size": total_size,
        }


def _count_comments(comments: List[Dict[str, Any]]) -> int:
    """Count a comment tree, including every nested reply."""
    total = 0
    for comment in comments:
        total += 1 + _count_comments(comment.get("replies") or [])
    return total


def main() -> int:
    """Run the cleaner standalone."""
    from logging_setup import configure_logging

    configure_logging("cleaner.log")

    try:
        cleaner = TextCleaner()
        stats = cleaner.get_cleaning_stats()
        logger.info(
            "Starting with %d raw files, %d already processed",
            stats["raw_files"],
            stats["processed_files"],
        )
        cleaner.process_posts()
        final = cleaner.get_cleaning_stats()
        logger.info("Cleaning completed:")
        logger.info("  raw files: %d", final["raw_files"])
        logger.info("  processed files: %d", final["processed_files"])
        logger.info("  output files: %d", final["output_files"])
        logger.info("  total output size: %.2f MB", final["total_output_size"] / (1024 * 1024))
    except Exception as exc:
        logger.error("Cleaning failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
