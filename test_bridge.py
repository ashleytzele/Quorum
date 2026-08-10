import io
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent / "local"))
import bridge


def test_generate_argv_with_and_without_template():
    a = bridge._generate_argv("py", "review.py", "m1", "q1", "weekly_review", "/tmp/o.md")
    assert a == ["py", "review.py", "--meetily-app", "m1", "--meeting", "q1",
                 "-t", str(bridge.REPO_ROOT / "weekly_review.json"), "-o", "/tmp/o.md"]
    b = bridge._generate_argv("py", "review.py", "m1", "q1", None, "/tmp/o.md")
    assert b == ["py", "review.py", "--meetily-app", "m1", "--meeting", "q1", "-o", "/tmp/o.md"]


def test_parse_projects():
    assert bridge._parse_projects("projects (2): A, B\nwrote x\n") == ["A", "B"]
    assert bridge._parse_projects("nothing\n") == []


def test_health_and_cors():
    c = bridge.create_app().test_client()
    r = c.get("/health")
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    assert r.headers["Access-Control-Allow-Origin"]  # CORS header present


def test_generate_preflight_options():
    c = bridge.create_app().test_client()
    r = c.open("/generate", method="OPTIONS")
    assert r.status_code in (200, 204)
    assert r.headers["Access-Control-Allow-Origin"]


def test_recordings_via_stub(monkeypatch):
    import meetily_app
    monkeypatch.setattr(meetily_app, "list_meetings",
                        lambda *a, **k: [{"id": "m1", "title": "Alpha", "created_at": "2026-07-25"}])
    c = bridge.create_app().test_client()
    assert c.get("/recordings").get_json() == [{"id": "m1", "title": "Alpha", "created_at": "2026-07-25"}]


def test_generate_missing_ids_400():
    c = bridge.create_app().test_client()
    assert c.post("/generate", json={"meeting_id": "q1"}).status_code == 400


def test_generate_success(monkeypatch):
    def fake_run(argv, **kw):
        Path(argv[argv.index("-o") + 1]).write_text("# AI Minutes\nbody")
        class R: returncode = 0; stdout = "projects (1): P\nwrote o\n"; stderr = ""
        return R()
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    c = bridge.create_app().test_client()
    r = c.post("/generate", json={"meeting_id": "q1", "meetily_id": "m1", "template": "weekly_review"}).get_json()
    assert "# AI Minutes" in r["markdown"] and r["projects"] == ["P"]


def test_generate_invalid_template_400():
    c = bridge.create_app().test_client()
    r = c.post("/generate", json={"meeting_id": "q1", "meetily_id": "m1", "template": "../evil"})
    assert r.status_code == 400 and "invalid template" in r.get_json()["error"]


def test_generate_failure_500(monkeypatch):
    def fail_run(argv, **kw):
        class R: returncode = 1; stdout = ""; stderr = "No transcript found."
        return R()
    monkeypatch.setattr(bridge.subprocess, "run", fail_run)
    c = bridge.create_app().test_client()
    r = c.post("/generate", json={"meeting_id": "q1", "meetily_id": "m1"})
    assert r.status_code == 500 and "No transcript" in r.get_json()["error"]


def test_generate_audio_argv():
    a = bridge._generate_audio_argv("py", "review.py", "/t/a.webm", "q1", "weekly_review", "/t/o.md")
    assert a == ["py", "review.py", "/t/a.webm", "--meeting", "q1",
                 "-t", str(bridge.REPO_ROOT / "weekly_review.json"), "-o", "/t/o.md"]
    b = bridge._generate_audio_argv("py", "review.py", "/t/a.webm", "q1", None, "/t/o.md")
    assert b == ["py", "review.py", "/t/a.webm", "--meeting", "q1", "-o", "/t/o.md"]


def test_safe_audio_suffix():
    assert bridge._safe_audio_suffix("meeting.m4a") == ".m4a"
    assert bridge._safe_audio_suffix("clip.MP3") == ".mp3"
    assert bridge._safe_audio_suffix("blob") == ".webm"           # no ext -> default
    assert bridge._safe_audio_suffix("../evil.exe") == ".webm"    # non-audio -> default (never .exe)


def test_generate_audio_missing_fields_400():
    c = bridge.create_app().test_client()
    # no audio file
    r = c.post("/generate-audio", data={"meeting_id": "q1"}, content_type="multipart/form-data")
    assert r.status_code == 400
    # no meeting_id
    r = c.post("/generate-audio",
               data={"audio": (io.BytesIO(b"AUDIO"), "a.webm")}, content_type="multipart/form-data")
    assert r.status_code == 400


def test_generate_audio_success(monkeypatch):
    def fake_run(argv, **kw):
        Path(argv[argv.index("-o") + 1]).write_text("# Minutes\nbody")
        class R: returncode = 0; stdout = "projects (1): P\n"; stderr = ""
        return R()
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    c = bridge.create_app().test_client()
    r = c.post("/generate-audio",
               data={"meeting_id": "q1", "template": "weekly_review",
                     "audio": (io.BytesIO(b"AUDIO"), "rec.webm")},
               content_type="multipart/form-data").get_json()
    assert "# Minutes" in r["markdown"] and r["projects"] == ["P"]


def test_generate_audio_failure_500(monkeypatch):
    def fail_run(argv, **kw):
        class R: returncode = 1; stdout = ""; stderr = "no audio track"
        return R()
    monkeypatch.setattr(bridge.subprocess, "run", fail_run)
    c = bridge.create_app().test_client()
    r = c.post("/generate-audio",
               data={"meeting_id": "q1", "audio": (io.BytesIO(b"x"), "a.webm")},
               content_type="multipart/form-data")
    assert r.status_code == 500 and "no audio" in r.get_json()["error"]


def test_generate_audio_preflight():
    c = bridge.create_app().test_client()
    r = c.open("/generate-audio", method="OPTIONS")
    assert r.status_code in (200, 204) and r.headers["Access-Control-Allow-Origin"]
