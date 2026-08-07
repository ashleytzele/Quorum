import json
import os
import pytest
from pathlib import Path
from review import number_lines, build_prompt, read_notes, needs_transcribe, main


def test_number_lines():
    assert number_lines("hello\nworld") == "1: hello\n2: world"


def test_build_prompt_includes_sections_notes_and_numbered_transcript():
    template = {
        "name": "T",
        "description": "DESC-TEXT",
        "sections": [
            {"title": "Alpha", "instruction": "do alpha", "format": "string"},
            {"title": "Beta", "instruction": "do beta", "format": "list",
             "item_format": "| A | B |"},
        ],
    }
    msgs = build_prompt(template, "hello\nworld", "NOTE ONE")
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert "DESC-TEXT" in system
    assert "Alpha" in system and "Beta" in system
    assert "do alpha" in system and "do beta" in system
    assert "| A | B |" in system            # item_format carried through
    assert "GROUND TRUTH" in user and "NOTE ONE" in user
    assert "1: hello" in user and "2: world" in user


def test_build_prompt_omits_notes_block_when_empty():
    template = {"name": "T", "description": "D",
                "sections": [{"title": "X", "instruction": "i", "format": "string"}]}
    user = build_prompt(template, "line one", "")[1]["content"]
    assert "GROUND TRUTH" not in user
    assert "1: line one" in user


def test_build_prompt_injects_required_projects():
    template = {"name": "T", "description": "D",
                "sections": [{"title": "X", "instruction": "i", "format": "string"}]}
    system = build_prompt(template, "t", "", projects=["Alpha", "Beta [?]"])[0]["content"]
    assert "REQUIRED PROJECTS" in system
    assert "- Alpha" in system and "- Beta [?]" in system


def test_build_prompt_no_required_block_without_projects():
    template = {"name": "T", "description": "D",
                "sections": [{"title": "X", "instruction": "i", "format": "string"}]}
    system = build_prompt(template, "t", "")[0]["content"]
    assert "REQUIRED PROJECTS" not in system


def test_read_notes_empty_returns_empty_string():
    assert read_notes([]) == ""


def test_needs_transcribe(tmp_path):
    audio = tmp_path / "a.m4a"
    audio.write_text("x")
    transcript = tmp_path / "a.manglish.txt"

    # transcript missing -> must transcribe
    assert needs_transcribe(audio, transcript) is True

    # transcript newer than audio -> skip
    transcript.write_text("y")
    newer = audio.stat().st_mtime + 10
    os.utime(transcript, (newer, newer))
    assert needs_transcribe(audio, transcript) is False

    # transcript older than audio -> must transcribe
    older = audio.stat().st_mtime - 10
    os.utime(transcript, (older, older))
    assert needs_transcribe(audio, transcript) is True

    # audio gone, transcript present -> trust transcript, skip
    audio.unlink()
    assert needs_transcribe(audio, transcript) is False


