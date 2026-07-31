"""Shared fixtures: synthetic Reddit objects and raw JSON batches."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeForest(list):
    """Stands in for a PRAW CommentForest: a list that can `replace_more`."""

    def __init__(self, items=(), raises=False):
        super().__init__(items)
        self.raises = raises
        self.replace_more_calls = 0

    def replace_more(self, limit=None):
        self.replace_more_calls += 1
        if self.raises:
            raise RuntimeError("expansion failed")


class FakeComment:
    """Minimal stand-in for a PRAW Comment."""

    def __init__(
        self,
        comment_id,
        body="a comment",
        author="commenter",
        score=3,
        created_utc=1_700_000_000.0,
        is_submitter=False,
        replies=None,
    ):
        self.id = comment_id
        self.body = body
        self.author = author
        self.score = score
        self.created_utc = created_utc
        self.is_submitter = is_submitter
        self.permalink = "/r/EngineeringStudents/comments/{}/".format(comment_id)
        self.replies = FakeForest(replies or [])


class FakeSubmission:
    """Minimal stand-in for a PRAW Submission."""

    def __init__(
        self,
        submission_id,
        title="a title",
        selftext="post body",
        author="poster",
        score=10,
        num_comments=0,
        created_utc=1_700_000_000.0,
        comments=None,
    ):
        self.id = submission_id
        self.title = title
        self.selftext = selftext
        self.author = author
        self.score = score
        self.num_comments = num_comments
        self.created_utc = created_utc
        self.url = "https://reddit.com/r/EngineeringStudents/comments/{}/".format(submission_id)
        self.permalink = "/r/EngineeringStudents/comments/{}/".format(submission_id)
        self.is_self = True
        self.over_18 = False
        self.stickied = False
        self.subreddit = "EngineeringStudents"
        self.comments = FakeForest(comments or [])


class FakeSubreddit:
    """Serves the same submissions from every listing, like Reddit's sorts do."""

    def __init__(self, submissions):
        self.submissions = list(submissions)
        self.calls = []
        self.display_name = "EngineeringStudents"
        self.title = "Engineering Students"
        self.description = "a subreddit"
        self.subscribers = 123
        self.created_utc = 1_400_000_000.0
        self.public_description = "engineering students"

    def hot(self, limit=None):
        self.calls.append(("hot", limit))
        return iter(self.submissions)

    def new(self, limit=None):
        self.calls.append(("new", limit))
        return iter(self.submissions)

    def top(self, limit=None, time_filter="all"):
        self.calls.append(("top:{}".format(time_filter), limit))
        return iter(self.submissions)


class FakeReddit:
    """Minimal stand-in for a PRAW Reddit client."""

    def __init__(self, subreddit):
        self._subreddit = subreddit

    def subreddit(self, name):
        return self._subreddit


@pytest.fixture
def fake_submission():
    """A submission with a two-level comment tree."""
    grandchild = FakeComment("gc1", body="deepest reply")
    child = FakeComment("c1", body="a reply", replies=[grandchild])
    top = FakeComment("t1", body="top level", is_submitter=True, replies=[child])
    return FakeSubmission("p1", num_comments=3, comments=[top])


@pytest.fixture
def raw_post():
    """A raw post dictionary in the shape the scraper writes."""
    return {
        "id": "p1",
        "title": "How do I study for **thermo**?",
        "text": "See [this guide](https://example.com/guide) and ask /u/someone.",
        "author": "poster",
        "created_date": "2023-11-14T22:13:20",
        "upvotes": 42,
        "num_comments": 2,
        "comments": [
            {
                "id": "t1",
                "author": "helper",
                "body": "Try the textbook!!!",
                "created_date": "2023-11-14T23:00:00",
                "upvotes": 7,
                "is_submitter": False,
                "replies": [
                    {
                        "id": "c1",
                        "author": "poster",
                        "body": "Thanks???",
                        "created_date": "2023-11-15T00:00:00",
                        "upvotes": 2,
                        "is_submitter": True,
                        "replies": [],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def raw_dir(tmp_path, raw_post):
    """A raw directory holding one synthetic batch file."""
    directory = tmp_path / "raw"
    directory.mkdir()
    batch = directory / "posts_batch_0001.json"
    batch.write_text(json.dumps([raw_post]), encoding="utf-8")
    return directory


@pytest.fixture
def clean_dir(tmp_path):
    """An empty output directory."""
    directory = tmp_path / "clean"
    directory.mkdir()
    return directory
