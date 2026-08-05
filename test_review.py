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
