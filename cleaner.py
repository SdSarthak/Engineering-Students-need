"""
Text Cleaner for Reddit Posts
Processes raw JSON files from scraper and converts them to clean, human-readable text files.
Handles file size limits and text cleaning operations.
"""

import json
import os
import re
import logging
from typing import List, Dict, Any, Generator
from datetime import datetime
import html
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cleaner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TextCleaner:
    """Text cleaner for Reddit posts."""
    
    def __init__(self, raw_dir: str = "data/raw", clean_dir: str = "data/clean", max_file_size: int = 200 * 1024 * 1024, max_words: int = 500000):
        """
        Initialize text cleaner.
        
        Args:
            raw_dir: Directory containing raw JSON files
            clean_dir: Directory to save cleaned text files
            max_file_size: Maximum file size in bytes (default 200MB)
            max_words: Maximum word count per file (default 500,000 words)
        """
        self.raw_dir = raw_dir
        self.clean_dir = clean_dir
        self.max_file_size = max_file_size
        self.max_words = max_words
        self.ensure_clean_directory()
        
    def ensure_clean_directory(self):
        """Ensure the clean directory exists."""
        os.makedirs(self.clean_dir, exist_ok=True)
    
    def count_words(self, text: str) -> int:
        """Count words in text."""
        if not text:
            return 0
        # Split by whitespace and filter out empty strings
        words = [word for word in text.split() if word.strip()]
        return len(words)
    
    def get_file_word_count(self, filepath: str) -> int:
        """Get word count of existing file."""
        if not os.path.exists(filepath):
            return 0
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                return self.count_words(content)
        except IOError:
            return 0
    
    def get_processed_files(self) -> set:
        """Get set of already processed JSON files."""
        processed_file = os.path.join(self.clean_dir, "processed_files.txt")
        if os.path.exists(processed_file):
            try:
                with open(processed_file, 'r', encoding='utf-8') as f:
                    return set(line.strip() for line in f if line.strip())
            except IOError:
                pass
        return set()
    
    def mark_file_processed(self, filename: str):
        """Mark a JSON file as processed."""
        processed_file = os.path.join(self.clean_dir, "processed_files.txt")
        try:
            with open(processed_file, 'a', encoding='utf-8') as f:
                f.write(f"{filename}\n")
        except IOError as e:
            logger.error(f"Could not mark file as processed: {e}")
    
    def clean_text(self, text: str) -> str:
        """
        Clean text content by removing HTML, links, and special characters.
        
        Args:
            text: Raw text to clean
            
        Returns:
            Cleaned text
        """
        if not text or text.strip() == "":
            return ""
        
        # Decode HTML entities
        text = html.unescape(text)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove Reddit markdown links [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        
        # Remove standalone URLs
        text = re.sub(r'https?://[^\s]+', '', text)
        
        # Remove Reddit user mentions
        text = re.sub(r'/u/[A-Za-z0-9_-]+', '', text)
        text = re.sub(r'u/[A-Za-z0-9_-]+', '', text)
        
        # Remove subreddit mentions
        text = re.sub(r'/r/[A-Za-z0-9_-]+', '', text)
        text = re.sub(r'r/[A-Za-z0-9_-]+', '', text)
        
        # Remove excessive whitespace and newlines
        text = re.sub(r'\n\s*\n', '\n\n', text)  # Multiple newlines to double newlines
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single space
        
        # Remove special Reddit formatting
        text = re.sub(r'^\s*[>\-*+]\s*', '', text, flags=re.MULTILINE)  # Remove quote markers and list markers
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Remove bold formatting
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Remove italic formatting
        text = re.sub(r'`([^`]+)`', r'\1', text)  # Remove code formatting
        text = re.sub(r'~~([^~]+)~~', r'\1', text)  # Remove strikethrough
        
        # Remove excessive punctuation
        text = re.sub(r'[.]{3,}', '...', text)  # Multiple dots to three dots
        text = re.sub(r'[!]{2,}', '!', text)  # Multiple exclamation marks to one
        text = re.sub(r'[?]{2,}', '?', text)  # Multiple question marks to one
        
        # Clean up the text
        text = text.strip()
        
        return text
    
    def format_comment_for_output(self, comment: Dict[str, Any], depth: int = 0) -> str:
        """
        Format a single comment and its replies for text output.
        
        Args:
            comment: Comment dictionary from JSON
            depth: Current nesting depth for indentation
            
        Returns:
            Formatted text string
        """
        # Extract and clean data
        body = self.clean_text(comment.get('body', ''))
        author = comment.get('author', '[deleted]')
        created_date = comment.get('created_date', '')
        upvotes = comment.get('upvotes', 0)
        comment_id = comment.get('id', '')
        is_submitter = comment.get('is_submitter', False)
        
        # Skip empty comments
        if not body:
            return ""
        
        # Create indentation based on depth
        indent = "  " * depth
        reply_indent = "  " * (depth + 1)
        
        # Format the comment
        output_lines = []
        
        # Comment header
        output_lines.append(f"{indent}┌─ COMMENT ID: {comment_id}")
        output_lines.append(f"{indent}│  AUTHOR: {author}{' (OP)' if is_submitter else ''}")
        output_lines.append(f"{indent}│  DATE: {created_date}")
        output_lines.append(f"{indent}│  UPVOTES: {upvotes}")
        output_lines.append(f"{indent}└─")
        
        # Comment body
        if body:
            # Split body into lines and indent each line
            body_lines = body.split('\n')
            for line in body_lines:
                if line.strip():  # Only add non-empty lines
                    output_lines.append(f"{reply_indent}{line}")
                else:
                    output_lines.append("")  # Preserve empty lines
        
        output_lines.append("")  # Add spacing after comment
        
        # Process replies recursively
        replies = comment.get('replies', [])
        if replies:
            for reply in replies:
                reply_output = self.format_comment_for_output(reply, depth + 1)
                if reply_output:
                    output_lines.append(reply_output)
        
        return "\n".join(output_lines)

    def format_post_for_output(self, post: Dict[str, Any]) -> str:
        """
        Format a single post and all its comments for text output.
        
        Args:
            post: Post dictionary from JSON
            
        Returns:
            Formatted text string
        """
        # Extract and clean data
        title = self.clean_text(post.get('title', ''))
        text = self.clean_text(post.get('text', ''))
        author = post.get('author', '[deleted]')
        created_date = post.get('created_date', '')
        upvotes = post.get('upvotes', 0)
        num_comments = post.get('num_comments', 0)
        post_id = post.get('id', '')
        comments = post.get('comments', [])
        
        # Skip posts with no meaningful content
        if not title and not text and not comments:
            return ""
        
        # Format the post
        output_lines = []
        output_lines.append("=" * 100)
        output_lines.append(f"POST ID: {post_id}")
        output_lines.append(f"AUTHOR: {author}")
        output_lines.append(f"DATE: {created_date}")
        output_lines.append(f"UPVOTES: {upvotes}")
        output_lines.append(f"TOTAL COMMENTS: {num_comments}")
        output_lines.append(f"SCRAPED COMMENTS: {len(comments)}")
        output_lines.append("-" * 100)
        
        if title:
            output_lines.append(f"TITLE: {title}")
            output_lines.append("")
        
        if text:
            output_lines.append("POST CONTENT:")
            output_lines.append(text)
            output_lines.append("")
        
        # Add comments section
        if comments:
            output_lines.append("COMMENTS:")
            output_lines.append("=" * 100)
            
            for comment in comments:
                comment_output = self.format_comment_for_output(comment, depth=0)
                if comment_output:
                    output_lines.append(comment_output)
            
            output_lines.append("=" * 100)
        else:
            output_lines.append("NO COMMENTS SCRAPED")
        
        output_lines.append("=" * 100)
        output_lines.append("")
        
        return "\n".join(output_lines)
    
    def get_json_files(self) -> List[str]:
        """Get list of JSON files to process."""
        if not os.path.exists(self.raw_dir):
            logger.error(f"Raw directory {self.raw_dir} does not exist")
            return []
        
        json_files = []
        for filename in os.listdir(self.raw_dir):
            if filename.endswith('.json') and not filename.startswith('scraping_progress'):
                json_files.append(filename)
        
        return sorted(json_files)
    
    def load_json_file(self, filename: str) -> List[Dict[str, Any]]:
        """
        Load posts from a JSON file.
        
        Args:
            filename: Name of the JSON file
            
        Returns:
            List of post dictionaries
        """
        filepath = os.path.join(self.raw_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                else:
                    logger.warning(f"Unexpected data format in {filename}")
                    return []
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading {filename}: {e}")
            return []
    
    def get_next_output_filename(self) -> str:
        """Get the next available output filename."""
        counter = 1
        while True:
            filename = f"cleaned_posts_{counter:04d}.txt"
            filepath = os.path.join(self.clean_dir, filename)
            if not os.path.exists(filepath):
                return filepath
            counter += 1
    
    def get_current_output_file(self) -> str:
        """Get the current output file or create a new one if needed."""
        # Find the most recent output file
        output_files = [f for f in os.listdir(self.clean_dir) if f.startswith('cleaned_posts_') and f.endswith('.txt')]
        
        if not output_files:
            return self.get_next_output_filename()
        
        # Get the most recent file
        latest_file = sorted(output_files)[-1]
        filepath = os.path.join(self.clean_dir, latest_file)
        
        # Check if it's under both size and word limits
        file_size = os.path.getsize(filepath)
        word_count = self.get_file_word_count(filepath)
        
        if file_size < self.max_file_size and word_count < self.max_words:
            return filepath
        else:
            logger.info(f"Creating new file. Current file: {file_size / (1024*1024):.1f}MB, {word_count:,} words")
            return self.get_next_output_filename()
    
    def process_posts(self):
        """Process all JSON files and create cleaned text files."""
        logger.info("Starting text cleaning process")
        
        processed_files = self.get_processed_files()
        json_files = self.get_json_files()
        
        if not json_files:
            logger.warning("No JSON files found to process")
            return
        
        # Filter out already processed files
        files_to_process = [f for f in json_files if f not in processed_files]
        
        if not files_to_process:
            logger.info("All files have already been processed")
            return
        
        total_posts_processed = 0
        current_output_file = self.get_current_output_file()
        
        # Create progress bar for files
        file_progress = tqdm(
            files_to_process,
            desc="Processing files",
            unit="file",
            dynamic_ncols=True,
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} files [{elapsed}<{remaining}, {rate_fmt}]'
        )
        
        for json_filename in file_progress:
            file_progress.set_postfix({'current_file': json_filename})
            
            posts = self.load_json_file(json_filename)
            
            if not posts:
                logger.warning(f"No posts found in {json_filename}")
                self.mark_file_processed(json_filename)
                continue
            
            # Create progress bar for posts in this file
            post_progress = tqdm(
                posts,
                desc=f"Processing {json_filename}",
                unit="post",
                leave=False,
                dynamic_ncols=True,
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} posts [{elapsed}<{remaining}, {rate_fmt}]'
            )
            
            # Process posts and write to output file
            with open(current_output_file, 'a', encoding='utf-8') as output_file:
                for post in post_progress:
                    formatted_post = self.format_post_for_output(post)
                    if formatted_post:
                        # Check if adding this post would exceed limits
                        post_size = len(formatted_post.encode('utf-8'))
                        post_word_count = self.count_words(formatted_post)
                        
                        current_size = os.path.getsize(current_output_file)
                        current_word_count = self.get_file_word_count(current_output_file)
                        
                        # Check both file size and word count limits
                        if (current_size + post_size > self.max_file_size or 
                            current_word_count + post_word_count > self.max_words):
                            # Close current file and start a new one
                            output_file.close()
                            current_output_file = self.get_next_output_filename()
                            logger.info(f"Created new output file: {os.path.basename(current_output_file)}")
                            
                            # Reopen for writing
                            output_file = open(current_output_file, 'a', encoding='utf-8')
                        
                        output_file.write(formatted_post)
                        total_posts_processed += 1
                        
                        # Update post progress
                        current_size = os.path.getsize(current_output_file)
                        current_word_count = self.get_file_word_count(current_output_file)
                        post_progress.set_postfix({
                            'comments': len(post.get('comments', [])),
                            'size': f"{current_size / (1024*1024):.1f}MB",
                            'words': f"{current_word_count:,}"
                        })
            
            # Close post progress bar
            post_progress.close()
            
            # Mark file as processed
            self.mark_file_processed(json_filename)
            
            # Update file progress
            file_progress.set_postfix({
                'processed_posts': total_posts_processed,
                'current_file': json_filename
            })
        
        # Close file progress bar
        file_progress.close()
        
        logger.info(f"Text cleaning completed. Total posts processed: {total_posts_processed}")
        logger.info(f"Output files saved in: {self.clean_dir}")
    
    def get_cleaning_stats(self) -> Dict[str, Any]:
        """Get statistics about the cleaning process."""
        stats = {
            "raw_files": len(self.get_json_files()),
            "processed_files": len(self.get_processed_files()),
            "output_files": len([f for f in os.listdir(self.clean_dir) if f.startswith('cleaned_posts_')]),
            "total_output_size": 0
        }
        
        # Calculate total output size
        for filename in os.listdir(self.clean_dir):
            if filename.startswith('cleaned_posts_') and filename.endswith('.txt'):
                filepath = os.path.join(self.clean_dir, filename)
                stats["total_output_size"] += os.path.getsize(filepath)
        
        return stats


def main():
    """Main function to run the cleaner."""
    try:
        cleaner = TextCleaner()
        
        # Get initial stats
        stats = cleaner.get_cleaning_stats()
        logger.info(f"Starting with {stats['raw_files']} raw files, {stats['processed_files']} already processed")
        
        # Process posts
        cleaner.process_posts()
        
        # Get final stats
        final_stats = cleaner.get_cleaning_stats()
        logger.info(f"Cleaning completed:")
        logger.info(f"  - Raw files: {final_stats['raw_files']}")
        logger.info(f"  - Processed files: {final_stats['processed_files']}")
        logger.info(f"  - Output files: {final_stats['output_files']}")
        logger.info(f"  - Total output size: {final_stats['total_output_size'] / (1024*1024):.2f} MB")
        
    except Exception as e:
        logger.error(f"Cleaning failed: {e}")


if __name__ == "__main__":
    main()
