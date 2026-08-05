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


def test_combine_inputs_includes_during_notes():
    from quorum import _combine_inputs
    out = _combine_inputs(
        pre_notes=[("WCE", "pre stuff")],
        file_texts=[],
        links=[],
        during_notes=[("WCE", "live decision: ship Friday"), ("MSAR", "  ")],
    )
    assert "--- WCE (pre-meeting note) ---" in out and "pre stuff" in out
    assert "--- WCE (during-meeting note) ---" in out and "live decision: ship Friday" in out
    assert "MSAR" not in out          # blank during-note dropped
    # during-note for a team appears after that team's pre-note block
    assert out.index("(pre-meeting note)") < out.index("(during-meeting note)")


def test_combine_inputs_backward_compatible_without_during():
    from quorum import _combine_inputs
    out = _combine_inputs(pre_notes=[("WCE", "x")], file_texts=[], links=[])
    assert "--- WCE (pre-meeting note) ---" in out and "during-meeting" not in out


def test_fetch_notes_empty_warns_and_returns_blank(monkeypatch, capsys):
    import quorum
    class FakeExec:
        def __init__(self, data): self.data = data
    class FakeTable:
        def select(self, *a): return self
        def eq(self, *a): return self
        def execute(self): return FakeExec([])          # no notes, no submissions
    class FakeClient:
        def table(self, name): return FakeTable()
    monkeypatch.setattr(quorum, "_client", lambda: FakeClient())
    result = quorum.fetch_notes("MID-empty")             # must NOT raise SystemExit
    assert result == ""
    assert "no notes" in capsys.readouterr().err.lower()


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
