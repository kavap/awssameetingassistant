#!/usr/bin/env python3
"""KB Ingestion CLI — uploads AWS docs to S3 and triggers Bedrock KB sync.

Usage:
    uv run python scripts/ingest.py --urls data/urls.txt
    uv run python scripts/ingest.py --urls data/urls.txt --sync-only
    uv run python scripts/ingest.py --urls data/urls.txt --prefix custom/path/

Requires BEDROCK_KB_S3_BUCKET, BEDROCK_KB_ID, BEDROCK_KB_DATA_SOURCE_ID in .env.
Run scripts/setup_kb.py first to create the KB and get these values.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from backend.config import settings

console = Console()

CHUNK_SIZE = 512   # words per chunk
CHUNK_OVERLAP = 64
MAX_CONCURRENT = 3
S3_PREFIX = "kb-documents/"

_STRIP_TAGS = {"nav", "header", "footer", "script", "style", "aside", "form", "button"}


def extract_text(html: str) -> tuple[str, str]:
    """Return (title, clean_text) from HTML."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()
    content = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="main-content")
        or soup.find(id="content")
        or soup.body
    )
    if not content:
        return title, ""
    text = re.sub(r"\s+", " ", content.get_text(separator=" ", strip=True)).strip()
    return title, text


def chunk_text(text: str) -> list[str]:
    words = text.split()
    if len(words) <= CHUNK_SIZE:
        return [text] if text else []
    chunks, start = [], 0
    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def upload_chunk_to_s3(
    s3_client,
    bucket: str,
    key: str,
    text: str,
    metadata: dict,
) -> None:
    """Upload a text chunk and its metadata JSON sidecar to S3."""
    # Upload document text
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=text.encode("utf-8"),
        ContentType="text/plain",
    )

    # Upload Bedrock KB metadata sidecar: <key>.metadata.json
    # Bedrock KB reads these to populate metadata fields on each chunk
    meta_key = f"{key}.metadata.json"
    s3_client.put_object(
        Bucket=bucket,
        Key=meta_key,
        Body=json.dumps({"metadataAttributes": metadata}).encode("utf-8"),
        ContentType="application/json",
    )


async def ingest_url(
    url: str,
    s3_client,
    bucket: str,
    prefix: str,
    http_client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    progress: Progress,
    task_id,
) -> tuple[int, int]:
    try:
        resp = await http_client.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        console.print(f"[red]FETCH ERROR[/red] {url}: {e}")
        return 0, 0

    title, text = extract_text(resp.text)
    if not text:
        console.print(f"[yellow]EMPTY[/yellow] {url}")
        return 0, 0

    chunks = chunk_text(text)
    ok, failed = 0, 0

    for i, chunk in enumerate(chunks):
        async with sem:
            try:
                doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url}#{i}"))
                s3_key = f"{prefix}{doc_id}.txt"
                metadata = {
                    "source_url": url,
                    "title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "content_hash": content_hash(chunk),
                }
                # Run synchronous S3 upload in executor
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    upload_chunk_to_s3,
                    s3_client,
                    bucket,
                    s3_key,
                    chunk,
                    metadata,
                )
                ok += 1
            except Exception as e:
                console.print(f"[red]S3 ERROR[/red] chunk {i} of {url}: {e}")
                failed += 1

        progress.advance(task_id)

    return ok, failed


def trigger_kb_sync(kb_id: str, data_source_id: str) -> str | None:
    """Start a Bedrock KB ingestion job. Returns job ID or None on failure."""
    try:
        client = boto3.client("bedrock-agent", region_name=settings.aws_region)
        resp = client.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=data_source_id,
        )
        return resp["ingestionJob"]["ingestionJobId"]
    except Exception as e:
        console.print(f"[red]KB SYNC ERROR[/red]: {e}")
        return None


async def main(urls_file: str, sync_only: bool, prefix: str) -> None:
    bucket = settings.bedrock_kb_s3_bucket
    kb_id = settings.bedrock_kb_id
    ds_id = settings.bedrock_kb_data_source_id

    console.rule("[bold blue]AWS KB Ingestion → Bedrock Knowledge Base[/bold blue]")

    if not bucket:
        console.print("[red]ERROR[/red]: BEDROCK_KB_S3_BUCKET not set in .env")
        console.print("Run: [bold]uv run python scripts/setup_kb.py[/bold] to create the KB first.")
        sys.exit(1)

    if sync_only:
        if not kb_id or not ds_id:
            console.print("[red]ERROR[/red]: BEDROCK_KB_ID and BEDROCK_KB_DATA_SOURCE_ID required for --sync-only")
            sys.exit(1)
        console.print(f"Triggering KB sync for KB [bold]{kb_id}[/bold]...")
        job_id = trigger_kb_sync(kb_id, ds_id)
        if job_id:
            console.print(f"[green]Ingestion job started:[/green] {job_id}")
        return

    path = Path(urls_file)
    if not path.exists():
        console.print(f"[red]File not found:[/red] {urls_file}")
        sys.exit(1)

    urls = [
        l.strip() for l in path.read_text().splitlines()
        if l.strip() and not l.startswith("#")
    ]
    if not urls:
        console.print("[yellow]No URLs to process.[/yellow]")
        sys.exit(0)

    console.print(f"URLs: [bold]{len(urls)}[/bold]  |  S3 bucket: [bold]{bucket}[/bold]  |  Prefix: [bold]{prefix}[/bold]")

    s3 = boto3.client("s3", region_name=settings.aws_region)
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    total_ok = total_failed = 0

    async with httpx.AsyncClient(headers={"User-Agent": "AWS-Meeting-Assistant/1.0"}) as http:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            for url in urls:
                task_id = progress.add_task(f"[cyan]{url[:60]}[/cyan]", total=20)
                ok, failed = await ingest_url(url, s3, bucket, prefix, http, sem, progress, task_id)
                total_ok += ok
                total_failed += failed
                progress.update(task_id, completed=progress.tasks[task_id].total)

    # Summary
    table = Table(title="Upload Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold")
    table.add_row("URLs processed", str(len(urls)))
    table.add_row("Chunks uploaded to S3", str(total_ok))
    table.add_row("Chunks failed", str(total_failed))
    table.add_row("S3 bucket", bucket)
    console.print(table)

    # Trigger KB sync if configured
    if kb_id and ds_id:
        console.print(f"\nTriggering Bedrock KB ingestion job...")
        job_id = trigger_kb_sync(kb_id, ds_id)
        if job_id:
            console.print(f"[green]✓ Ingestion job started:[/green] [bold]{job_id}[/bold]")
            console.print("Monitor in AWS Console: Bedrock → Knowledge Bases → Data Sources → Sync Jobs")
        else:
            console.print("[yellow]Warning:[/yellow] Could not trigger KB sync. Start it manually in the AWS Console.")
    else:
        console.print(
            "\n[yellow]Note:[/yellow] BEDROCK_KB_ID or BEDROCK_KB_DATA_SOURCE_ID not set. "
            "Documents uploaded to S3 — trigger sync manually in AWS Console or run:\n"
            "  uv run python scripts/ingest.py --sync-only"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest AWS docs into Bedrock KB via S3.")
    parser.add_argument("--urls", default="data/urls.txt", help="Path to URLs file")
    parser.add_argument("--sync-only", action="store_true", help="Skip upload, only trigger KB sync")
    parser.add_argument("--prefix", default=S3_PREFIX, help="S3 key prefix for uploaded chunks")
    args = parser.parse_args()
    asyncio.run(main(args.urls, args.sync_only, args.prefix))
