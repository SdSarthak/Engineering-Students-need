"""Tests for text cleaning, formatting and output rotation."""

import json

from cleaner import TextCleaner


def build_cleaner(raw_dir, clean_dir, **kwargs):
    """Build a cleaner pointed at temporary directories."""
    return TextCleaner(raw_dir=str(raw_dir), clean_dir=str(clean_dir), **kwargs)


def test_clean_text_strips_markup(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)

    cleaned = cleaner.clean_text(
        "<b>Hello</b> &amp; welcome to [the guide](https://example.com) "
        "from /u/someone in /r/EngineeringStudents"
    )

    assert "<b>" not in cleaned
    assert "&amp;" not in cleaned
    assert "https://" not in cleaned
    assert "the guide" in cleaned
    assert "someone" not in cleaned
    assert "EngineeringStudents" not in cleaned


def test_clean_text_keeps_words_containing_slash_r(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)

    # Bare "r/x" inside a larger token must not be eaten.
    assert cleaner.clean_text("hour/rate math") == "hour/rate math"


def test_clean_text_collapses_formatting_and_punctuation(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)

    cleaned = cleaner.clean_text("**bold** *italic* `code` ~~gone~~ what????  wow!!!!")

    assert cleaned == "bold italic code gone what? wow!"


def test_clean_text_strips_list_and_quote_markers(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)

    cleaned = cleaner.clean_text("> quoted line\n- first item\n+ second item")

    assert cleaned.splitlines() == ["quoted line", "first item", "second item"]


def test_clean_text_keeps_negative_numbers(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)

    assert cleaner.clean_text("-40 degrees is cold") == "-40 degrees is cold"


def test_clean_text_handles_empty_input(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)

    assert cleaner.clean_text("") == ""
    assert cleaner.clean_text("   \n  ") == ""


def test_format_post_renders_nested_comments(raw_dir, clean_dir, raw_post):
    cleaner = build_cleaner(raw_dir, clean_dir)

    output = cleaner.format_post_for_output(raw_post)

    assert "POST ID: p1" in output
    assert "TITLE: How do I study for thermo?" in output
    assert "SCRAPED COMMENTS: 2" in output, "nested replies count towards the total"
    assert "COMMENT ID: t1" in output
    assert "COMMENT ID: c1" in output
    assert "(OP)" in output
    # The reply is indented one level deeper than its parent.
    assert "\n  +- COMMENT ID: c1" in output


def test_format_post_keeps_deleted_comment_with_replies(raw_dir, clean_dir):
    post = {
        "id": "p2",
        "title": "title",
        "text": "",
        "comments": [
            {
                "id": "t1",
                "body": "",
                "author": "[deleted]",
                "replies": [{"id": "c1", "body": "still here", "author": "someone", "replies": []}],
            }
        ],
    }
    cleaner = build_cleaner(raw_dir, clean_dir)

    output = cleaner.format_post_for_output(post)

    assert "COMMENT ID: t1" in output
    assert "still here" in output


def test_format_post_drops_fully_empty_posts(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)

    assert cleaner.format_post_for_output({"id": "x", "title": "", "text": "", "comments": []}) == ""


def test_process_posts_writes_output_and_marks_processed(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)

    summary = cleaner.process_posts()

    assert summary["posts_written"] == 1
    assert summary["files_processed"] == 1

    output = (clean_dir / "cleaned_posts_0001.txt").read_text(encoding="utf-8")
    assert "POST ID: p1" in output
    assert "posts_batch_0001.json" in (clean_dir / "processed_files.txt").read_text(
        encoding="utf-8"
    )


def test_process_posts_is_idempotent(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)

    cleaner.process_posts()
    first = (clean_dir / "cleaned_posts_0001.txt").read_text(encoding="utf-8")
    second_summary = cleaner.process_posts()

    assert second_summary["posts_written"] == 0
    assert (clean_dir / "cleaned_posts_0001.txt").read_text(encoding="utf-8") == first


def test_rotation_writes_every_post(raw_dir, clean_dir, raw_post):
    # Ten posts with a byte budget that only fits one or two per file.
    posts = []
    for index in range(10):
        post = dict(raw_post)
        post["id"] = "p{}".format(index)
        posts.append(post)
    (raw_dir / "posts_batch_0001.json").write_text(json.dumps(posts), encoding="utf-8")

    cleaner = build_cleaner(raw_dir, clean_dir, max_file_size=1500)
    summary = cleaner.process_posts()

    assert summary["posts_written"] == 10

    combined = ""
    for path in sorted(clean_dir.glob("cleaned_posts_*.txt")):
        combined += path.read_text(encoding="utf-8")

    assert len(list(clean_dir.glob("cleaned_posts_*.txt"))) > 1, "output should have rotated"
    for index in range(10):
        assert "POST ID: p{}\n".format(index) in combined, "post p{} was lost".format(index)


def test_rotation_on_word_budget(raw_dir, clean_dir, raw_post):
    posts = []
    for index in range(4):
        post = dict(raw_post)
        post["id"] = "p{}".format(index)
        posts.append(post)
    (raw_dir / "posts_batch_0001.json").write_text(json.dumps(posts), encoding="utf-8")

    cleaner = build_cleaner(raw_dir, clean_dir, max_words=40)
    summary = cleaner.process_posts()

    assert summary["posts_written"] == 4
    assert len(list(clean_dir.glob("cleaned_posts_*.txt"))) > 1


def test_oversized_single_post_still_written(raw_dir, clean_dir, raw_post):
    (raw_dir / "posts_batch_0001.json").write_text(json.dumps([raw_post]), encoding="utf-8")
    cleaner = build_cleaner(raw_dir, clean_dir, max_file_size=10)

    summary = cleaner.process_posts()

    assert summary["posts_written"] == 1
    combined = "".join(
        path.read_text(encoding="utf-8") for path in clean_dir.glob("cleaned_posts_*.txt")
    )
    assert "POST ID: p1" in combined


def test_unreadable_batch_is_skipped(raw_dir, clean_dir):
    (raw_dir / "posts_batch_0002.json").write_text("{not json", encoding="utf-8")
    cleaner = build_cleaner(raw_dir, clean_dir)

    summary = cleaner.process_posts()

    assert summary["posts_written"] == 1
    assert summary["files_processed"] == 2


def test_progress_file_is_not_treated_as_a_batch(raw_dir, clean_dir):
    (raw_dir / "scraping_progress.json").write_text("{}", encoding="utf-8")
    cleaner = build_cleaner(raw_dir, clean_dir)

    assert cleaner.get_json_files() == ["posts_batch_0001.json"]


def test_missing_raw_directory_is_reported(tmp_path, clean_dir):
    cleaner = TextCleaner(raw_dir=str(tmp_path / "nope"), clean_dir=str(clean_dir))

    assert cleaner.get_json_files() == []
    assert cleaner.process_posts()["posts_written"] == 0


def test_cleaning_stats(raw_dir, clean_dir):
    cleaner = build_cleaner(raw_dir, clean_dir)
    cleaner.process_posts()

    stats = cleaner.get_cleaning_stats()

    assert stats["raw_files"] == 1
    assert stats["processed_files"] == 1
    assert stats["output_files"] == 1
    assert stats["total_output_size"] > 0
