import os
import pytest
from quorum import _combine_inputs, _client, publish_minutes


def test_combine_inputs_merges_with_headers():
    out = _combine_inputs(
        pre_notes=[("WCE", "did the thing"), ("MSAR", "  ")],   # blank one dropped
        file_texts=[("log.pdf", "file body")],
        links=[("dashboard", "https://x.test")],
    )
    assert "--- WCE (pre-meeting note) ---" in out
    assert "did the thing" in out
    assert "MSAR" not in out                      # empty pre_note omitted
    assert "--- log.pdf ---" in out and "file body" in out
    assert "--- link: dashboard ---" in out and "https://x.test" in out


def test_combine_inputs_empty_is_empty_string():
    assert _combine_inputs([], [], []) == ""


def test_client_requires_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(SystemExit):
        _client()


def test_publish_refuses_empty_markdown():
    with pytest.raises(SystemExit):
        publish_minutes("some-id", "   ")


def test_sync_templates_empty_is_noop_without_network():
    from quorum import sync_templates
    assert sync_templates([]) == []      # returns early, never builds a client


def test_set_meeting_status_builds_update(monkeypatch):
    import quorum
    captured = {}
    class FakeExec:
        def __init__(self, data): self.data = data
    class FakeTable:
        def update(self, payload): captured["payload"] = payload; return self
        def eq(self, col, val): captured["eq"] = (col, val); return self
        def execute(self): return FakeExec([{"id": captured["eq"][1], "status": captured["payload"]["status"]}])
    class FakeClient:
        def table(self, name): captured["table"] = name; return FakeTable()
    monkeypatch.setattr(quorum, "_client", lambda: FakeClient())
    out = quorum.set_meeting_status("MID-1", "processing")
    assert captured["table"] == "meetings"
    assert captured["payload"] == {"status": "processing"}
    assert captured["eq"] == ("id", "MID-1")
    assert out == [{"id": "MID-1", "status": "processing"}]


def test_publish_minutes_sets_published_status(monkeypatch):
    import quorum
    captured = {}
    class FakeExec:
        def __init__(self, data): self.data = data
    class FakeTable:
        def update(self, payload): captured["payload"] = payload; return self
        def eq(self, col, val): return self
        def execute(self): return FakeExec([{"id": "MID-1"}])
    class FakeClient:
        def table(self, name): return FakeTable()
    monkeypatch.setattr(quorum, "_client", lambda: FakeClient())
    quorum.publish_minutes("MID-1", "# Minutes")
    assert captured["payload"]["status"] == "published"
    assert captured["payload"]["is_active"] is False
    assert captured["payload"]["minutes_final"] == "# Minutes"
