#!/usr/bin/env python3
"""Local single-user GUI backend. Stores meetings as folders, spawns ffmpeg for
recording, and shells out to review.py for generation. Bind 127.0.0.1 only."""
import json
import re
import datetime
import subprocess
import signal
import os
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_DEVICE_LINE = re.compile(r"\[(\d+)\]\s+(.+?)\s*$")


def _safe_name(s: str) -> str:
    if not isinstance(s, str) or not _NAME_RE.match(s):
        raise ValueError(f"unsafe name: {s!r}")
    return s


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return s or "meeting"


def _meeting_status(d: Path) -> str:
    if (d / "minutes.md").exists():
        return "done"
    if (d / "recording.m4a").exists():
        return "recorded"
    return "ready"


def _create_meeting(root: Path, title: str, template: str) -> dict:
    root = Path(root)
    base = _slugify(title)
    slug, n = base, 1
    while (root / slug).exists():
        n += 1
        slug = f"{base}-{n}"
    d = root / slug
    (d / "notes").mkdir(parents=True)
    meta = {"title": title or "Untitled", "date": datetime.date.today().isoformat(),
            "template": template or "weekly_review", "created": datetime.datetime.now().isoformat(timespec="seconds")}
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    return {"id": slug, **{k: meta[k] for k in ("title", "date", "template")}}


def _read_meta(d: Path) -> dict:
    return json.loads((d / "meta.json").read_text())


def _list_meetings(root: Path) -> list:
    root = Path(root)
    out = []
    for d in root.iterdir() if root.exists() else []:
        if not (d / "meta.json").exists():
            continue
        meta = _read_meta(d)
        out.append({"id": d.name, "title": meta.get("title", d.name),
                    "date": meta.get("date", ""), "template": meta.get("template", ""),
                    "status": _meeting_status(d)})
    out.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    return out


def _list_templates(repo_root: Path) -> list:
    rows = []
    for p in sorted(Path(repo_root).glob("*.json")):
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(data, dict) and data.get("name") and "sections" in data:
            rows.append({"stem": p.stem, "name": data["name"], "description": data.get("description") or ""})
    return rows


def _notes(d: Path) -> list:
    nd = d / "notes"
    return [{"name": f.stem, "content": f.read_text()} for f in sorted(nd.glob("*.md"))] if nd.exists() else []


def _list_audio() -> str:
    r = subprocess.run(["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                       capture_output=True, text=True)
    return r.stderr or r.stdout


def _resolve_device_index(list_output: str, device_name: str):
    in_audio = False
    for line in list_output.splitlines():
        if "AVFoundation audio devices:" in line:
            in_audio = True
            continue
        if "AVFoundation video devices:" in line:
            in_audio = False
            continue
        if in_audio:
            m = _DEVICE_LINE.search(line)
            if m and m.group(2) == device_name:
                return m.group(1)
    return None


def _spawn_ffmpeg(idx: str, out_path: Path):
    return subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-f", "avfoundation",
         "-i", f":{idx}", "-c:a", "aac", str(out_path)])


def create_app(meetings_root) -> Flask:
    root = Path(meetings_root)
    root.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__, static_folder=None)
    app.config["ROOT"] = root

    def _dir(mid):
        return root / _safe_name(mid)

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:fn>")
    def static_files(fn):
        return send_from_directory(STATIC, fn)

    @app.get("/api/templates")
    def templates():
        return jsonify(_list_templates(REPO_ROOT))

    @app.get("/api/meetings")
    def meetings():
        return jsonify(_list_meetings(root))

    @app.post("/api/meetings")
    def create():
        b = request.get_json(force=True)
        return jsonify(_create_meeting(root, b.get("title", ""), b.get("template", "weekly_review")))

    @app.get("/api/meetings/<mid>")
    def get_meeting(mid):
        try:
            d = _dir(mid)
        except ValueError:
            return ("bad id", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        mins = (d / "minutes.md")
        return jsonify({"meta": {**_read_meta(d), "id": d.name, "status": _meeting_status(d)},
                        "notes": _notes(d),
                        "minutes": mins.read_text() if mins.exists() else ""})

    @app.put("/api/meetings/<mid>")
    def update_meeting(mid):
        try:
            d = _dir(mid)
        except ValueError:
            return ("bad id", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        meta = _read_meta(d)
        b = request.get_json(force=True)
        for k in ("title", "template"):
            if k in b:
                meta[k] = b[k]
        (d / "meta.json").write_text(json.dumps(meta, indent=2))
        return jsonify({"ok": True})

    @app.put("/api/meetings/<mid>/notes/<path:name>")
    def save_note(mid, name):
        try:
            d, safe = _dir(mid), _safe_name(name)
        except ValueError:
            return ("bad name", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        (d / "notes").mkdir(exist_ok=True)
        (d / "notes" / f"{safe}.md").write_text(request.get_json(force=True).get("content", ""))
        return jsonify({"ok": True})

    rec = {"proc": None, "meeting_id": None}   # single active recording

    @app.get("/api/record/status")
    def record_status():
        active = rec["proc"] is not None and rec["proc"].poll() is None
        return jsonify({"recording": active, "meeting_id": rec["meeting_id"] if active else None})

    @app.post("/api/meetings/<mid>/record/start")
    def record_start(mid):
        try:
            d = _dir(mid)
        except ValueError:
            return ("bad id", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        if rec["proc"] is not None and rec["proc"].poll() is None:
            return ("already recording", 409)
        name = os.environ.get("RECORD_DEVICE", "Aggregate Device")
        idx = _resolve_device_index(_list_audio(), name)
        if idx is None:
            return (jsonify({"error": f"audio device {name!r} not found"}), 400)
        rec["proc"] = _spawn_ffmpeg(idx, d / "recording.m4a")
        rec["meeting_id"] = d.name
        return jsonify({"ok": True})

    @app.post("/api/meetings/<mid>/record/stop")
    def record_stop(mid):
        if rec["proc"] is None or rec["proc"].poll() is not None:
            rec["proc"], rec["meeting_id"] = None, None
            return ("not recording", 409)
        rec["proc"].send_signal(signal.SIGINT)
        try:
            rec["proc"].wait(timeout=10)
        except Exception:
            pass
        rec["proc"], rec["meeting_id"] = None, None
        f = _dir(mid) / "recording.m4a"
        if not (f.exists() and f.stat().st_size > 0):
            return (jsonify({"error": "recording produced no file"}), 500)
        return jsonify({"ok": True, "bytes": f.stat().st_size})

    return app


if __name__ == "__main__":
    app = create_app(REPO_ROOT / "meetings")
    app.run(host="127.0.0.1", port=8765)
