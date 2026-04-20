"""Meeting artifact persistence — JSON files in meetings/ directory."""
from __future__ import annotations

import json
import logging
import os
import pathlib
import time

logger = logging.getLogger(__name__)

# Resolve relative to CWD at import time (same convention as .env in lifespan)
MEETINGS_DIR = pathlib.Path(os.getcwd()) / "meetings"


def _ensure_dir() -> None:
    MEETINGS_DIR.mkdir(parents=True, exist_ok=True)


def save_meeting(record: dict) -> None:
    """Write full meeting record to meetings/{session_id}.json and update index."""
    _ensure_dir()
    session_id = record.get("session_id")
    if not session_id:
        raise ValueError("record must have session_id")

    # Atomic write: tmp file then rename
    target = MEETINGS_DIR / f"{session_id}.json"
    tmp = MEETINGS_DIR / f"{session_id}.json.tmp"
    tmp.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, target)
    logger.info(f"[storage] saved meeting {session_id} ({target.stat().st_size} bytes)")

    _update_index(session_id, record)


def list_meetings() -> list[dict]:
    """Return index entries sorted newest first. Empty list if no meetings saved."""
    index_path = MEETINGS_DIR / "index.json"
    if not index_path.exists():
        return []
    try:
        entries = json.loads(index_path.read_text(encoding="utf-8"))
        return sorted(entries, key=lambda e: e.get("stopped_at", 0), reverse=True)
    except Exception as e:
        logger.warning(f"[storage] index read failed: {e}")
        return []


def get_meeting(session_id: str) -> dict | None:
    """Load full meeting record. Returns None if not found."""
    path = MEETINGS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[storage] load failed for {session_id}: {e}")
        return None


def delete_meeting(session_id: str) -> bool:
    """Delete a meeting record and remove from index. Returns True if deleted."""
    path = MEETINGS_DIR / f"{session_id}.json"
    if not path.exists():
        return False
    path.unlink()
    _remove_from_index(session_id)
    logger.info(f"[storage] deleted meeting {session_id}")
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _update_index(session_id: str, record: dict) -> None:
    index_path = MEETINGS_DIR / "index.json"
    entries: list[dict] = []
    if index_path.exists():
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    # Build lightweight index entry (no full transcript/analysis)
    analysis_a = record.get("analysis_track_a") or {}
    new_entry = {
        "session_id": session_id,
        "customer_id": record.get("customer_id", "anonymous"),
        "meeting_type": record.get("meeting_type", ""),
        "meeting_name": record.get("meeting_name", ""),
        "started_at": record.get("started_at", 0),
        "stopped_at": record.get("stopped_at", time.time()),
        "transcript_count": len(record.get("transcript", [])),
        "stage": analysis_a.get("stage", 0),
        "cycle_count": analysis_a.get("cycle_count", 0),
    }

    # Replace existing entry if same session_id, otherwise prepend
    entries = [e for e in entries if e.get("session_id") != session_id]
    entries.insert(0, new_entry)

    tmp = MEETINGS_DIR / "index.json.tmp"
    tmp.write_text(json.dumps(entries, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, index_path)


def _remove_from_index(session_id: str) -> None:
    index_path = MEETINGS_DIR / "index.json"
    if not index_path.exists():
        return
    try:
        entries = json.loads(index_path.read_text(encoding="utf-8"))
        entries = [e for e in entries if e.get("session_id") != session_id]
        index_path.write_text(json.dumps(entries, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[storage] index remove failed: {e}")
