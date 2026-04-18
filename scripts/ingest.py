#!/usr/bin/env python3
"""KB Ingestion CLI.

Usage:
    uv run python scripts/ingest.py --urls data/urls.txt
    uv run python scripts/ingest.py --urls data/urls.txt --reset
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import sys
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from backend.config import settings
from backend.knowledge_base import embeddings, qdrant_client

console = Console()

CHUNK_SIZE = 512  # tokens (approximate: words)
CHUNK_OVERLAP = 64
MAX_CONCURRENT_EMBEDS = 3

# Tags to strip from HTML
_STRIP_TAGS = {"nav", "header", "footer", "script", "style", "aside", "form", "button"}

# Tags that are good content containers
_CONTENT_TAGS = ["main", "article", "[role=main]", ".content", "#content"]


def extract_text_from_html(html: str, url: str) -> tuple[str, str]:
    """Extract clean text and title from HTML. Returns (title, text)."""
    soup = BeautifulSoup(html, "lxml")

    # Get title
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    # Remove noisy tags
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()

    # Try to find the main content area
    content = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="main-content")
        or soup.find(id="content")
        or soup.find(class_="content")
        or soup.body
    )

    if content is None:
        return title, ""

    text = content.get_text(separator=" ", strip=True)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if len(words) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_size - overlap

    return chunks


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


async def ingest_url(
    url: str,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    progress: Progress,
    task_id,
) -> tuple[int, int]:
    """Fetch, parse, chunk, embed, and upsert one URL. Returns (chunks_ok, chunks_failed)."""
    try:
        response = await client.get(url, follow_redirects=True, timeout=30)
        response.raise_for_status()
    except Exception as e:
        console.print(f"[red]FETCH ERROR[/red] {url}: {e}")
        return 0, 0

    title, text = extract_text_from_html(response.text, url)
    if not text:
        console.print(f"[yellow]EMPTY[/yellow] {url}")
        return 0, 0

    chunks = chunk_text(text)
    ok = 0
    failed = 0

    for i, chunk in enumerate(chunks):
        async with sem:
            try:
                dense_vec = embeddings.embed_sync(chunk)
                sparse_vec = qdrant_client.compute_sparse_vector(chunk)
                doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url}#{i}"))
                metadata = {
                    "url": url,
                    "title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "content_hash": content_hash(chunk),
                }
                await qdrant_client.upsert_document(
                    doc_id=doc_id,
                    text=chunk,
                    metadata=metadata,
                    dense_vec=dense_vec,
                    sparse_vec=sparse_vec,
                )
                ok += 1
            except Exception as e:
                console.print(f"[red]EMBED/UPSERT ERROR[/red] chunk {i} of {url}: {e}")
                failed += 1

        progress.advance(task_id)

    return ok, failed


async def main(urls_file: str, reset: bool) -> None:
    # Load URLs
    path = Path(urls_file)
    if not path.exists():
        console.print(f"[red]File not found:[/red] {urls_file}")
        sys.exit(1)

    urls = [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    if not urls:
        console.print("[yellow]No URLs to process.[/yellow]")
        sys.exit(0)

    console.rule("[bold blue]AWS KB Ingestion Pipeline[/bold blue]")
    console.print(f"URLs to process: [bold]{len(urls)}[/bold]")
    console.print(f"Qdrant: [bold]{settings.qdrant_host}:{settings.qdrant_port}[/bold]")
    console.print(f"Collection: [bold]{settings.qdrant_collection}[/bold]")
    console.print()

    # Setup Qdrant
    if reset:
        console.print("[yellow]Dropping existing collection...[/yellow]")
        await qdrant_client.drop_collection()

    await qdrant_client.ensure_collection()
    console.print("[green]Collection ready.[/green]")

    # Semaphore to rate-limit Bedrock embedding calls
    sem = asyncio.Semaphore(MAX_CONCURRENT_EMBEDS)

    total_ok = 0
    total_failed = 0

    async with httpx.AsyncClient(
        headers={"User-Agent": "AWS-Meeting-Assistant/1.0"},
        follow_redirects=True,
    ) as http_client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            for url in urls:
                # Estimate chunks for progress bar (rough: 1 chunk per 500 words)
                task_id = progress.add_task(f"[cyan]{url[:60]}[/cyan]", total=20)
                ok, failed = await ingest_url(url, http_client, sem, progress, task_id)
                total_ok += ok
                total_failed += failed
                progress.update(task_id, completed=progress.tasks[task_id].total)

    # Summary table
    table = Table(title="Ingestion Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold")
    table.add_row("URLs processed", str(len(urls)))
    table.add_row("Chunks indexed", str(total_ok))
    table.add_row("Chunks failed", str(total_failed))
    table.add_row("Collection", settings.qdrant_collection)
    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest AWS docs/blogs into the KB.")
    parser.add_argument("--urls", default="data/urls.txt", help="Path to URLs file")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate collection")
    args = parser.parse_args()

    asyncio.run(main(args.urls, args.reset))
