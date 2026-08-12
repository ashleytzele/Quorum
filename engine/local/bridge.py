#!/usr/bin/env python3
"""Local bridge for Quorum's admin minutes page. Shells the existing review.py
(--meetily-app transcript + --meeting team-notes + template) and returns markdown.
Binds 127.0.0.1 only; CORS-allows the Quorum origin. Reuses review.py/quorum/
meetily_app unchanged — this file adds no pipeline logic."""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))          # so `import meetily_app` resolves
# QUORUM_ORIGIN sets the CORS allow-origin. MEETEAM_ORIGIN kept as a fallback so an existing .env doesn't break.
QUORUM_ORIGIN = os.environ.get("QUORUM_ORIGIN", os.environ.get("MEETEAM_ORIGIN", "http://localhost:8000"))
_PROJECTS_RE = re.compile(r"^projects \(\d+\):\s*(.*)$", re.M)
# Faster whisper model for the interactive record/import path (nearly large-v3 accuracy,
# ~5-8x faster). Overridable; only used if the file exists, else review.py keeps its default.
_FAST_WHISPER = os.environ.get("BRIDGE_WHISPER_MODEL", str(
    Path.home() / "Library" / "Application Support" / "com.meetily.ai"
    / "models" / "ggml-large-v3-turbo-q5_0.bin"))


def _transcribe_env(fast=False):
    """Env for the transcription subprocess. Default keeps review.py's accurate
    windowed large-v3. `fast` (opt-in 'Fast draft') switches to single-pass + turbo:
    ~5-8x faster but ~35-40% less content on hard/accented audio — measured."""
    env = dict(os.environ)
    if fast:
        env["WHISPER_SINGLE_PASS"] = "1"
        if Path(_FAST_WHISPER).exists():
            env["WHISPER_MODEL"] = _FAST_WHISPER
    return env


def _template_arg(template):
    """Resolve a template stem to a `-t <path>` across ALL sources (repo + Meetily app
    dirs), via review.py's Phase-8 resolver. Returns [] when not given or not found — then
    review.py falls back to the meeting's stored template (also resolved across the union)."""
    if not template:
        return []
    import review
    p = review._find_template_path(template, REPO_ROOT)
    return ["-t", str(p)] if p else []


def _generate_argv(python, review_py, meetily_id, meeting_id, template, out_path):
    return [python, str(review_py), "--meetily-app", meetily_id, "--meeting", meeting_id,
            *_template_arg(template), "-o", str(out_path)]


def _parse_projects(stdout):
    m = _PROJECTS_RE.search(stdout or "")
    if not m or not m.group(1).strip():
        return []
    return [x.strip() for x in m.group(1).split(",") if x.strip()]


_AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".webm", ".mp4", ".ogg", ".aac", ".flac"}


def _safe_audio_suffix(filename):
    ext = Path(filename or "").suffix.lower()
    return ext if ext in _AUDIO_EXTS else ".webm"


def _generate_audio_argv(python, review_py, audio_path, meeting_id, template, out_path):
    return [python, str(review_py), str(audio_path), "--meeting", meeting_id,
            *_template_arg(template), "-o", str(out_path)]


def create_app() -> Flask:
    app = Flask(__name__)

    @app.after_request
    def _cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = QUORUM_ORIGIN
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/recordings")
    def recordings():
        import meetily_app
        return jsonify(meetily_app.list_meetings())

    @app.route("/generate", methods=["POST", "OPTIONS"])
    def generate():
        if request.method == "OPTIONS":
            return ("", 204)
        b = request.get_json(force=True) or {}
        meeting_id, meetily_id = b.get("meeting_id"), b.get("meetily_id")
        if not meeting_id or not meetily_id:
            return (jsonify({"error": "meeting_id and meetily_id required"}), 400)
        template = b.get("template")
        if template and not re.fullmatch(r"[A-Za-z0-9_-]+", template):
            return (jsonify({"error": "invalid template name"}), 400)
        try:
            fd, tmp = tempfile.mkstemp(suffix=".md")
            os.close(fd)
            out = Path(tmp)
            try:
                argv = _generate_argv(sys.executable, REPO_ROOT / "review.py",
                                      meetily_id, meeting_id, template, out)
                r = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, text=True)
                if r.returncode != 0 or not out.exists() or not out.read_text().strip():
                    return (jsonify({"error": (r.stderr or "generation failed").strip()}), 500)
                markdown = out.read_text()
            finally:
                if out.exists():
                    out.unlink()
            return jsonify({"ok": True, "markdown": markdown,
                            "projects": _parse_projects(r.stdout),
                            "warnings": [l for l in (r.stderr or "").splitlines() if l.strip()]})
        except Exception as e:
            return (jsonify({"error": str(e)}), 500)

    @app.route("/generate-audio", methods=["POST", "OPTIONS"])
    def generate_audio():
        if request.method == "OPTIONS":
            return ("", 204)
        meeting_id = request.form.get("meeting_id")
        f = request.files.get("audio")
        if not meeting_id or f is None:
            return (jsonify({"error": "meeting_id and audio file required"}), 400)
        template = request.form.get("template") or None
        if template and not re.fullmatch(r"[A-Za-z0-9_-]+", template):
            return (jsonify({"error": "invalid template name"}), 400)
        fast = bool(request.form.get("fast"))
        try:
            afd, atmp = tempfile.mkstemp(suffix=_safe_audio_suffix(f.filename))
            os.close(afd)
            audio = Path(atmp)
            ofd, otmp = tempfile.mkstemp(suffix=".md")
            os.close(ofd)
            out = Path(otmp)
            try:
                f.save(str(audio))
                argv = _generate_audio_argv(sys.executable, REPO_ROOT / "review.py",
                                            audio, meeting_id, template, out)
                r = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, text=True,
                                   env=_transcribe_env(fast))
                if r.returncode != 0 or not out.exists() or not out.read_text().strip():
                    return (jsonify({"error": (r.stderr or "generation failed").strip()}), 500)
                markdown = out.read_text()
            finally:
                for p in (audio, out, audio.with_suffix(".manglish.txt")):
                    try:
                        p.unlink()
                    except OSError:
                        pass
            return jsonify({"ok": True, "markdown": markdown,
                            "projects": _parse_projects(r.stdout),
                            "warnings": [l for l in (r.stderr or "").splitlines() if l.strip()]})
        except Exception as e:
            return (jsonify({"error": str(e)}), 500)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8899)
