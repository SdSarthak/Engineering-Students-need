# Reddit Engineering Students Scraper

A small, dependency-light pipeline that collects posts and full comment threads
from r/EngineeringStudents through Reddit's free API and turns them into clean,
human-readable text files.

The pipeline has two independent phases:

| Phase | Module | Needs credentials | Output |
| --- | --- | --- | --- |
| Scrape | `scraper.py` | yes | `data/raw/posts_batch_NNNN.json` |
| Clean | `cleaner.py` | no | `data/clean/cleaned_posts_NNNN.txt` |

`main.py` orchestrates both. Because cleaning is offline, you can re-run it over
already-scraped batches without touching the Reddit API at all.

## Features

- **Respectful scraping** - PRAW plus a configurable delay between submissions.
- **Real pagination** - walks `hot`, `new` and `top` across every time filter,
  deduplicating by post ID, so a run terminates instead of re-reading the same
  page forever.
- **Full comment trees** - each comment stores its direct replies nested inside
  it, so a comment appears exactly once no matter how deep the thread goes.
- **Resumable** - `data/raw/scraping_progress.json` records every post ID that
  has been saved; an interrupted run picks up where it stopped.
- **Bounded output** - cleaned text rotates to a new file once a byte or word
  budget is reached.
- **Credentials via environment** - nothing secret lives in the repository.

## Project structure

```
config.py            # environment-driven settings and .env loading
scraper.py           # PRAW scraping and raw JSON batches
cleaner.py           # text cleaning, formatting, output rotation
main.py              # CLI pipeline
logging_setup.py     # shared logging configuration
tests/               # pytest suite (synthetic fixtures, no network)
data/raw/            # scraped JSON        (git-ignored)
data/clean/          # cleaned text        (git-ignored)
logs/                # run logs            (git-ignored)
```

`data/` and `logs/` are ignored on purpose - scraped Reddit content is not
redistributed through this repository.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
# for the test suite as well
pip install -r requirements-dev.txt
```

### 2. Get Reddit API credentials

1. Go to <https://www.reddit.com/prefs/apps>.
2. Click **Create App** (or **Create Another App**).
3. Choose **script** as the app type. Any redirect URI works, e.g.
   `http://localhost:8080`.
4. The string under the app name is your **client ID**; the **secret** is shown
   next to it.

Reddit's free API is enough for this pipeline - no paid tier is required.

### 3. Provide the credentials

```bash
cp .env.example .env
# then edit .env
```

`config.py` reads `.env` at import time and never overrides variables that are
already exported, so this also works:

```bash
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"
export REDDIT_USERNAME="your_reddit_username"
```

If neither is set and you run interactively, `main.py` prompts for the values.
Pass `--non-interactive` to fail fast instead (useful in cron or CI).

## Usage

```bash
# scrape 500 posts, then clean everything not yet cleaned
python main.py

# scrape more, in larger batches
python main.py --limit 2000 --batch-size 100

# walk every listing to exhaustion
python main.py --limit 0

# clean the raw files already on disk, no credentials needed
python main.py --clean-only

# scrape only, leave cleaning for later
python main.py --scrape-only --limit 200

# a different subreddit
python main.py --subreddit AskEngineers --limit 100
```

### Command line arguments

| Flag | Default | Meaning |
| --- | --- | --- |
| `--limit N` | `500` | Maximum posts to scrape this run, `0` for unlimited |
| `--batch-size N` | `50` | Posts per raw JSON batch file |
| `--subreddit NAME` | `EngineeringStudents` | Subreddit to scrape |
| `--skip-scraping` | off | Skip scraping, run cleaning only |
| `--clean-only` | off | Same as above, and skips the credential check |
| `--scrape-only` | off | Skip cleaning |
| `--non-interactive` | off | Never prompt for missing credentials |

The modules also run standalone: `python scraper.py` scrapes with the defaults
from the environment, `python cleaner.py` cleans whatever is in `data/raw`.

## Configuration

