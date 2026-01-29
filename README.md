# Reddit Engineering Students Scraper

A modular Python web scraper for collecting posts from r/EngineeringStudents using Reddit's free API. The scraper respects rate limits and Reddit's terms of service while providing clean, human-readable output files.

## Features

- **Respectful Scraping**: Uses PRAW (Python Reddit API Wrapper) with proper rate limiting
- **Modular Design**: Separate components for scraping, cleaning, and orchestration
- **Progress Tracking**: Saves progress to resume interrupted scraping sessions
- **Text Cleaning**: Removes HTML, markdown, and special characters for clean output
- **File Size Management**: Automatically splits output into files ≤ 400MB
- **Comprehensive Logging**: Detailed logs for monitoring and debugging

## Project Structure

```
├── scraper.py          # Reddit scraping logic using PRAW
├── cleaner.py          # Text processing and cleaning
├── main.py            # Pipeline orchestration
├── requirements.txt   # Python dependencies
├── README.md         # This file
├── data/
│   ├── raw/          # Raw JSON files from scraper
│   └── clean/        # Cleaned text files
└── logs/             # Log files (created during execution)
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get Reddit API Credentials

1. Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps)
2. Click "Create App" or "Create Another App"
3. Choose "script" as the app type
4. Note down your **Client ID** and **Client Secret**

### 3. Set Up Credentials

**Option A: Environment Variables (Recommended)**
```bash
export REDDIT_CLIENT_ID="your_client_id_here"
export REDDIT_CLIENT_SECRET="your_client_secret_here"
export REDDIT_USER_AGENT="EngineeringStudents Scraper v1.0 by /u/your_username"
```

**Option B: Interactive Input**
The script will prompt for credentials if environment variables are not set.

## Usage

### Basic Usage

```bash
# Run the complete pipeline (scraping + cleaning)
python main.py

# Scrape 500 posts with batches of 50
python main.py --limit 500 --batch-size 50
```

### Advanced Options

```bash
# Only run the cleaning phase (skip scraping)
python main.py --clean-only

# Only run the scraping phase (skip cleaning)
python main.py --scrape-only

# Skip scraping and only clean existing raw files
python main.py --skip-scraping

# Scrape more posts
python main.py --limit 2000 --batch-size 100
```

### Command Line Arguments

- `--limit N`: Maximum number of posts to scrape (default: 1000)
- `--batch-size N`: Number of posts per batch (default: 100)
- `--skip-scraping`: Skip scraping phase, only run cleaning
- `--clean-only`: Only run the cleaning phase
- `--scrape-only`: Only run the scraping phase

## Output

### Raw Data (`data/raw/`)
- JSON files containing original post data
- Batch files: `posts_batch_0001.json`, `posts_batch_0002.json`, etc.
- Progress tracking: `scraping_progress.json`

### Clean Data (`data/clean/`)
- Human-readable text files: `cleaned_posts_0001.txt`, `cleaned_posts_0002.txt`, etc.
- Each file ≤ 400MB (automatically split when limit reached)
- Processed files tracking: `processed_files.txt`

### Sample Output Format

```
================================================================================
POST ID: abc123
AUTHOR: username
DATE: 2024-01-15T10:30:00
UPVOTES: 25
COMMENTS: 8
--------------------------------------------------------------------------------
TITLE: How to prepare for technical interviews?

CONTENT:
I'm a computer science student in my junior year and I'm starting to apply for internships. What are the best resources for preparing for technical interviews? I've heard about LeetCode but are there other good platforms?

================================================================================
```

## Data Fields

Each scraped post includes:
- **ID**: Reddit post ID
- **Title**: Post title
- **Text**: Post content/body
- **Author**: Username (or [deleted])
- **Date**: Creation timestamp
- **Upvotes**: Score/upvotes
- **Comments**: Number of comments
- **URL**: Original post URL
- **Metadata**: Additional Reddit metadata

## Rate Limiting & Compliance

- **Rate Limiting**: 100ms delay between requests (10 requests/second)
- **Respectful Scraping**: Follows Reddit's API guidelines
- **No Paid APIs**: Uses only free Reddit API access
- **Progress Saving**: Can resume interrupted scraping sessions

## Logging

The scraper creates detailed logs:
- `scraper.log`: Scraping operations
- `cleaner.log`: Text cleaning operations  
- `pipeline.log`: Overall pipeline execution

## Error Handling

- Graceful handling of deleted/removed posts
- Network error recovery
- Progress preservation on interruption
- Comprehensive error logging

## Development

### Running Individual Components

```bash
# Test scraper only
python scraper.py

# Test cleaner only  
python cleaner.py
```

### Customization

- Modify `scraper.py` to change scraping parameters
- Adjust `cleaner.py` for different text cleaning rules
- Update `main.py` for pipeline modifications

## Troubleshooting

### Common Issues

1. **"Please set your Reddit app credentials"**
   - Ensure you've created a Reddit app and set the credentials
   - Check environment variables or enter them interactively

2. **Rate limit errors**
   - The scraper includes built-in rate limiting
   - If you still get errors, increase the delay in `scraper.py`

3. **Permission errors**
   - Ensure the script has write permissions for the `data/` directory
   - Check that the directories exist

4. **Empty output files**
   - Verify that posts are being scraped (check `data/raw/` for JSON files)
   - Check logs for any error messages

### Getting Help

- Check the log files for detailed error information
- Verify your Reddit app credentials are correct
- Ensure you have a stable internet connection
- Make sure you're not hitting Reddit's rate limits

## License

This project is for educational purposes. Please respect Reddit's terms of service and use responsibly.

## Contributing

Feel free to submit issues and enhancement requests!
