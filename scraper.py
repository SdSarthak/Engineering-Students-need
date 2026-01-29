"""
Reddit Scraper for r/EngineeringStudents
Scrapes posts using PRAW (Python Reddit API Wrapper) with free client credentials.
Respects rate limits and Reddit's terms of service.
"""

import praw
import json
import os
import time
from datetime import datetime
from typing import List, Dict, Any
import logging
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class RedditScraper:
    """Reddit scraper for r/EngineeringStudents using PRAW."""
    
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        """
        Initialize Reddit scraper with PRAW.
        
        Args:
            client_id: Reddit app client ID (free)
            client_secret: Reddit app client secret (free)
            user_agent: User agent string for API requests
        """
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        self.subreddit_name = "EngineeringStudents"
        self.data_dir = "data/raw"
        self.ensure_data_directory()
        
    def ensure_data_directory(self):
        """Ensure the data directory exists."""
        os.makedirs(self.data_dir, exist_ok=True)
        
    def get_progress_file(self) -> str:
        """Get the path to the progress tracking file."""
        return os.path.join(self.data_dir, "scraping_progress.json")
    
    def load_progress(self) -> Dict[str, Any]:
        """Load scraping progress from file."""
        progress_file = self.get_progress_file()
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load progress file: {e}")
        return {"last_processed_id": None, "total_posts": 0, "last_run": None}
    
    def save_progress(self, progress: Dict[str, Any]):
        """Save scraping progress to file."""
        progress_file = self.get_progress_file()
        try:
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress, f, indent=2, default=str)
        except IOError as e:
            logger.error(f"Could not save progress file: {e}")
    
    def extract_comment_data(self, comment, depth: int = 0) -> Dict[str, Any]:
        """
        Extract data from a Reddit comment and all its replies recursively.
        
        Args:
            comment: PRAW comment object
            depth: Current nesting depth for formatting
            
        Returns:
            Dictionary containing comment data and replies
        """
        try:
            # Handle deleted/removed comments
            author = str(comment.author) if comment.author else "[deleted]"
            body = comment.body if comment.body else ""
            
            # Clean up text content
            if body in ["[deleted]", "[removed]", ""]:
                body = ""
            
            comment_data = {
                "id": comment.id,
                "author": author,
                "body": body,
                "created_utc": comment.created_utc,
                "created_date": datetime.fromtimestamp(comment.created_utc).isoformat(),
                "upvotes": comment.score,
                "depth": depth,
                "permalink": f"https://reddit.com{comment.permalink}",
                "is_submitter": comment.is_submitter,
                "scraped_at": datetime.now().isoformat()
            }
            
            # Recursively extract replies
            replies = []
            if hasattr(comment, 'replies') and comment.replies:
                try:
                    # Expand comment replies
                    comment.replies.replace_more(limit=None)
                    for reply in comment.replies.list():
                        reply_data = self.extract_comment_data(reply, depth + 1)
                        if reply_data:
                            replies.append(reply_data)
                except Exception as e:
                    logger.warning(f"Error extracting replies for comment {comment.id}: {e}")
            
            comment_data["replies"] = replies
            return comment_data
            
        except Exception as e:
            logger.error(f"Error extracting data from comment {comment.id}: {e}")
            return None

    def extract_post_data(self, submission) -> Dict[str, Any]:
        """
        Extract relevant data from a Reddit submission including all comments.
        
        Args:
            submission: PRAW submission object
            
        Returns:
            Dictionary containing post data and all comments
        """
        try:
            # Handle deleted/removed posts
            author = str(submission.author) if submission.author else "[deleted]"
            title = submission.title if submission.title else "[no title]"
            selftext = submission.selftext if submission.selftext else ""
            
            # Clean up text content
            if selftext in ["[deleted]", "[removed]", ""]:
                selftext = ""
            
            post_data = {
                "id": submission.id,
                "title": title,
                "text": selftext,
                "author": author,
                "created_utc": submission.created_utc,
                "created_date": datetime.fromtimestamp(submission.created_utc).isoformat(),
                "upvotes": submission.score,
                "num_comments": submission.num_comments,
                "url": submission.url,
                "permalink": f"https://reddit.com{submission.permalink}",
                "is_self": submission.is_self,
                "over_18": submission.over_18,
                "stickied": submission.stickied,
                "subreddit": str(submission.subreddit),
                "scraped_at": datetime.now().isoformat(),
                "comments": []
            }
            
            # Extract all comments
            try:
                # Expand all comment trees
                submission.comments.replace_more(limit=None)
                logger.info(f"Extracting comments for post {submission.id} ({submission.num_comments} total)")
                
                comment_count = 0
                for comment in submission.comments.list():
                    comment_data = self.extract_comment_data(comment, depth=0)
                    if comment_data:
                        post_data["comments"].append(comment_data)
                        comment_count += 1
                
                logger.info(f"Successfully extracted {comment_count} comments for post {submission.id}")
                
            except Exception as e:
                logger.error(f"Error extracting comments for post {submission.id}: {e}")
                # Continue with post data even if comments fail
            
            return post_data
            
        except Exception as e:
            logger.error(f"Error extracting data from post {submission.id}: {e}")
            return None
    
    def save_posts_batch(self, posts: List[Dict[str, Any]], batch_num: int):
        """
        Save a batch of posts to a JSON file.
        
        Args:
            posts: List of post dictionaries
            batch_num: Batch number for filename
        """
        if not posts:
            return
            
        filename = f"posts_batch_{batch_num:04d}.json"
        filepath = os.path.join(self.data_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(posts, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(posts)} posts to {filename}")
        except IOError as e:
            logger.error(f"Could not save batch {batch_num}: {e}")
    
    def scrape_posts(self, limit: int = 0, batch_size: int = 50):
        """
        Scrape posts from r/EngineeringStudents with proper pagination.
        
        Args:
            limit: Maximum number of posts to scrape (0 for no limit - scrape all available)
            batch_size: Number of posts to save per batch
        """
        logger.info(f"Starting to scrape r/{self.subreddit_name}")
        if limit == 0:
            logger.info("No limit set - will scrape ALL available posts using pagination")
        
        # Load previous progress
        progress = self.load_progress()
        last_processed_id = progress.get("last_processed_id")
        total_posts = progress.get("total_posts", 0)
        
        try:
            subreddit = self.reddit.subreddit(self.subreddit_name)
            
            current_batch = []
            batch_num = (total_posts // batch_size) + 1
            processed_count = 0
            skipped_count = 0
            consecutive_empty_pages = 0
            max_empty_pages = 3  # Stop after 3 consecutive empty pages
            
            # Create progress bar
            progress_bar = tqdm(
                desc="Scraping posts",
                unit="posts",
                dynamic_ncols=True,
                bar_format='{l_bar}{bar}| {n_fmt} posts [{elapsed}<{remaining}, {rate_fmt}]'
            )
            
            # Use different sorting methods to get more posts
            sort_methods = ['hot', 'top']
            sort_method_index = 0
            
            while True:
                # Get posts using current sort method
                current_sort = sort_methods[sort_method_index]
                logger.info(f"Scraping posts sorted by: {current_sort}")
                
                if current_sort == 'hot':
                    posts = subreddit.hot(limit=100)
                elif current_sort == 'top':
                    posts = subreddit.top(limit=100, time_filter='year')
           
                page_posts = list(posts)
                
                if not page_posts:
                    consecutive_empty_pages += 1
                    logger.info(f"Empty page {consecutive_empty_pages}/{max_empty_pages} for {current_sort}")
                    
                    if consecutive_empty_pages >= max_empty_pages:
                        logger.info("Reached maximum empty pages, trying next sort method")
                        sort_method_index += 1
                        consecutive_empty_pages = 0
                        
                        if sort_method_index >= len(sort_methods):
                            logger.info("All sort methods exhausted, stopping scraping")
                            break
                        continue
                else:
                    consecutive_empty_pages = 0
                
                for submission in page_posts:
                    # Skip if we've already processed this post
                    if last_processed_id and submission.id == last_processed_id:
                        skipped_count += 1
                        progress_bar.set_postfix({
                            'processed': processed_count,
                            'skipped': skipped_count,
                            'batch': batch_num,
                            'sort': current_sort
                        })
                        continue
                    
                    # Extract post data
                    post_data = self.extract_post_data(submission)
                    if post_data:
                        current_batch.append(post_data)
                        processed_count += 1
                        
                        # Update progress bar
                        progress_bar.update(1)
                        progress_bar.set_postfix({
                            'processed': processed_count,
                            'skipped': skipped_count,
                            'batch': batch_num,
                            'comments': len(post_data.get('comments', [])),
                            'sort': current_sort
                        })
                        
                        # Save batch when it reaches batch_size
                        if len(current_batch) >= batch_size:
                            self.save_posts_batch(current_batch, batch_num)
                            total_posts += len(current_batch)
                            batch_num += 1
                            current_batch = []
                            
                            # Update progress
                            progress["last_processed_id"] = post_data["id"]
                            progress["total_posts"] = total_posts
                            progress["last_run"] = datetime.now().isoformat()
                            self.save_progress(progress)
                    
                    # Rate limiting - be respectful to Reddit's servers
                    time.sleep(0.2)  # 200ms delay between requests
                    
                    # Break if we've reached the limit
                    if limit > 0 and processed_count >= limit:
                        break
                
                # Break if we've reached the limit
                if limit > 0 and processed_count >= limit:
                    break
                
                # If we got fewer than 100 posts, we might be at the end
                if len(page_posts) < 100:
                    logger.info(f"Got {len(page_posts)} posts (less than 100), trying next sort method")
                    sort_method_index += 1
                    consecutive_empty_pages = 0
                    
                    if sort_method_index >= len(sort_methods):
                        logger.info("All sort methods exhausted, stopping scraping")
                        break
            
            # Save remaining posts in the last batch
            if current_batch:
                self.save_posts_batch(current_batch, batch_num)
                total_posts += len(current_batch)
                progress["total_posts"] = total_posts
            
            # Close progress bar
            progress_bar.close()
            
            # Final progress update
            progress["last_run"] = datetime.now().isoformat()
            self.save_progress(progress)
            
            logger.info(f"Scraping completed. Total posts processed: {total_posts}")
            logger.info(f"Posts skipped (already processed): {skipped_count}")
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            raise
    
    def get_subreddit_info(self) -> Dict[str, Any]:
        """Get basic information about the subreddit."""
        try:
            subreddit = self.reddit.subreddit(self.subreddit_name)
            return {
                "name": subreddit.display_name,
                "title": subreddit.title,
                "description": subreddit.description,
                "subscribers": subreddit.subscribers,
                "created_utc": subreddit.created_utc,
                "public_description": subreddit.public_description
            }
        except Exception as e:
            logger.error(f"Error getting subreddit info: {e}")
            return {}


def main():
    """Main function to run the scraper."""
    # Reddit app credentials (you need to create a free Reddit app)
    # Go to https://www.reddit.com/prefs/apps and create a "script" app
    CLIENT_ID = "your_client_id_here"  # Replace with your client ID
    CLIENT_SECRET = "your_client_secret_here"  # Replace with your client secret
    USER_AGENT = "EngineeringStudents Scraper v1.0 by /u/your_username"
    
    # Check if credentials are set
    if CLIENT_ID == "your_client_id_here" or CLIENT_SECRET == "your_client_secret_here":
        logger.error("Please set your Reddit app credentials in the main() function")
        logger.info("1. Go to https://www.reddit.com/prefs/apps")
        logger.info("2. Click 'Create App' or 'Create Another App'")
        logger.info("3. Choose 'script' as the app type")
        logger.info("4. Copy the client ID and secret to this script")
        return
    
    try:
        # Initialize scraper
        scraper = RedditScraper(CLIENT_ID, CLIENT_SECRET, USER_AGENT)
        
        # Get subreddit info
        subreddit_info = scraper.get_subreddit_info()
        logger.info(f"Scraping r/{subreddit_info.get('name', 'EngineeringStudents')}")
        logger.info(f"Subscribers: {subreddit_info.get('subscribers', 'Unknown')}")
        
        # Start scraping (adjust limit as needed)
        scraper.scrape_posts(limit=500, batch_size=50)  # Scrape 500 posts in batches of 50
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}")


if __name__ == "__main__":
    main()
