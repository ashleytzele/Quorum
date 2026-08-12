#!/usr/bin/env python3
"""Supabase I/O for the review pipeline — pull a Quorum meeting's pre-meeting
notes, and publish the finished review to its minutes. All network access lives
here; review.py's core stays offline-testable."""

import ipaddress
import os
import socket
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

# Public-link fetching (opt-out via QUORUM_FETCH_LINKS=0). Caps keep one page from
# blowing up the prompt; the timeout/size bounds keep a slow or huge link from stalling.
_LINK_CAP = int(os.environ.get("QUORUM_LINK_CAP", "6000"))        # chars of text kept per link
_LINK_TIMEOUT = float(os.environ.get("QUORUM_LINK_TIMEOUT", "10"))  # seconds per request
_LINK_MAX_BYTES = 3_000_000                                        # download ceiling per link


def _combine_inputs(pre_notes, file_texts, links, during_notes=()) -> str:
    parts = []
    for team, text in pre_notes:
        if text and text.strip():
            parts.append(f"--- {team} (pre-meeting note) ---")
            parts.append(text.strip())
            parts.append("")
    for team, text in during_notes:
        if text and text.strip():
            parts.append(f"--- {team} (during-meeting note) ---")
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


def _host_is_public(host: str) -> bool:
    """True only if EVERY resolved address is a routable public IP. `not is_global` blocks
    localhost / private / link-local (incl. metadata 169.254.169.254) / CGNAT 100.64/10
    (Tailscale) / multicast / unspecified; `is_reserved` additionally blocks NAT64-wrapped
    reserved space that still reports is_global. (IPv4-mapped IPv6 like ::ffff:169.254.169.254
    is classified correctly only on Python ≥3.13 — this venv is 3.14.)"""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for *_, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        if ip.is_reserved or not ip.is_global:
            return False
    return True


def _ext_for(content_type: str, url: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    known = {"text/html": ".html", "application/xhtml+xml": ".html",
             "application/pdf": ".pdf", "text/plain": ".txt"}
    if ct in known:
        return known[ct]
    suf = Path(urlparse(url).path).suffix.lower()
    return suf if suf in (".html", ".htm", ".pdf", ".txt", ".md") else ".html"


def fetch_link_text(url: str):
    """Fetch a PUBLIC http(s) link and return its markitdown-converted text (capped),
    or None if it can't be fetched safely/successfully — the caller then falls back to
    the bare URL. Public only: private/localhost hosts are refused and EVERY redirect hop
    is re-validated before connecting. ponytail: DNS can rebind between the check and the
    connect; acceptable for a local single-user tool — pin the resolved IP via a custom
    adapter if this ever serves multiple tenants."""
    try:
        import requests
        from markitdown import MarkItDown
    except Exception:
        return None
    current = url
    for _hop in range(5):
        try:
            p = urlparse(current)
            host = p.hostname                      # can raise ValueError on a malformed IPv6 authority
        except ValueError:
            return None
        if p.scheme not in ("http", "https") or not host:
            return None
        if not _host_is_public(host):
            return None
        try:
            r = requests.get(current, timeout=_LINK_TIMEOUT, stream=True,
                             allow_redirects=False,
                             headers={"User-Agent": "Quorum-minutes/1.0"})
        except Exception:
            return None
        try:
            if r.is_redirect or r.is_permanent_redirect:
                loc = r.headers.get("location")
                if not loc:
                    return None
                current = urljoin(current, loc)
                continue
            if r.status_code != 200:
                return None
            body = r.raw.read(_LINK_MAX_BYTES + 1, decode_content=True)
        except Exception:
            return None
        finally:
            r.close()
        if not body or len(body) > _LINK_MAX_BYTES:
            return None
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=_ext_for(r.headers.get("content-type", ""), current))
            with os.fdopen(fd, "wb") as fh:
                fh.write(body)
            text = (MarkItDown().convert(tmp).text_content or "").strip()
        except Exception:              # incl. mkstemp OSError — degrade to the bare URL, never escape
            return None
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        if not text:
            return None
        return text[:_LINK_CAP].rstrip() + "\n…[truncated]" if len(text) > _LINK_CAP else text
    return None  # too many redirects


def _client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — put them in .env.")
    from supabase import create_client
    return create_client(url, key)


def fetch_notes(meeting_id: str) -> str:
    c = _client()
    note_rows = (c.table("notes").select("pre_note, content, teams(name)")
                 .eq("meeting_id", meeting_id).execute().data) or []
    pre_notes = [((r.get("teams") or {}).get("name") or "Team",
                  r.get("pre_note") or "") for r in note_rows]
    during_notes = [((r.get("teams") or {}).get("name") or "Team",
                     r.get("content") or "") for r in note_rows]

    sub_rows = (c.table("submissions")
                .select("file_path, file_name, mime, url")
                .eq("meeting_id", meeting_id).execute().data) or []
    from markitdown import MarkItDown
    md = MarkItDown()
    fetch_links = os.environ.get("QUORUM_FETCH_LINKS", "1") != "0"
    file_texts, links = [], []
    for s in sub_rows:
        if s.get("mime") == "link" or (s.get("url") and not s.get("file_path")):
            url = s.get("url")
            label = s.get("file_name") or url
            text = fetch_link_text(url) if (fetch_links and url) else None
            if text:
                # Fetched public link → include its content like an attached document.
                file_texts.append((f"link: {label} — {url}", text))
            else:
                # Private/unreachable/disabled → keep the bare URL (today's behavior).
                links.append((label, url))
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

    combined = _combine_inputs(pre_notes, file_texts, links, during_notes)
    if not combined:
        print(f"warning: no notes or submissions for meeting {meeting_id} — "
              f"generating from the recording alone.", file=sys.stderr)
        return ""
    return combined


def sync_templates(rows) -> list:
    """Upsert template-registry rows [{stem, name, description}] into Supabase."""
    if not rows:
        return []
    c = _client()
    res = c.table("templates").upsert(rows, on_conflict="stem").execute()
    return res.data or []


def get_meeting_template(meeting_id: str):
    """Return the meeting's chosen template stem, or None."""
    c = _client()
    rows = (c.table("meetings").select("template")
            .eq("id", meeting_id).execute().data) or []
    return (rows[0].get("template") if rows else None) or None


def set_meeting_status(meeting_id: str, status: str) -> list:
    """update meetings set status=<status> where id=<meeting_id>."""
    c = _client()
    res = c.table("meetings").update({"status": status}).eq("id", meeting_id).execute()
    return res.data or []


def publish_minutes(meeting_id: str, markdown: str) -> list:
    if not markdown or not markdown.strip():
        sys.exit("Refusing to publish empty minutes.")
    c = _client()
    res = (c.table("meetings")
           .update({"minutes_final": markdown, "is_active": False, "status": "published"})
           .eq("id", meeting_id).execute())
    if not res.data:
        sys.exit(f"No meeting matched id {meeting_id}; nothing published.")
    return res.data
