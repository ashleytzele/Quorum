import json
from review import number_lines, build_prompt


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
