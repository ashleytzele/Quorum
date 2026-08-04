#!/usr/bin/env python3
"""Recording + notes -> structured review (weekly or interview) via local
whisper + the OpenAI API. See docs/superpowers/specs for the design."""

from pathlib import Path


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
