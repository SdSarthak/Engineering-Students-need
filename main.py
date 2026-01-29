"""
Main Pipeline for Reddit Engineering Students Scraper
Orchestrates the scraping and cleaning process.
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from scraper import RedditScraper
from cleaner import TextCleaner
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pipeline.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class Pipeline:
    """Main pipeline for scraping and cleaning Reddit posts."""
    
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        """
        Initialize the pipeline.
        
        Args:
            client_id: Reddit app client ID
            client_secret: Reddit app client secret
            user_agent: User agent string
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.scraper = None
        self.cleaner = None
        
    def initialize_components(self):
        """Initialize scraper and cleaner components."""
        try:
            self.scraper = RedditScraper(self.client_id, self.client_secret, self.user_agent)
            self.cleaner = TextCleaner()
            logger.info("Pipeline components initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise
    
    def run_scraping(self, limit: int = 0, batch_size: int = 50):
        """
        Run the scraping process.
        
        Args:
            limit: Maximum number of posts to scrape
            batch_size: Number of posts per batch
        """
        logger.info("Starting scraping phase")
        try:
            self.scraper.scrape_posts(limit=limit, batch_size=batch_size)
            logger.info("Scraping phase completed successfully")
        except Exception as e:
            logger.error(f"Scraping phase failed: {e}")
            raise
    
    def run_cleaning(self):
        """Run the text cleaning process."""
        logger.info("Starting cleaning phase")
        try:
            self.cleaner.process_posts()
            logger.info("Cleaning phase completed successfully")
        except Exception as e:
            logger.error(f"Cleaning phase failed: {e}")
            raise
    
    def run_full_pipeline(self, limit: int = 0, batch_size: int = 50, skip_scraping: bool = False):
        """
        Run the complete pipeline.
        
        Args:
            limit: Maximum number of posts to scrape
            batch_size: Number of posts per batch
            skip_scraping: Skip scraping phase if True
        """
        start_time = datetime.now()
        logger.info(f"Starting full pipeline at {start_time}")
        
        try:
            # Initialize components
            self.initialize_components()
            
            # Run scraping (unless skipped)
            if not skip_scraping:
                self.run_scraping(limit=limit, batch_size=batch_size)
            else:
                logger.info("Skipping scraping phase")
            
            # Run cleaning
            self.run_cleaning()
            
            # Pipeline completed
            end_time = datetime.now()
            duration = end_time - start_time
            logger.info(f"Pipeline completed successfully in {duration}")
            
            # Print summary
            self.print_summary()
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            sys.exit(1)
    
    def print_summary(self):
        """Print a summary of the pipeline results."""
        try:
            # Get scraper stats
            progress_file = os.path.join("data/raw", "scraping_progress.json")
            scraper_stats = {}
            if os.path.exists(progress_file):
                import json
                with open(progress_file, 'r') as f:
                    scraper_stats = json.load(f)
            
            # Get cleaner stats
            cleaner_stats = self.cleaner.get_cleaning_stats()
            
            print("\n" + "="*60)
            print("PIPELINE SUMMARY")
            print("="*60)
            print(f"Total posts scraped: {scraper_stats.get('total_posts', 0)}")
            print(f"Raw JSON files: {cleaner_stats['raw_files']}")
            print(f"Processed files: {cleaner_stats['processed_files']}")
            print(f"Output text files: {cleaner_stats['output_files']}")
            print(f"Total output size: {cleaner_stats['total_output_size'] / (1024*1024):.2f} MB")
            print(f"Last run: {scraper_stats.get('last_run', 'Unknown')}")
            print("="*60)
            
        except Exception as e:
            logger.error(f"Could not generate summary: {e}")


def get_credentials_from_config():
    """Get Reddit credentials from config file."""
    return config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET, config.REDDIT_USER_AGENT


def get_credentials_from_input():
    """Get Reddit credentials from user input."""
    print("Reddit API Credentials Setup")
    print("="*40)
    print("To get your credentials:")
    print("1. Go to https://www.reddit.com/prefs/apps")
    print("2. Click 'Create App' or 'Create Another App'")
    print("3. Choose 'script' as the app type")
    print("4. Copy the client ID and secret below")
    print()
    
    client_id = input("Enter your Reddit Client ID: ").strip()
    client_secret = input("Enter your Reddit Client Secret: ").strip()
    username = input("Enter your Reddit username (for user agent): ").strip()
    
    user_agent = f"EngineeringStudents Scraper v1.0 by /u/{username}" if username else "EngineeringStudents Scraper v1.0"
    
    return client_id, client_secret, user_agent


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(description='Reddit Engineering Students Scraper Pipeline')
    parser.add_argument('--limit', type=int, default=0, help='Maximum number of posts to scrape (default: 0 = unlimited)')
    parser.add_argument('--batch-size', type=int, default=50, help='Number of posts per batch (default: 50)')
    parser.add_argument('--skip-scraping', action='store_true', help='Skip scraping phase and only run cleaning')
    parser.add_argument('--clean-only', action='store_true', help='Only run the cleaning phase')
    parser.add_argument('--scrape-only', action='store_true', help='Only run the scraping phase')
    
    args = parser.parse_args()
    
    # Get credentials
    client_id, client_secret, user_agent = get_credentials_from_config()
    
    if not client_id or not client_secret:
        logger.info("Credentials not found in config file")
        client_id, client_secret, user_agent = get_credentials_from_input()
    
    if not client_id or not client_secret:
        logger.error("Reddit credentials are required")
        print("\nError: Reddit credentials are required to run the scraper.")
        print("Please set environment variables REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET,")
        print("or run the script interactively to enter them.")
        sys.exit(1)
    
    # Initialize and run pipeline
    pipeline = Pipeline(client_id, client_secret, user_agent)
    
    try:
        if args.clean_only:
            # Only run cleaning
            pipeline.initialize_components()
            pipeline.run_cleaning()
        elif args.scrape_only:
            # Only run scraping
            pipeline.initialize_components()
            pipeline.run_scraping(limit=args.limit, batch_size=args.batch_size)
        else:
            # Run full pipeline
            pipeline.run_full_pipeline(
                limit=args.limit,
                batch_size=args.batch_size,
                skip_scraping=args.skip_scraping
            )
    
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        print("\nPipeline interrupted by user. Progress has been saved.")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        print(f"\nPipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
