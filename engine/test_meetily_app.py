import sqlite3
import pytest
from pathlib import Path
import meetily_app


def _mkdb(path):
    c = sqlite3.connect(path)
    c.executescript("""
        create table meetings (id text primary key, title text, created_at text, folder_path text);
        create table transcript_chunks (meeting_id text primary key, transcript_text text);
        create table transcripts (id text primary key, meeting_id text, transcript text,
                                  speaker text, audio_start_time real);
    """)
    c.execute("insert into meetings values ('m1','Alpha','2026-07-24T10:00:00Z','/rec/a')")
    c.execute("insert into meetings values ('m2','Beta','2026-07-25T10:00:00Z','/rec/b')")
    c.execute("insert into transcript_chunks values ('m1','[00:01] full chunk transcript')")
    # m2 has no chunk — must fall back to assembling from transcripts (out of order)
    c.execute("insert into transcripts values ('t2','m2','second line','Bob',2.0)")
    c.execute("insert into transcripts values ('t1','m2','first line','',1.0)")
    c.commit(); c.close()


def test_assemble_from_chunks_pure():
    out = meetily_app._assemble_from_chunks([("", "hi"), ("Bob", "there"), ("", "  ")])
    assert out == "hi\nBob: there"


def test_get_transcript_prefers_chunk(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    assert meetily_app.get_transcript("m1", db) == "[00:01] full chunk transcript"


def test_get_transcript_falls_back_ordered(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    # ordered by audio_start_time: first line (blank speaker), then Bob's second line
    assert meetily_app.get_transcript("m2", db) == "first line\nBob: second line"


def test_get_transcript_unknown_exits(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    with pytest.raises(SystemExit):
        meetily_app.get_transcript("nope", db)


def test_list_meetings_newest_first(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    ids = [m["id"] for m in meetily_app.list_meetings(db)]
    assert ids == ["m2", "m1"]


def test_db_path_env_and_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MEETILY_APP_DB", str(tmp_path / "nope.sqlite"))
    with pytest.raises(SystemExit):
        meetily_app._db_path()


def test_connection_is_readonly(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    conn = meetily_app._connect(db)
    with pytest.raises(sqlite3.OperationalError):   # read-only rejects writes
        conn.execute("insert into meetings values ('x','X','now','/x')")
    conn.close()
