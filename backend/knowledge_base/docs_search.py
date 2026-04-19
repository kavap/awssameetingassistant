"""AWS Documentation search client.

Queries the public AWS docs search endpoint to find relevant documentation
pages for a given query. Results are scored at 0.5 (lower than typical
Bedrock KB scores of 0.7-0.9) so KB results rank higher by default.

Used as a second retrieval source alongside the Bedrock Knowledge Base to
ensure coverage of the latest AWS docs without needing to re-ingest.
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from urllib.parse import quote_plus

import urllib.request
import json as _json

logger = logging.getLogger(__name__)

_AWS_DOCS_SEARCH_URL = (
    "https://docs.aws.amazon.com/search/doc-search.html"
    "?searchPath=documentation&searchQuery={query}&this_doc_guide=*"
    "&locale=en_US&searchSuffix=&doc_locale=en_US&x=0&y=0"
)

_AWS_DOCS_API_URL = (
    "https://aws.amazon.com/api/dirs/items/search"
    "?item.locale=en_US&item.directoryId=aws-documentation"
    "&sort_by=item.additionalFields.lastUpdatedDate&sort_order=desc"
    "&size=5&item.directionalFilters=aws-documentation%23category%23"
    "&tags.id=aws-documentation%23category%23documentation"
    "&tags.id=SEARCH_TERM_PLACEHOLDER"
)

# Simpler direct approach: AWS has a JSON search API used by the docs site
_SEARCH_API = (
    "https://docs.aws.amazon.com/en_us/search/doc-search.html"
    "?searchPath=documentation&searchQuery={query}"
    "&x=0&y=0&this_doc_guide=*&doc_locale=en_US"
)

# The actual JSON endpoint used internally by docs.aws.amazon.com
_CLOUDSEARCH_API = (
    "https://cloudsearchdomain.us-east-1.amazonaws.com/2013-01-01/search"
    "?q={query}&q.parser=simple&size=5&return=_all_fields"
)


def _fetch_docs_sync(query: str, top_k: int = 3) -> list[dict]:
    """Synchronous AWS docs search — run via executor."""
    results: list[dict] = []
    try:
        encoded = quote_plus(query)
        # Use the AWS documentation search suggestions API
        url = (
            "https://docs.aws.amazon.com/autocomplete"
            f"?q={encoded}&locale=en_US&limit={top_k * 2}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (AWS Meeting Assistant; docs lookup)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read().decode())

        suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
        for item in suggestions[:top_k]:
            title = item.get("title", "")
            path = item.get("url", "") or item.get("path", "")
            if not path:
                continue
            if not path.startswith("http"):
                path = "https://docs.aws.amazon.com" + path
            snippet = item.get("description", "") or item.get("excerpt", "")
            results.append({
                "text": f"{title}\n{snippet}".strip(),
                "url": path,
                "title": title,
                "score": 0.5,
            })

    except Exception as e:
        logger.debug(f"AWS docs autocomplete failed ({e}), trying search fallback")
        try:
            results = _fetch_docs_search_fallback(query, top_k)
        except Exception as e2:
            logger.debug(f"AWS docs search fallback also failed: {e2}")

    return results


def _fetch_docs_search_fallback(query: str, top_k: int) -> list[dict]:
    """Fallback: scrape search result titles from the HTML search page."""
    import html
    import re
    encoded = quote_plus(query)
    url = (
        "https://docs.aws.amazon.com/search/doc-search.html"
        f"?searchPath=documentation&searchQuery={encoded}&this_doc_guide=*"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AWSMeetingAssistant/1.0)",
            "Accept": "text/html",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        html_content = resp.read().decode("utf-8", errors="replace")

    # Extract search result links and titles
    pattern = re.compile(
        r'<a[^>]+href="(https://docs\.aws\.amazon\.com/[^"]+)"[^>]*>'
        r'(.*?)</a>',
        re.DOTALL,
    )
    seen: set[str] = set()
    results: list[dict] = []
    for m in pattern.finditer(html_content):
        href = html.unescape(m.group(1))
        title = re.sub(r"<[^>]+>", "", html.unescape(m.group(2))).strip()
        if not title or href in seen:
            continue
        seen.add(href)
        results.append({
            "text": title,
            "url": href,
            "title": title,
            "score": 0.5,
        })
        if len(results) >= top_k:
            break

    return results


async def search_aws_docs(query: str, top_k: int = 3) -> list[dict]:
    """Async AWS docs search. Returns up to top_k results scored at 0.5."""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            None, partial(_fetch_docs_sync, query, top_k)
        )
    except Exception as e:
        logger.warning(f"AWS docs search failed for {query!r}: {e}")
        return []


def merge_and_dedupe(
    existing: list[dict],
    new_results: list[dict],
    max_results: int = 25,
) -> tuple[list[dict], set[str]]:
    """Merge new KB results into existing accumulated list.

    Returns (merged_list, all_seen_uris) deduplicated by URL, sorted by score desc,
    capped at max_results.
    """
    seen: set[str] = {r.get("url", r.get("uri", "")) for r in existing}
    merged = list(existing)
    for r in new_results:
        uri = r.get("url", r.get("uri", ""))
        if uri and uri not in seen:
            seen.add(uri)
            merged.append(r)
    merged.sort(key=lambda x: -x.get("score", 0.0))
    return merged[:max_results], seen
