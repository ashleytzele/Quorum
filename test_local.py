import json
from pathlib import Path
import pytest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "local"))
import serve


def test_safe_name_accepts_and_rejects():
    assert serve._safe_name("weekly_review-2") == "weekly_review-2"
    for bad in ["../etc", "a/b", "a b", "a.b", ""]:
        with pytest.raises(ValueError):
            serve._safe_name(bad)


def test_slugify():
    assert serve._slugify("Weekly Review 31/6") == "weekly-review-31-6"


def test_create_and_list_meeting(tmp_path):
    m = serve._create_meeting(tmp_path, "Team Sync", "weekly_review")
    assert m["title"] == "Team Sync" and m["template"] == "weekly_review"
    d = tmp_path / m["id"]
    assert (d / "meta.json").exists() and (d / "notes").is_dir()
    # collision → distinct id
    m2 = serve._create_meeting(tmp_path, "Team Sync", "weekly_review")
    assert m2["id"] != m["id"]
    listed = serve._list_meetings(tmp_path)
    assert {x["id"] for x in listed} == {m["id"], m2["id"]}
    assert all(x["status"] == "ready" for x in listed)   # no recording yet


def test_meeting_status_progression(tmp_path):
    m = serve._create_meeting(tmp_path, "S", "weekly_review")
    d = tmp_path / m["id"]
    assert serve._meeting_status(d) == "ready"
    (d / "recording.m4a").write_bytes(b"x")
    assert serve._meeting_status(d) == "recorded"
    (d / "minutes.md").write_text("# M")
    assert serve._meeting_status(d) == "done"


def test_list_templates_filters(tmp_path):
    (tmp_path / "weekly_review.json").write_text(json.dumps(
        {"name": "Weekly Review v2", "description": "by project", "sections": [{"title": "X"}]}))
    (tmp_path / "notatemplate.json").write_text(json.dumps({"foo": 1}))
    out = serve._list_templates(tmp_path)
    assert out == [{"stem": "weekly_review", "name": "Weekly Review v2", "description": "by project"}]


def test_api_create_get_and_save_note(tmp_path):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    r = c.post("/api/meetings", json={"title": "Demo", "template": "weekly_review"})
    mid = r.get_json()["id"]
    c.put(f"/api/meetings/{mid}/notes/DataProject", json={"content": "# DataProject\nshipped"})
    got = c.get(f"/api/meetings/{mid}").get_json()
    assert got["notes"] == [{"name": "DataProject", "content": "# DataProject\nshipped"}]
    assert got["minutes"] == ""


def test_api_note_path_traversal_rejected(tmp_path):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "D", "template": "weekly_review"}).get_json()["id"]
    assert c.put(f"/api/meetings/{mid}/notes/..%2fevil", json={"content": "x"}).status_code == 400


SAMPLE_DEVICES = """[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] Aggregate Device
[AVFoundation indev @ 0x1] [1] MacBook Air Microphone
[AVFoundation indev @ 0x1] [2] VB-Cable
"""

def test_resolve_device_index():
    assert serve._resolve_device_index(SAMPLE_DEVICES, "Aggregate Device") == "0"
    assert serve._resolve_device_index(SAMPLE_DEVICES, "VB-Cable") == "2"
    assert serve._resolve_device_index(SAMPLE_DEVICES, "Nope") is None


def test_record_status_and_single_recording(tmp_path, monkeypatch):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "R", "template": "weekly_review"}).get_json()["id"]
    assert c.get("/api/record/status").get_json() == {"recording": False, "meeting_id": None}

    class FakeProc:
        def __init__(self): self.signals = []
        def poll(self): return None
        def send_signal(self, s): self.signals.append(s)
        def wait(self, timeout=None): return 0
    fake = FakeProc()
    monkeypatch.setattr(serve, "_spawn_ffmpeg", lambda idx, out: fake)
    monkeypatch.setattr(serve, "_resolve_device_index", lambda blob, name: "0")
    monkeypatch.setattr(serve, "_list_audio", lambda: SAMPLE_DEVICES)

    assert c.post(f"/api/meetings/{mid}/record/start").status_code == 200
    assert c.get("/api/record/status").get_json()["recording"] is True
    # second start refused while one is active
    assert c.post(f"/api/meetings/{mid}/record/start").status_code == 409
    # stop finalizes (write a non-empty file to simulate ffmpeg output)
    (tmp_path / mid / "recording.m4a").write_bytes(b"AUDIO")
    assert c.post(f"/api/meetings/{mid}/record/stop").status_code == 200
    assert c.get("/api/record/status").get_json()["recording"] is False