Every setting in `config.py` can be overridden by an environment variable, all
of them listed in `.env.example`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | empty | API credentials |
| `REDDIT_USER_AGENT` | built from `REDDIT_USERNAME` | Sent with each request |
| `TARGET_SUBREDDIT` | `EngineeringStudents` | Subreddit to scrape |
| `DEFAULT_LIMIT` | `500` | Default `--limit` |
| `DEFAULT_BATCH_SIZE` | `50` | Default `--batch-size` |
| `RATE_LIMIT_DELAY` | `0.2` | Seconds between submissions |
| `MAX_COMMENT_DEPTH` | `10` | Deepest reply level followed |
| `RAW_DATA_DIR` / `CLEAN_DATA_DIR` | `data/raw`, `data/clean` | Output roots |
| `LOG_DIR` | `logs` | Where log files are written |
| `MAX_OUTPUT_FILE_SIZE` | `209715200` (200 MB) | Byte budget per text file |
| `MAX_OUTPUT_WORDS` | `500000` | Word budget per text file |

## Output

### Raw data (`data/raw/`)

`posts_batch_NNNN.json` holds a list of post objects:

```json
{
  "id": "abc123",
  "title": "How to prepare for technical interviews?",
  "text": "I'm a junior and starting to apply for internships...",
  "author": "username",
  "created_utc": 1700000000.0,
  "created_date": "2023-11-14T22:13:20",
  "upvotes": 25,
  "num_comments": 8,
  "url": "https://reddit.com/...",
  "permalink": "https://reddit.com/r/EngineeringStudents/comments/abc123/",
  "is_self": true,
  "over_18": false,
  "stickied": false,
  "subreddit": "EngineeringStudents",
  "scraped_at": "2026-07-31T01:00:00",
  "comments": [
    {
      "id": "def456",
      "author": "commenter",
      "body": "LeetCode plus mock interviews.",
      "upvotes": 12,
      "depth": 0,
      "is_submitter": false,
      "replies": []
    }
  ]
}
```

`scraping_progress.json` records `seen_ids`, `total_posts` and `last_run`.

### Clean data (`data/clean/`)

```
====================================================================================================
POST ID: abc123
AUTHOR: username
DATE: 2023-11-14T22:13:20
UPVOTES: 25
TOTAL COMMENTS: 8
SCRAPED COMMENTS: 3
----------------------------------------------------------------------------------------------------
TITLE: How to prepare for technical interviews?

POST CONTENT:
I'm a junior and starting to apply for internships. What are the best resources?

COMMENTS:
====================================================================================================
+- COMMENT ID: def456
|  AUTHOR: commenter
|  DATE: 2023-11-14T23:01:00
|  UPVOTES: 12
+-
  LeetCode plus mock interviews.

  +- COMMENT ID: ghi789
  |  AUTHOR: username (OP)
  |  DATE: 2023-11-15T00:02:00
  |  UPVOTES: 3
  +-
    Thanks, that helps.
====================================================================================================
```

Cleaning strips HTML, markdown links, bare URLs, `/u/` and `/r/` mentions,
emphasis markers, quote and list markers, and collapses repeated punctuation.
`processed_files.txt` records which raw batches have been folded in, so
re-running the cleaner never duplicates text.

## Tests

```bash
python -m pytest
```

The suite is deterministic and fully offline: PRAW is replaced with small fake
submission and comment objects, and every file operation happens in a pytest
`tmp_path`. No credentials, network or database are required.

## Rate limiting and compliance

- One submission every `RATE_LIMIT_DELAY` seconds (0.2 s by default), on top of
  PRAW's own rate limiting.
- Only the free, documented Reddit API is used.
- Scraped content stays local; `data/` is git-ignored.
- Respect [Reddit's API terms](https://www.redditinc.com/policies/data-api-terms)
  and the subreddit's rules when using anything you collect.

## Troubleshooting

**"Reddit credentials are required to scrape"**
`REDDIT_CLIENT_ID` or `REDDIT_CLIENT_SECRET` is unset. Copy `.env.example` to
`.env` and fill it in. Cleaning still works: `python main.py --clean-only`.

**`received 401 HTTP response`**
The client id and secret do not match, or the app is not of type *script*.
Recreate the app at <https://www.reddit.com/prefs/apps>.

**The scraper finishes with fewer posts than `--limit`**
Reddit caps each listing at roughly 1000 items. The scraper already walks
several sorts and time filters and deduplicates between them, so the ceiling is
Reddit's, not the scraper's. Re-running later picks up newly posted threads.

**"All raw files have already been processed"**
Every batch is recorded in `data/clean/processed_files.txt`. Delete the line for
a batch (or the whole file) to reprocess it.

**Empty output files**
Check `logs/scraper.log` and confirm `data/raw/` actually contains batches.

## License

Educational project. Respect Reddit's terms of service and use responsibly.
