#!/usr/bin/env python3
"""Recording + notes -> structured review (weekly or interview) via local
whisper + the OpenAI API. See docs/superpowers/specs for the design."""

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

MODEL = "gpt-4o-mini"  # "the mini" — confirm exact id from OpenAI dashboard
DEFAULT_TEMPLATE = "weekly_review.json"


def number_lines(text: str) -> str:
    return "\n".join(f"{i}: {ln}" for i, ln in enumerate(text.splitlines(), 1))


def _user_content(transcript: str, notes: str) -> str:
    parts = []
    if notes.strip():
        parts.append(
            "=== GROUND TRUTH: pre-meeting notes "
            "(trust these over the transcript on any conflict) ===")
        parts.append(notes.strip())
        parts.append("")
    parts.append("=== TRANSCRIPT (cite line numbers, e.g. (lines 12-18)) ===")
    parts.append(number_lines(transcript))
    return "\n".join(parts)


def build_prompt(template: dict, transcript: str, notes: str,
                 projects: list[str] | None = None) -> list[dict]:
    sys_parts = [
        template["description"],
        "",
        "Produce these sections in order, following each instruction exactly. "
        "Output GitHub-flavored markdown. Use each section's title as a heading.",
    ]
    for s in template["sections"]:
        sys_parts.append(f"\n## {s['title']}  (format: {s['format']})")
        sys_parts.append(s["instruction"])
        if s.get("item_format"):
            sys_parts.append(f"Row/item format:\n{s['item_format']}")
    if projects:
        sys_parts.append(
            "\nREQUIRED PROJECTS — output exactly one '### ' subsection for EACH "
            "item below. Do NOT merge two of them together and do NOT drop any, "
            "even if their wording overlaps (e.g. one project's 'node' vs "
            "another's 'nodes'):")
        sys_parts.extend(f"- {p}" for p in projects)
    system = "\n".join(sys_parts)

    return [{"role": "system", "content": system},
            {"role": "user", "content": _user_content(transcript, notes)}]


def list_projects(enumerate_instruction: str, transcript: str, notes: str,
                  model: str) -> list[str]:
    """First pass: ask the model only to enumerate the distinct projects, so the
    second pass can't quietly merge or drop one."""
    system = (enumerate_instruction +
              "\nRespond with ONLY the list, one item per line — no numbering, "
              "no blank lines, no commentary.")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": _user_content(transcript, notes)}]
    text = call_openai(messages, model)
    return [ln.strip(" -*\t") for ln in text.splitlines() if ln.strip()]


def read_notes(paths: list[str]) -> str:
    if not paths:
        return ""
    from markitdown import MarkItDown
    md = MarkItDown()
    chunks = []
    for p in paths:
        chunks.append(f"--- {Path(p).name} ---")
        chunks.append(md.convert(p).text_content.strip())
    return "\n\n".join(chunks)


def needs_transcribe(audio: Path, transcript: Path) -> bool:
    if not transcript.exists():
        return True
    if not audio.exists():
        return False
    return transcript.stat().st_mtime < audio.stat().st_mtime


def _audio_path(recording: str) -> Path:
    rec = Path(recording)
    return (rec / "audio.mp4") if rec.is_dir() else rec


def transcribe(recording: str, clean: bool) -> str:
    audio = _audio_path(recording)
    transcript = audio.parent / (audio.stem + ".manglish.txt")
    if needs_transcribe(audio, transcript):
        script = Path(__file__).resolve().parent / "retranscribe.sh"
        cmd = [str(script)] + (["--clean"] if clean else []) + [str(recording)]
        subprocess.run(cmd, check=True)
    return transcript.read_text()


def call_openai(messages: list[dict], model: str) -> str:
    from openai import OpenAI
    client = OpenAI()  # reads OPENAI_API_KEY from env
    resp = client.chat.completions.create(model=model, messages=messages)
    return resp.choices[0].message.content


def _date_from(recording: str) -> str:
    audio = _audio_path(recording)
    target = audio if audio.exists() else Path(recording)
    return datetime.date.fromtimestamp(target.stat().st_mtime).isoformat()


def _fetch_via_quorum(meeting_id: str) -> str:
    import quorum
    return quorum.fetch_notes(meeting_id)


def _publish_via_quorum(meeting_id: str, markdown: str) -> None:
    import quorum
    quorum.publish_minutes(meeting_id, markdown)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Recording + notes -> markdown review.")
    ap.add_argument("recording", nargs="?",
                    help="audio/recording folder (generate), or the review .md (with --publish)")
    ap.add_argument("notes", nargs="*", help="pre-meeting .docx/.pptx/.pdf files")
    ap.add_argument("-t", "--template",
                    default=str(Path(__file__).resolve().parent / DEFAULT_TEMPLATE))
    ap.add_argument("--clean", action="store_true", help="denoise before transcribing")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the prompt and stop; no OpenAI call")
    ap.add_argument("-o", "--out", help="output .md path")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--meeting", metavar="ID",
                    help="Quorum meeting id: pull its pre-meeting notes as ground truth")
    ap.add_argument("--publish", metavar="MEETING_ID",
                    help="publish the given review .md to this meeting's minutes and archive it")
    args = ap.parse_args(argv)

    if args.publish:
        if not args.recording:
            sys.exit("--publish needs the review .md file as the positional argument.")
        text = Path(args.recording).read_text()
        _publish_via_quorum(args.publish, text)
        print(f"published {args.recording} -> meeting {args.publish} (archived)")
        return

    if not args.recording:
        sys.exit("a recording (audio file or folder) is required.")

    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set. export it, or put it in a .env you source.")

    template = json.loads(Path(args.template).read_text())
    notes = read_notes(args.notes)
    if args.meeting:
        qnotes = _fetch_via_quorum(args.meeting)
        notes = (qnotes + "\n\n" + notes).strip() if notes.strip() else qnotes
    transcript = transcribe(args.recording, args.clean)

    # Two-pass: if the template asks to enumerate first (weekly review does,
    # interviews don't), list the projects, then require one section per project.
    projects = None
    if template.get("enumerate") and not args.dry_run:
        projects = list_projects(template["enumerate"], transcript, notes, args.model)
        print(f"projects ({len(projects)}): {', '.join(projects)}")

    messages = build_prompt(template, transcript, notes, projects)

    if args.dry_run:
        for m in messages:
            print(f"\n===== {m['role'].upper()} =====\n{m['content']}")
        return

    result = call_openai(messages, args.model)
    stem = Path(args.template).stem
    out = args.out or f"{stem}_{_date_from(args.recording)}.md"
    Path(out).write_text(result)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