def test_dry_run_prints_prompt_without_api_key(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    template = tmp_path / "t.json"
    template.write_text(json.dumps({
        "name": "T", "description": "D",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    audio = tmp_path / "a.m4a"
    audio.write_text("x")
    transcript = tmp_path / "a.manglish.txt"
    transcript.write_text("hello world")
    newer = audio.stat().st_mtime + 10
    os.utime(transcript, (newer, newer))   # fresh -> transcribe() won't shell out

    main([str(audio), "-t", str(template), "--dry-run"])

    out = capsys.readouterr().out
    assert "SYSTEM" in out
    assert "1: hello world" in out          # line-numbered transcript in the prompt


def test_publish_mode_pushes_file(tmp_path, monkeypatch):
    import review
    md = tmp_path / "r.md"
    md.write_text("# Minutes\nbody")
    called = {}
    monkeypatch.setattr(review, "_publish_via_quorum",
                        lambda mid, text: called.update(mid=mid, text=text))
    review.main([str(md), "--publish", "MID-1"])
    assert called == {"mid": "MID-1", "text": "# Minutes\nbody"}


def test_publish_mode_requires_a_file(monkeypatch):
    import review
    monkeypatch.setattr(review, "_publish_via_quorum", lambda mid, text: None)
    with pytest.raises(SystemExit):
        review.main(["--publish", "MID-1"])      # no .md positional


def test_meeting_mode_merges_quorum_notes(tmp_path, capsys, monkeypatch):
    import review
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(review, "_fetch_via_quorum", lambda mid: "QUORUM-NOTE")
    template = tmp_path / "t.json"
    template.write_text(json.dumps({"name": "T", "description": "D",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    audio = tmp_path / "a.m4a"
    audio.write_text("x")
    transcript = tmp_path / "a.manglish.txt"
    transcript.write_text("hello world")
    newer = audio.stat().st_mtime + 10
    os.utime(transcript, (newer, newer))

    review.main([str(audio), "-t", str(template), "--meeting", "MID-1", "--dry-run"])
    out = capsys.readouterr().out
    assert "QUORUM-NOTE" in out and "GROUND TRUTH" in out


def test_resolve_template_precedence(tmp_path):
    import review
    (tmp_path / "weekly_review.json").write_text("{}")
    (tmp_path / "interview_review.json").write_text("{}")
    # explicit -t wins
    assert review.resolve_template("/x/custom.json", "interview_review", tmp_path) == "/x/custom.json"
    # else the meeting's stem
    assert review.resolve_template(None, "interview_review", tmp_path) == str(tmp_path / "interview_review.json")
    # else the default
    assert review.resolve_template(None, None, tmp_path) == str(tmp_path / "weekly_review.json")


def test_resolve_template_unknown_stem_exits(tmp_path):
    import review
    (tmp_path / "weekly_review.json").write_text("{}")
    with pytest.raises(SystemExit):
        review.resolve_template(None, "nope", tmp_path)


def test_meeting_mode_uses_meeting_template(tmp_path, capsys, monkeypatch):
    import review
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(review, "_fetch_via_quorum", lambda mid: "QNOTE")
    monkeypatch.setattr(review, "_meeting_template_via_quorum", lambda mid: "interview_review")
    audio = tmp_path / "a.m4a"; audio.write_text("x")
    transcript = tmp_path / "a.manglish.txt"; transcript.write_text("hi")
    newer = audio.stat().st_mtime + 10; os.utime(transcript, (newer, newer))
    # no -t: the interview template (real file in the repo) must be selected
    review.main([str(audio), "--meeting", "MID-1", "--dry-run"])
    out = capsys.readouterr().out
    assert "Interview" in out          # interview_review.json's section titles reach the prompt


def test_read_template_meta_keeps_templates_skips_others(tmp_path, capsys):
    import review
    (tmp_path / "weekly_review.json").write_text(json.dumps(
        {"name": "Weekly Review v2", "description": "by project", "registry": True,
         "sections": [{"title": "X"}]}))
    (tmp_path / "notatemplate.json").write_text(json.dumps({"foo": 1}))       # no name+sections
    (tmp_path / "broken.json").write_text("{ not json")
    (tmp_path / "array.json").write_text(json.dumps([1, 2, 3]))              # non-object JSON
    (tmp_path / "unmarked.json").write_text(json.dumps(
        {"name": "Cruft", "description": "d", "sections": [{"title": "Y"}]}))  # no registry marker
    rows = review._read_template_meta(sorted(tmp_path.glob("*.json")))
    assert rows == [{"stem": "weekly_review", "name": "Weekly Review v2",
                     "description": "by project"}]


def test_meeting_generate_writes_processing_then_draft(tmp_path, capsys, monkeypatch):
    import review
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(review, "_fetch_via_quorum", lambda mid: "QNOTE")
    monkeypatch.setattr(review, "_meeting_template_via_quorum", lambda mid: None)
    monkeypatch.setattr(review, "_sync_templates_via_quorum", lambda rows: rows)
    calls = []
    monkeypatch.setattr(review, "_set_status_via_quorum", lambda mid, s: calls.append((mid, s)))
    monkeypatch.setattr(review, "transcribe", lambda rec, clean: "hello transcript")
    monkeypatch.setattr(review, "call_openai", lambda messages, model: "# Minutes\nbody")
    audio = tmp_path / "a.m4a"; audio.write_text("x")
    template = tmp_path / "weekly_review.json"
    template.write_text(json.dumps({"name": "T", "description": "d",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    out = tmp_path / "o.md"
    review.main([str(audio), "-t", str(template), "--meeting", "MID-1", "-o", str(out)])
    assert calls == [("MID-1", "processing"), ("MID-1", "draft")]


def test_status_write_failure_does_not_abort_generate(tmp_path, monkeypatch):
    import review
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(review, "_fetch_via_quorum", lambda mid: "QNOTE")
    monkeypatch.setattr(review, "_meeting_template_via_quorum", lambda mid: None)
    monkeypatch.setattr(review, "_sync_templates_via_quorum", lambda rows: rows)
    def boom(mid, s): raise RuntimeError("supabase down")
    monkeypatch.setattr(review, "_set_status_via_quorum", boom)
    monkeypatch.setattr(review, "transcribe", lambda rec, clean: "hi")
    monkeypatch.setattr(review, "call_openai", lambda messages, model: "# M")
    audio = tmp_path / "a.m4a"; audio.write_text("x")
    template = tmp_path / "weekly_review.json"
    template.write_text(json.dumps({"name": "T", "description": "d",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    out = tmp_path / "o.md"
    review.main([str(audio), "-t", str(template), "--meeting", "MID-1", "-o", str(out)])
    assert out.read_text() == "# M"      # generate completed despite status failures


def test_sync_templates_mode_reads_local_and_calls_quorum(tmp_path, monkeypatch, capsys):
    import review
    sent = {}
    monkeypatch.setattr(review, "_local_templates",
                        lambda d: sorted(tmp_path.glob("*.json")))
    (tmp_path / "interview_review.json").write_text(json.dumps(
        {"name": "Interview Record", "description": "neutral", "registry": True,
         "sections": [{"title": "Y"}]}))
    monkeypatch.setattr(review, "_sync_templates_via_quorum",
                        lambda rows: sent.setdefault("rows", rows) or rows)
    review.main(["--sync-templates"])
    assert sent["rows"] == [{"stem": "interview_review", "name": "Interview Record",
                             "description": "neutral"}]
    assert "synced 1" in capsys.readouterr().out


def test_list_meetily_prints_and_returns(capsys, monkeypatch):
    import review
    monkeypatch.setattr(review, "_list_meetily_meetings",
                        lambda: [{"id": "m2", "title": "Beta", "created_at": "2026-07-25T10:00:00Z"},
                                 {"id": "m1", "title": "Alpha", "created_at": "2026-07-24T10:00:00Z"}])
    review.main(["--list-meetily"])
    out = capsys.readouterr().out
    assert "m2" in out and "2026-07-25" in out and "Beta" in out


def test_meetily_app_uses_transcript_without_recording(tmp_path, capsys, monkeypatch):
    import review
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(review, "_transcript_via_meetily_app", lambda mid: "APP TRANSCRIPT TEXT")
    def no_transcribe(*a, **k):
        raise AssertionError("transcribe must not be called in --meetily-app mode")
    monkeypatch.setattr(review, "transcribe", no_transcribe)
    template = tmp_path / "weekly_review.json"
    template.write_text(json.dumps({"name": "T", "description": "d",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    # no recording positional, dry-run to skip OpenAI
    review.main(["--meetily-app", "m1", "-t", str(template), "--dry-run"])
    out = capsys.readouterr().out
    assert "APP TRANSCRIPT TEXT" in out


def test_recording_or_meetily_app_required(monkeypatch):
    import review
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        review.main(["--dry-run"])      # neither a recording nor --meetily-app
