#!/usr/bin/env python3
"""Local bridge for MeeTeam's admin minutes page. Shells the existing review.py
(--meetily-app transcript + --meeting team-notes + template) and returns markdown.
Binds 127.0.0.1 only; CORS-allows the MeeTeam origin. Reuses review.py/quorum/
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
MEETEAM_ORIGIN = os.environ.get("MEETEAM_ORIGIN", "http://localhost:8000")
_PROJECTS_RE = re.compile(r"^projects \(\d+\):\s*(.*)$", re.M)


def _generate_argv(python, review_py, meetily_id, meeting_id, template, out_path):
    argv = [python, str(review_py), "--meetily-app", meetily_id, "--meeting", meeting_id]
    if template:
        argv += ["-t", str(REPO_ROOT / f"{template}.json")]
    argv += ["-o", str(out_path)]
    return argv


def _parse_projects(stdout):
    m = _PROJECTS_RE.search(stdout or "")
    if not m or not m.group(1).strip():
        return []
    return [x.strip() for x in m.group(1).split(",") if x.strip()]


def create_app() -> Flask:
    app = Flask(__name__)

    @app.after_request
    def _cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = MEETEAM_ORIGIN
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

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8899)
