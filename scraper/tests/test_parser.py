"""Tests for the HN scraper parser logic.

All tests run against a saved HTML fixture (tests/fixture.html) — no network calls.
"""

import json
import os
from pathlib import Path

import pytest

# Allow imports from the parent directory
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import (
    parse_stories,
    format_json,
    format_csv,
    format_markdown,
    _extract_points,
    _extract_title_url,
    _find_submission_rows,
)
from bs4 import BeautifulSoup

FIXTURE_PATH = Path(__file__).parent / "fixture.html"


@pytest.fixture
def html():
    return FIXTURE_PATH.read_text(encoding="utf-8")


@pytest.fixture
def stories(html):
    return parse_stories(html, limit=30)


# ---------- Core parsing ----------

class TestParseStories:
    def test_returns_list(self, stories):
        assert isinstance(stories, list)

    def test_returns_up_to_30_stories(self, stories):
        assert len(stories) == 30

    def test_limit_works(self, html):
        limited = parse_stories(html, limit=5)
        assert len(limited) == 5

    def test_limit_zero_returns_empty(self, html):
        assert parse_stories(html, limit=0) == []

    def test_each_story_has_required_keys(self, stories):
        for s in stories:
            assert "title" in s
            assert "url" in s
            assert "points" in s

    def test_titles_are_nonempty_strings(self, stories):
        for s in stories:
            assert isinstance(s["title"], str)
            assert len(s["title"]) > 0

    def test_urls_are_strings(self, stories):
        for s in stories:
            assert isinstance(s["url"], str)
            assert s["url"].startswith("http")

    def test_points_are_nonnegative_ints(self, stories):
        for s in stories:
            assert isinstance(s["points"], int)
            assert s["points"] >= 0

    def test_first_story_has_points(self, stories):
        """The top story on HN almost always has >0 points."""
        assert stories[0]["points"] > 0

    def test_stories_are_unique(self, stories):
        titles = [s["title"] for s in stories]
        assert len(titles) == len(set(titles))


# ---------- Edge cases ----------

class TestEdgeCases:
    def test_empty_html_returns_empty(self):
        assert parse_stories("", limit=30) == []

    def test_no_stories_html(self):
        assert parse_stories("<html><body><p>Nothing</p></body></html>") == []

    def test_malformed_html_does_not_crash(self):
        bad_html = "<table><tr class='athing' id='123'><td><a href='http://x.com'>Title</a></td></tr></table>"
        result = parse_stories(bad_html, limit=5)
        # Should either parse something or return empty, but never crash
        assert isinstance(result, list)


# ---------- Submission row finder ----------

class TestFindSubmissionRows:
    def test_finds_rows(self, html):
        soup = BeautifulSoup(html, "html.parser")
        rows = _find_submission_rows(soup)
        assert len(rows) >= 30

    def test_fallback_strategy(self):
        """When 'athing' class is absent, the fallback uses numeric IDs."""
        fake_html = """
        <table>
          <tr id="12345"><td><span>1.</span></td><td><a href="http://example.com">Test</a></td></tr>
          <tr><td>subtext</td></tr>
        </table>
        """
        soup = BeautifulSoup(fake_html, "html.parser")
        rows = _find_submission_rows(soup)
        assert len(rows) >= 1


# ---------- Title + URL extraction ----------

class TestExtractTitleUrl:
    def test_external_link(self):
        html = '<tr><td><span><a href="https://example.com/article">Cool Article</a></span></td></tr>'
        row = BeautifulSoup(html, "html.parser").find("tr")
        title, url = _extract_title_url(row)
        assert title == "Cool Article"
        assert url == "https://example.com/article"

    def test_self_post_link(self):
        html = '<tr><td><span><a href="item?id=12345">Ask HN: Something</a></span></td></tr>'
        row = BeautifulSoup(html, "html.parser").find("tr")
        title, url = _extract_title_url(row)
        assert title == "Ask HN: Something"
        assert "item?id=12345" in url
        assert url.startswith("http")

    def test_skip_vote_links(self):
        html = '<tr><td><a href="vote?id=123&how=up">x</a><a href="http://real.com">Real Title</a></td></tr>'
        row = BeautifulSoup(html, "html.parser").find("tr")
        title, url = _extract_title_url(row)
        assert title == "Real Title"


# ---------- Points extraction ----------

class TestExtractPoints:
    def test_extracts_from_score_span(self):
        html = """
        <table>
          <tr class="athing" id="111"><td>story</td></tr>
          <tr><td><span id="score_111">42 points</span></td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr", class_="athing")
        assert _extract_points(row) == 42

    def test_extracts_from_text_fallback(self):
        html = """
        <table>
          <tr class="athing" id="222"><td>story</td></tr>
          <tr><td>99 points by someone</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr", class_="athing")
        assert _extract_points(row) == 99

    def test_zero_when_no_sibling(self):
        html = '<table><tr class="athing" id="333"><td>story</td></tr></table>'
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr", class_="athing")
        assert _extract_points(row) == 0

    def test_single_point(self):
        html = """
        <table>
          <tr class="athing" id="444"><td>story</td></tr>
          <tr><td><span id="score_444">1 point</span></td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr", class_="athing")
        assert _extract_points(row) == 1


# ---------- Output formatters ----------

class TestFormatJson:
    def test_valid_json(self, stories):
        output = format_json(stories)
        parsed = json.loads(output)
        assert "stories" in parsed
        assert "scraped_at" in parsed
        assert "count" in parsed

    def test_scraped_at_is_iso8601(self, stories):
        output = format_json(stories)
        parsed = json.loads(output)
        ts = parsed["scraped_at"]
        # Should end with +00:00 or Z
        assert "T" in ts
        # Should be parseable
        from datetime import datetime
        datetime.fromisoformat(ts)

    def test_count_matches_stories(self, stories):
        output = format_json(stories)
        parsed = json.loads(output)
        assert parsed["count"] == len(parsed["stories"])


class TestFormatCsv:
    def test_has_header(self, stories):
        output = format_csv(stories)
        lines = output.strip().split("\n")
        assert lines[0].strip() == "title,url,points"

    def test_correct_line_count(self, stories):
        output = format_csv(stories)
        lines = output.strip().split("\n")
        assert len(lines) == len(stories) + 1  # header + data


class TestFormatMarkdown:
    def test_has_header_row(self, stories):
        output = format_markdown(stories)
        lines = output.split("\n")
        assert "Title" in lines[0]
        assert "---" in lines[1]

    def test_correct_line_count(self, stories):
        output = format_markdown(stories)
        lines = output.split("\n")
        assert len(lines) == len(stories) + 2  # header + separator + data
