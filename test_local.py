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
