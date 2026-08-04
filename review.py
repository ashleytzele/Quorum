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


def build_prompt(template: dict, transcript: str, notes: str) -> list[dict]:
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
    system = "\n".join(sys_parts)

    user_parts = []
    if notes.strip():
        user_parts.append(
            "=== GROUND TRUTH: pre-meeting notes "
            "(trust these over the transcript on any conflict) ===")
        user_parts.append(notes.strip())
        user_parts.append("")
    user_parts.append("=== TRANSCRIPT (cite line numbers, e.g. (lines 12-18)) ===")
    user_parts.append(number_lines(transcript))
    user = "\n".join(user_parts)

    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


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


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Recording + notes -> markdown review.")
    ap.add_argument("recording", help="audio file or Meetily recording folder")
    ap.add_argument("notes", nargs="*", help="pre-meeting .docx/.pptx/.pdf files")
    ap.add_argument("-t", "--template",
                    default=str(Path(__file__).resolve().parent / DEFAULT_TEMPLATE))
    ap.add_argument("--clean", action="store_true", help="denoise before transcribing")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the prompt and stop; no OpenAI call")
    ap.add_argument("-o", "--out", help="output .md path")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args(argv)

    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set. export it, or put it in a .env you source.")

    template = json.loads(Path(args.template).read_text())
    transcript = transcribe(args.recording, args.clean)
    notes = read_notes(args.notes)
    messages = build_prompt(template, transcript, notes)

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
