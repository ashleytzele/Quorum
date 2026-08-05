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
