"""Tests for the scraper's extraction, dedup and batching logic."""

import json

import pytest

from conftest import FakeComment, FakeForest, FakeReddit, FakeSubmission, FakeSubreddit
from scraper import RedditScraper


def build_scraper(tmp_path, submissions, **kwargs):
    """Build a scraper wired to a fake Reddit client."""
    subreddit = FakeSubreddit(submissions)
    scraper = RedditScraper(
        "", "", "", data_dir=str(tmp_path / "raw"), rate_limit_delay=0, reddit=FakeReddit(subreddit), **kwargs
    )
    return scraper, subreddit


def test_requires_credentials_without_client():
    with pytest.raises(ValueError):
        RedditScraper("", "", "agent")


def test_extract_post_data_nests_comments_once(tmp_path, fake_submission):
    scraper, _ = build_scraper(tmp_path, [fake_submission])

    post = scraper.extract_post_data(fake_submission)

    assert post["id"] == "p1"
    assert post["created_date"] == "2023-11-14T22:13:20"
    assert post["permalink"].startswith("https://reddit.com/r/")

    # One top-level comment, each descendant appearing exactly once.
    assert len(post["comments"]) == 1
    top = post["comments"][0]
    assert top["id"] == "t1"
    assert top["is_submitter"] is True
    assert [reply["id"] for reply in top["replies"]] == ["c1"]
    assert [reply["id"] for reply in top["replies"][0]["replies"]] == ["gc1"]
    assert top["replies"][0]["replies"][0]["replies"] == []

    ids = _collect_ids(post["comments"])
    assert ids == ["t1", "c1", "gc1"], "each comment must be stored exactly once"


def test_comment_depth_is_capped(tmp_path):
    deep = FakeComment("d3")
    mid = FakeComment("d2", replies=[deep])
    top = FakeComment("d1", replies=[mid])
    submission = FakeSubmission("p1", comments=[top])
    scraper, _ = build_scraper(tmp_path, [submission], max_comment_depth=1)

    post = scraper.extract_post_data(submission)

    assert _collect_ids(post["comments"]) == ["d1", "d2"]


def test_deleted_comment_body_is_blanked(tmp_path):
    submission = FakeSubmission("p1", comments=[FakeComment("t1", body="[removed]", author=None)])
    scraper, _ = build_scraper(tmp_path, [submission])

    post = scraper.extract_post_data(submission)

    assert post["comments"][0]["body"] == ""
    assert post["comments"][0]["author"] == "[deleted]"


def test_reply_expansion_failure_is_survivable(tmp_path):
    comment = FakeComment("t1")
    comment.replies = FakeForest([FakeComment("c1")], raises=True)
    submission = FakeSubmission("p1", comments=[comment])
    scraper, _ = build_scraper(tmp_path, [submission])

    post = scraper.extract_post_data(submission)

    # replace_more blew up, but the already-loaded replies are still returned.
    assert _collect_ids(post["comments"]) == ["t1", "c1"]


def test_scrape_posts_deduplicates_across_listings(tmp_path):
    submissions = [FakeSubmission("p{}".format(i)) for i in range(5)]
    scraper, subreddit = build_scraper(tmp_path, submissions)

    progress = scraper.scrape_posts(limit=0, batch_size=10)

    # Every listing serves the same five posts; each is stored once.
    assert progress["total_posts"] == 5
    assert progress["seen_ids"] == ["p0", "p1", "p2", "p3", "p4"]
    assert len(subreddit.calls) > 1, "more than one listing should be walked"

    batches = sorted((tmp_path / "raw").glob("posts_batch_*.json"))
    assert len(batches) == 1
    stored = json.loads(batches[0].read_text(encoding="utf-8"))
    assert [post["id"] for post in stored] == ["p0", "p1", "p2", "p3", "p4"]


def test_scrape_posts_honours_limit_and_batch_size(tmp_path):
    submissions = [FakeSubmission("p{}".format(i)) for i in range(10)]
    scraper, _ = build_scraper(tmp_path, submissions)

    progress = scraper.scrape_posts(limit=4, batch_size=2)

    assert progress["total_posts"] == 4
    batches = sorted((tmp_path / "raw").glob("posts_batch_*.json"))
    assert [path.name for path in batches] == [
        "posts_batch_0001.json",
        "posts_batch_0002.json",
    ]


def test_scrape_posts_resumes_without_reprocessing(tmp_path):
    submissions = [FakeSubmission("p{}".format(i)) for i in range(4)]
    scraper, _ = build_scraper(tmp_path, submissions)

    scraper.scrape_posts(limit=2, batch_size=2)
    second = scraper.scrape_posts(limit=2, batch_size=2)

    assert second["total_posts"] == 4
    assert second["seen_ids"] == ["p0", "p1", "p2", "p3"]
    names = sorted(path.name for path in (tmp_path / "raw").glob("posts_batch_*.json"))
    assert names == ["posts_batch_0001.json", "posts_batch_0002.json"]


def test_partial_batch_is_flushed(tmp_path):
    submissions = [FakeSubmission("p{}".format(i)) for i in range(3)]
    scraper, _ = build_scraper(tmp_path, submissions)

    scraper.scrape_posts(limit=3, batch_size=2)

    stored = []
    for path in sorted((tmp_path / "raw").glob("posts_batch_*.json")):
        stored.extend(json.loads(path.read_text(encoding="utf-8")))
    assert [post["id"] for post in stored] == ["p0", "p1", "p2"]


def test_legacy_progress_file_is_upgraded(tmp_path):
    scraper, _ = build_scraper(tmp_path, [])
    progress_path = tmp_path / "raw" / "scraping_progress.json"
    progress_path.write_text(
        json.dumps({"last_processed_id": "old1", "total_posts": 7}), encoding="utf-8"
    )

    progress = scraper.load_progress()

    assert progress["seen_ids"] == ["old1"]
    assert progress["total_posts"] == 7


def test_corrupt_progress_file_falls_back(tmp_path):
    scraper, _ = build_scraper(tmp_path, [])
    (tmp_path / "raw" / "scraping_progress.json").write_text("{not json", encoding="utf-8")

    progress = scraper.load_progress()

    assert progress == {"seen_ids": [], "total_posts": 0, "last_run": None}


def test_next_batch_number_skips_existing_files(tmp_path):
    scraper, _ = build_scraper(tmp_path, [])
    (tmp_path / "raw" / "posts_batch_0003.json").write_text("[]", encoding="utf-8")

    assert scraper.next_batch_number() == 4


def test_invalid_batch_size_rejected(tmp_path):
    scraper, _ = build_scraper(tmp_path, [])
    with pytest.raises(ValueError):
        scraper.scrape_posts(limit=1, batch_size=0)


def _collect_ids(comments):
    """Flatten a nested comment tree into a list of IDs."""
    ids = []
    for comment in comments:
        ids.append(comment["id"])
        ids.extend(_collect_ids(comment.get("replies", [])))
    return ids
