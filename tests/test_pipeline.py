"""Tests for configuration loading and the command line pipeline."""

import json
import os

import pytest

import config
import main as pipeline_main
from cleaner import TextCleaner
from conftest import FakeReddit, FakeSubmission, FakeSubreddit
from main import Pipeline


def test_load_dotenv_does_not_override_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'REDDIT_CLIENT_ID="from_file"\nSOME_OTHER=plain\n# comment\n\n', encoding="utf-8"
    )
    monkeypatch.setenv("REDDIT_CLIENT_ID", "from_shell")
    monkeypatch.delenv("SOME_OTHER", raising=False)

    config.load_dotenv(str(env_file))

    assert os.environ["REDDIT_CLIENT_ID"] == "from_shell"
    assert os.environ["SOME_OTHER"] == "plain"


def test_load_dotenv_ignores_missing_file(tmp_path):
    config.load_dotenv(str(tmp_path / "absent.env"))  # must not raise


def test_config_holds_no_hardcoded_credentials(monkeypatch):
    source = open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.py"),
        encoding="utf-8",
    ).read()

    assert 'REDDIT_CLIENT_ID", ""' in source
    assert 'REDDIT_CLIENT_SECRET", ""' in source


def test_int_parsing_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("SOME_INT", "not-a-number")
    assert config._get_int("SOME_INT", 7) == 7
    monkeypatch.setenv("SOME_INT", "12")
    assert config._get_int("SOME_INT", 7) == 12
    monkeypatch.delenv("SOME_INT")
    assert config._get_int("SOME_INT", 7) == 7


def test_cleaning_needs_no_credentials(raw_dir, clean_dir, monkeypatch):
    monkeypatch.setattr(config, "RAW_DATA_DIR", str(raw_dir))
    monkeypatch.setattr(config, "CLEAN_DATA_DIR", str(clean_dir))

    pipeline = Pipeline()  # no client id, no secret
    pipeline.run_cleaning()

    assert (clean_dir / "cleaned_posts_0001.txt").exists()


def test_scraping_without_credentials_raises():
    with pytest.raises(ValueError):
        Pipeline().run_scraping(limit=1)


def test_clean_only_exits_zero_without_credentials(raw_dir, clean_dir, monkeypatch, capsys):
    monkeypatch.setattr(config, "RAW_DATA_DIR", str(raw_dir))
    monkeypatch.setattr(config, "CLEAN_DATA_DIR", str(clean_dir))
    monkeypatch.setattr(config, "REDDIT_CLIENT_ID", "")
    monkeypatch.setattr(config, "REDDIT_CLIENT_SECRET", "")

    exit_code = pipeline_main.main(["--clean-only"])

    assert exit_code == 0
    assert "PIPELINE SUMMARY" in capsys.readouterr().out


def test_scrape_without_credentials_exits_one(monkeypatch, capsys):
    monkeypatch.setattr(config, "REDDIT_CLIENT_ID", "")
    monkeypatch.setattr(config, "REDDIT_CLIENT_SECRET", "")
    monkeypatch.setattr(config, "credentials", lambda: ("", "", "agent"))

    exit_code = pipeline_main.main(["--scrape-only", "--non-interactive"])

    assert exit_code == 1
    assert "credentials are required" in capsys.readouterr().out


def test_bad_batch_size_exits_two(capsys):
    assert pipeline_main.main(["--batch-size", "0", "--clean-only"]) == 2


def test_full_pipeline_scrapes_then_cleans(tmp_path, monkeypatch, capsys):
    raw_dir = tmp_path / "raw"
    clean_dir = tmp_path / "clean"
    monkeypatch.setattr(config, "RAW_DATA_DIR", str(raw_dir))
    monkeypatch.setattr(config, "CLEAN_DATA_DIR", str(clean_dir))
    monkeypatch.setattr(config, "RATE_LIMIT_DELAY", 0)

    subreddit = FakeSubreddit([FakeSubmission("p{}".format(i)) for i in range(3)])
    pipeline = Pipeline("id", "secret", "agent")
    pipeline.scraper = __import__("scraper").RedditScraper(
        "", "", "", data_dir=str(raw_dir), rate_limit_delay=0, reddit=FakeReddit(subreddit)
    )
    pipeline.cleaner = TextCleaner(raw_dir=str(raw_dir), clean_dir=str(clean_dir))

    pipeline.run_full_pipeline(limit=3, batch_size=2)

    output = "".join(
        path.read_text(encoding="utf-8") for path in clean_dir.glob("cleaned_posts_*.txt")
    )
    for index in range(3):
        assert "POST ID: p{}\n".format(index) in output

    summary = capsys.readouterr().out
    assert "Total posts scraped:  3" in summary


def test_scraper_stats_reads_progress_file(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "scraping_progress.json").write_text(
        json.dumps({"total_posts": 12, "last_run": "2026-07-31T00:00:00"}), encoding="utf-8"
    )
    monkeypatch.setattr(config, "RAW_DATA_DIR", str(raw_dir))

    stats = Pipeline().scraper_stats()

    assert stats["total_posts"] == 12


def test_scraper_stats_tolerates_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DATA_DIR", str(tmp_path / "absent"))

    assert Pipeline().scraper_stats() == {}
