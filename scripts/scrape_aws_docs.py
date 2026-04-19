#!/usr/bin/env python3
"""AWS Documentation scraper for KB seeding.

Reads a seeds file of AWS topics, uses the AWS Docs search to discover
relevant documentation URLs, optionally fetches and previews page titles,
then outputs a URL list that can be piped into scripts/ingest.py.

Usage:
    uv run python scripts/scrape_aws_docs.py \
        --seeds data/kb_seeds.txt \
        --output data/urls.txt \
        --per-seed 3

Then ingest:
    uv run python scripts/ingest.py data/urls.txt
"""
from __future__ import annotations

import argparse
import html
import logging
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _search_docs(query: str, top_k: int = 3) -> list[str]:
    """Return up to top_k AWS docs URLs for a search query."""
    urls: list[str] = []

    # 1. Try autocomplete API (JSON, fast)
    try:
        encoded = quote_plus(query)
        url = f"https://docs.aws.amazon.com/autocomplete?q={encoded}&locale=en_US&limit={top_k * 2}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AWSMeetingAssistantKBScraper/1.0", "Accept": "application/json"},
        )
        import json
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        for item in data.get("suggestions", [])[:top_k]:
            path = item.get("url", "") or item.get("path", "")
            if path:
                full = path if path.startswith("http") else f"https://docs.aws.amazon.com{path}"
                if full not in urls:
                    urls.append(full)
    except Exception as e:
        logger.debug(f"Autocomplete failed for {query!r}: {e}")

    # 2. Fallback: HTML scrape of search page
    if len(urls) < top_k:
        try:
            encoded = quote_plus(query)
            search_url = (
                f"https://docs.aws.amazon.com/search/doc-search.html"
                f"?searchPath=documentation&searchQuery={encoded}&this_doc_guide=*"
            )
            req = urllib.request.Request(
                search_url,
                headers={"User-Agent": "AWSMeetingAssistantKBScraper/1.0", "Accept": "text/html"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            pattern = re.compile(
                r'<a[^>]+href="(https://docs\.aws\.amazon\.com/[^"#]+)"',
                re.DOTALL,
            )
            for m in pattern.finditer(body):
                u = html.unescape(m.group(1))
                if u not in urls:
                    urls.append(u)
                if len(urls) >= top_k:
                    break
        except Exception as e:
            logger.debug(f"HTML scrape failed for {query!r}: {e}")

    return urls[:top_k]


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape AWS docs URLs from seed topics")
    parser.add_argument("--seeds", default="data/kb_seeds.txt", help="Seeds file path")
    parser.add_argument("--output", default="data/urls.txt", help="Output URL list path")
    parser.add_argument("--per-seed", type=int, default=3, help="URLs per seed topic")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests (s)")
    args = parser.parse_args()

    seeds_path = Path(args.seeds)
    if not seeds_path.exists():
        logger.error(f"Seeds file not found: {seeds_path}")
        sys.exit(1)

    topics = [
        line.strip()
        for line in seeds_path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    logger.info(f"Loaded {len(topics)} seed topics from {seeds_path}")

    all_urls: list[str] = []
    seen: set[str] = set()

    for i, topic in enumerate(topics, 1):
        logger.info(f"[{i}/{len(topics)}] Searching: {topic!r}")
        urls = _search_docs(topic, args.per_seed)
        new = [u for u in urls if u not in seen]
        seen.update(new)
        all_urls.extend(new)
        logger.info(f"  → found {len(urls)} URLs, {len(new)} new (total: {len(all_urls)})")
        if i < len(topics):
            time.sleep(args.delay)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(all_urls) + "\n")
    logger.info(f"\nWrote {len(all_urls)} URLs to {output_path}")
    logger.info(f"Next step: uv run python scripts/ingest.py {output_path}")


if __name__ == "__main__":
    main()
