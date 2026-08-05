#!/usr/bin/env python3
"""Supabase I/O for the review pipeline — pull a Quorum meeting's pre-meeting
notes, and publish the finished review to its minutes. All network access lives
here; review.py's core stays offline-testable."""

import os
import sys
import tempfile
from pathlib import Path


def _combine_inputs(pre_notes, file_texts, links) -> str:
    parts = []
    for team, text in pre_notes:
        if text and text.strip():
            parts.append(f"--- {team} (pre-meeting note) ---")
            parts.append(text.strip())
            parts.append("")
    for name, text in file_texts:
        if text and text.strip():
            parts.append(f"--- {name} ---")
            parts.append(text.strip())
            parts.append("")
    for label, url in links:
        if url:
            parts.append(f"--- link: {label} ---")
            parts.append(url)
            parts.append("")
    return "\n".join(parts).strip()


def _client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — put them in .env.")
    from supabase import create_client
    return create_client(url, key)


def fetch_notes(meeting_id: str) -> str:
    c = _client()
    note_rows = (c.table("notes").select("pre_note, teams(name)")
                 .eq("meeting_id", meeting_id).execute().data) or []
    pre_notes = [((r.get("teams") or {}).get("name") or "Team",
                  r.get("pre_note") or "") for r in note_rows]

    sub_rows = (c.table("submissions")
                .select("file_path, file_name, mime, url")
                .eq("meeting_id", meeting_id).execute().data) or []
    from markitdown import MarkItDown
    md = MarkItDown()
    file_texts, links = [], []
    for s in sub_rows:
        if s.get("mime") == "link" or (s.get("url") and not s.get("file_path")):
            links.append((s.get("file_name") or s.get("url"), s.get("url")))
            continue
        if not s.get("file_path"):
            continue
        blob = c.storage.from_("submissions").download(s["file_path"])
        suffix = Path(s.get("file_name") or s["file_path"]).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            tmp = fh.name
            fh.write(blob)
        try:
            name = s.get("file_name") or Path(s["file_path"]).name
            file_texts.append((name, md.convert(tmp).text_content))
        finally:
            os.unlink(tmp)

    combined = _combine_inputs(pre_notes, file_texts, links)
    if not combined:
        sys.exit(f"No notes or submissions found for meeting {meeting_id}.")
    return combined


def publish_minutes(meeting_id: str, markdown: str) -> list:
    if not markdown or not markdown.strip():
        sys.exit("Refusing to publish empty minutes.")
    c = _client()
    res = (c.table("meetings")
           .update({"minutes_final": markdown, "is_active": False})
           .eq("id", meeting_id).execute())
    if not res.data:
        sys.exit(f"No meeting matched id {meeting_id}; nothing published.")
    return res.data