def test_record_stop_checks_recording_meetings_folder_not_url_mid(tmp_path, monkeypatch):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid_a = c.post("/api/meetings", json={"title": "A", "template": "weekly_review"}).get_json()["id"]
    mid_b = c.post("/api/meetings", json={"title": "B", "template": "weekly_review"}).get_json()["id"]

    class FakeProc:
        def poll(self): return None
        def send_signal(self, s): pass
        def wait(self, timeout=None): return 0
    monkeypatch.setattr(serve, "_spawn_ffmpeg", lambda idx, out: FakeProc())
    monkeypatch.setattr(serve, "_resolve_device_index", lambda blob, name: "0")
    monkeypatch.setattr(serve, "_list_audio", lambda: SAMPLE_DEVICES)

    # start recording meeting A
    assert c.post(f"/api/meetings/{mid_a}/record/start").status_code == 200
    # only A's folder gets a real recording; B's folder has nothing
    (tmp_path / mid_a / "recording.m4a").write_bytes(b"AUDIO")
    # stop is called with B's id in the URL — must still validate A's (the recording's) folder
    assert c.post(f"/api/meetings/{mid_b}/record/stop").status_code == 200
    assert c.get("/api/record/status").get_json() == {"recording": False, "meeting_id": None}
    assert not (tmp_path / mid_b / "recording.m4a").exists()


def test_generate_argv_sorted_notes():
    argv = serve._generate_argv("py", "review.py", "rec.m4a",
                                ["notes/b.md", "notes/a.md"], "weekly_review.json", "out.md")
    assert argv == ["py", "review.py", "rec.m4a", "notes/a.md", "notes/b.md",
                    "-t", "weekly_review.json", "-o", "out.md"]


def test_parse_projects():
    assert serve._parse_projects("projects (3): A, B, C\nwrote out.md\n") == ["A", "B", "C"]
    assert serve._parse_projects("wrote out.md\n") == []


def test_generate_requires_recording(tmp_path):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "G", "template": "weekly_review"}).get_json()["id"]
    assert c.post(f"/api/meetings/{mid}/generate").status_code == 400   # no recording yet


def test_generate_runs_review_and_returns_minutes(tmp_path, monkeypatch):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "G", "template": "weekly_review"}).get_json()["id"]
    d = tmp_path / mid
    (d / "recording.m4a").write_bytes(b"AUDIO")
    (d / "notes" / "P.md").write_text("# P")
    def fake_run(argv, **kw):
        Path(argv[argv.index("-o") + 1]).write_text("# Minutes\nbody")   # simulate review.py writing -o
        class R: returncode = 0; stdout = "projects (1): P\nwrote out\n"; stderr = ""
        return R()
    monkeypatch.setattr(serve.subprocess, "run", fake_run)
    r = c.post(f"/api/meetings/{mid}/generate").get_json()
    assert r["projects"] == ["P"] and "# Minutes" in r["minutes"]
    # edit + save
    c.put(f"/api/meetings/{mid}/minutes", json={"content": "# Edited"})
    assert c.get(f"/api/meetings/{mid}").get_json()["minutes"] == "# Edited"


def test_generate_failure_keeps_old_minutes(tmp_path, monkeypatch):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "G", "template": "weekly_review"}).get_json()["id"]
    d = tmp_path / mid
    (d / "recording.m4a").write_bytes(b"A")
    (d / "minutes.md").write_text("# Old")
    def fail_run(argv, **kw):
        class R: returncode = 1; stdout = ""; stderr = "OPENAI_API_KEY not set."
        return R()
    monkeypatch.setattr(serve.subprocess, "run", fail_run)
    r = c.post(f"/api/meetings/{mid}/generate")
    assert r.status_code == 500 and "OPENAI_API_KEY" in r.get_json()["error"]
    assert (d / "minutes.md").read_text() == "# Old"     # not overwritten
