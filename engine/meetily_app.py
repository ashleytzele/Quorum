#!/usr/bin/env python3
"""Read-only adapter over the official Meetily desktop app's SQLite
(~/Library/Application Support/com.meetily.ai/meeting_minutes.sqlite). Pulls a
meeting's transcript so review.py can generate minutes without re-transcribing.
NEVER writes to the app's data — every connection is opened read-only."""
import os
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = (Path.home() / "Library" / "Application Support"
              / "com.meetily.ai" / "meeting_minutes.sqlite")


def _db_path() -> Path:
    p = Path(os.environ.get("MEETILY_APP_DB", DEFAULT_DB))
    if not p.exists():
        sys.exit(f"Meetily app DB not found at {p}. Is the app installed? "
                 f"Override with MEETILY_APP_DB=/path/to/meeting_minutes.sqlite")
    return p


def _connect(db_path):
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _assemble_from_chunks(rows) -> str:
    """rows: list of (speaker, text) -> one transcript; blanks dropped, speaker prefix when set."""
    lines = []
    for speaker, text in rows:
        text = (text or "").strip()
        if not text:
            continue
        lines.append(f"{speaker}: {text}" if speaker else text)
    return "\n".join(lines).strip()


def list_meetings(db_path=None) -> list:
    c = _connect(db_path or _db_path())
    try:
        rows = c.execute("select id, title, created_at, folder_path "
                         "from meetings order by created_at desc").fetchall()
    finally:
        c.close()
    return [{"id": r[0], "title": r[1], "created_at": r[2], "folder_path": r[3]} for r in rows]


def get_transcript(meeting_id: str, db_path=None) -> str:
    c = _connect(db_path or _db_path())
    try:
        row = c.execute("select transcript_text from transcript_chunks where meeting_id=?",
                        (meeting_id,)).fetchone()
        if row and (row[0] or "").strip():
            text = row[0].strip()
        else:
            parts = c.execute("select speaker, transcript from transcripts "
                              "where meeting_id=? order by audio_start_time",
                              (meeting_id,)).fetchall()
            text = _assemble_from_chunks(parts)
    finally:
        c.close()
    if not text.strip():
        sys.exit(f"No transcript found for Meetily app meeting {meeting_id}.")
    return text
