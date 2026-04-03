#!/usr/bin/env python3
"""Hacker News front page scraper.

Extracts story titles, URLs, and point counts from https://news.ycombinator.com.
Outputs JSON (default), CSV, or Markdown table.

Usage:
    python scraper.py [--format json|csv|markdown] [--limit N]
"""

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

HN_URL = "https://news.ycombinator.com"
REQUEST_TIMEOUT = 15  # seconds


def fetch_html(url: str = HN_URL, timeout: int = REQUEST_TIMEOUT) -> str:
    """Fetch raw HTML from the given URL."""
    response = requests.get(url, timeout=timeout, headers={
        "User-Agent": "HN-Scraper/1.0 (educational project)"
    })
    response.raise_for_status()
    return response.text


def parse_stories(html: str, limit: int = 30) -> list[dict]:
    """Parse story data from HN HTML.

    Strategy (resilient to class name changes):
    1. Find submission rows via <tr> tags that carry an integer `id` attribute
       and contain a numbered rank indicator (e.g. "1.").
    2. Extract the story link — the first <a> whose href starts with "http"
       (or a relative "item?id=" for self-posts).
    3. Walk to the next sibling <tr> for the subtext row, then pull the
       score from the first element whose text matches "N points".
    """
    soup = BeautifulSoup(html, "html.parser")
    stories: list[dict] = []

    # --- Primary selector: rows with class containing "athing" ---
    submission_rows = _find_submission_rows(soup)

    for row in submission_rows:
        if len(stories) >= limit:
            break

        story = _extract_story(row)
        if story:
            stories.append(story)

    return stories


def _find_submission_rows(soup: BeautifulSoup) -> list:
    """Locate the <tr> elements that represent individual stories.

    Uses multiple strategies so a class-name change doesn't break us:
    1. <tr class="athing"> (current HN markup)
    2. Fallback: any <tr> with a numeric `id` that contains a rank number
    """
    # Strategy 1: class-based (fast path)
    rows = soup.find_all("tr", class_="athing")
    if rows:
        return rows

    # Strategy 2: heuristic — rows whose first <td> contains a rank like "1."
    candidates = []
    for tr in soup.find_all("tr"):
        tr_id = tr.get("id", "")
        if tr_id.isdigit():
            # Likely a submission row
            candidates.append(tr)
    return candidates


def _extract_story(row) -> dict | None:
    """Pull title, URL, and points from a submission row + its sibling."""
    # --- Title & URL ---
    title, url = _extract_title_url(row)
    if not title:
        return None

    # --- Points (from the next sibling row) ---
    points = _extract_points(row)

    return {
        "title": title,
        "url": url,
        "points": points,
    }


def _extract_title_url(row) -> tuple[str, str]:
    """Get the story title and URL from a submission row.

    Strategies (in order):
    1. Find a <span> wrapping the title link (current: class="titleline").
    2. Fallback: first <a> whose href is external or an item link.
    """
    # Strategy 1: look for a title-wrapping span that contains an <a>
    for span in row.find_all("span"):
        link = span.find("a", href=True)
        if link and _is_story_link(link):
            return link.get_text(strip=True), _normalize_url(link["href"])

    # Strategy 2: brute-force — scan all <a> tags in the row
    for link in row.find_all("a", href=True):
        if _is_story_link(link):
            return link.get_text(strip=True), _normalize_url(link["href"])

    return "", ""


def _is_story_link(tag) -> bool:
    """Determine whether an <a> tag looks like a story link."""
    href = tag.get("href", "")
    text = tag.get_text(strip=True)
    # Skip tiny links (vote arrows, "hide", etc.)
    if len(text) < 2:
        return False
    # Skip vote links
    if href.startswith("vote?"):
        return False
    # Skip user profile links
    if href.startswith("user?"):
        return False
    # Skip "from?" domain links
    if href.startswith("from?"):
        return False
    # Accept external URLs or HN item links (self-posts)
    if href.startswith("http") or href.startswith("item?"):
        return True
    return False


def _normalize_url(href: str) -> str:
    """Turn relative HN URLs into absolute ones."""
    if href.startswith("item?"):
        return f"https://news.ycombinator.com/{href}"
    return href


def _extract_points(row) -> int:
    """Get the point count from the subtext row following the submission row.

    Strategies:
    1. Find sibling row, look for text matching "N points".
    2. Look for a <span> whose id starts with "score_".
    """
    import re

    sibling = row.find_next_sibling("tr")
    if not sibling:
        return 0

    # Strategy 1: span with id starting with "score_"
    score_span = sibling.find("span", id=lambda x: x and x.startswith("score_"))
    if score_span:
        match = re.search(r"(\d+)", score_span.get_text())
        if match:
            return int(match.group(1))

    # Strategy 2: regex across the whole subtext row
    text = sibling.get_text()
    match = re.search(r"(\d+)\s+points?", text)
    if match:
        return int(match.group(1))

    return 0


# ---------- Output formatters ----------

def format_json(stories: list[dict]) -> str:
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "count": len(stories),
        "stories": stories,
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


def format_csv(stories: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["title", "url", "points"])
    writer.writeheader()
    writer.writerows(stories)
    return buf.getvalue()


def format_markdown(stories: list[dict]) -> str:
    lines = [
        f"| # | Title | URL | Points |",
        f"|---|-------|-----|--------|",
    ]
    for i, s in enumerate(stories, 1):
        title = s["title"].replace("|", "\\|")
        lines.append(f"| {i} | {title} | {s['url']} | {s['points']} |")
    return "\n".join(lines)


FORMATTERS = {
    "json": format_json,
    "csv": format_csv,
    "markdown": format_markdown,
}


def main():
    parser = argparse.ArgumentParser(description="Scrape Hacker News front page")
    parser.add_argument(
        "--format",
        choices=FORMATTERS.keys(),
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Number of stories to return (default: 30)",
    )
    args = parser.parse_args()

    try:
        html = fetch_html()
    except requests.exceptions.Timeout:
        print("Error: Request timed out. Try again later.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Hacker News.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Error: HTTP {e.response.status_code}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        stories = parse_stories(html, limit=args.limit)
    except Exception as e:
        print(f"Error parsing HTML: {e}", file=sys.stderr)
        sys.exit(1)

    if not stories:
        print("Warning: No stories found. HN markup may have changed.", file=sys.stderr)

    output = FORMATTERS[args.format](stories)
    print(output)


if __name__ == "__main__":
    main()
