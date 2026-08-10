# Phase 8 — Unified template pool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Widen `review.py`'s template source to the union of our repo templates + the Meetily app's bundled and user template folders, so every template (ours + the app's 7) syncs into MeeTeam's dropdown and can drive generation. MeeTeam and the other modules are untouched.

**Architecture:** A small template-source layer in `review.py`: the repo folder (gated by the existing `registry:true` marker) plus the Meetily app folders (env-overridable, every valid `name`+`sections` JSON, no marker), deduped by stem with repo > user > bundled precedence. `--sync-templates`, the auto-sync on generate, and `resolve_template` all read this union.

**Tech Stack:** Python 3, `pytest`, the existing `review.py`. No new dependency, no schema change, no MeeTeam edit.

## Global Constraints

- meetily repo only (`/Users/leleditit/Desktop/Ospit/meetily`). Tests: `./.venv/bin/python -m pytest` (the repo-local `.venv` has pytest + deps; `/tmp/rvenv` is gone/ephemeral).
- Do NOT modify `quorum.py`, `meetily_app.py`, `local/`, or MeeTeam. Read-only on the Meetily app's files.
- Template sources, in precedence order: (1) repo dir — include only `registry:true` files (unchanged Phase-3 rule); (2) app **user** dir; (3) app **bundled** dir — from the app dirs include every valid `name`+`sections` JSON (no marker). Dedupe by stem, first source wins.
- App dirs are env-overridable and OPTIONAL: `MEETILY_APP_TEMPLATES` (bundled, default `/Applications/meetily.app/Contents/Resources/templates`), `MEETILY_APP_USER_TEMPLATES` (default `~/Library/Application Support/meetily/templates`). A dir that doesn't exist contributes nothing — never an error.
- Phases 1–7 behavior and tests stay green. `_read_template_meta`'s default (marker required) is preserved for its existing direct callers/tests.

---

### Task 1: Union template sources across repo + Meetily app folders

**Files:**
- Modify: `review.py`
- Modify: `test_review.py`

**Interfaces:**
- Produces:
  - `_app_template_dirs() -> list[Path]` — existing Meetily app template dirs (user, then bundled), from env/defaults.
  - `all_templates(script_dir) -> list[dict]` — union `[{stem,name,description}]`, deduped by stem (repo > user > bundled).
  - `_find_template_path(stem, script_dir) -> Path | None` — first `<stem>.json` across repo dir + app dirs.
- Changed: `_read_template_meta(paths, requires_marker=True)` — gains the flag; app dirs pass `False`.
- Changed: `resolve_template`, `--sync-templates` mode, and the auto-sync on generate use the union.

- [ ] **Step 1: Write the failing tests**

Add to `test_review.py`:

```python
def _write_tpl(p, name, marker=False, extra=None):
    import json as _json
    d = {"name": name, "description": name.lower(), "sections": [{"title": "X", "instruction": "i", "format": "string"}]}
    if marker:
        d["registry"] = True
    if extra:
        d.update(extra)
    p.write_text(_json.dumps(d))


def test_all_templates_unions_repo_and_app(tmp_path, monkeypatch):
    import review
    repo = tmp_path / "repo"; user = tmp_path / "user"; bundled = tmp_path / "bundled"
    for d in (repo, user, bundled): d.mkdir()
    _write_tpl(repo / "weekly_review.json", "Weekly Review", marker=True)
    _write_tpl(repo / "cruft.json", "Cruft No Marker", marker=False)          # repo: dropped (no marker)
    _write_tpl(user / "weekly_progress_review.json", "Weekly Progress Review")  # app user: kept
    _write_tpl(bundled / "daily_standup.json", "Daily Standup")                 # app bundled: kept
    (bundled / "notjson.json").write_text("{ broken")                           # skipped
    monkeypatch.setenv("MEETILY_APP_USER_TEMPLATES", str(user))
    monkeypatch.setenv("MEETILY_APP_TEMPLATES", str(bundled))
    stems = sorted(r["stem"] for r in review.all_templates(repo))
    assert stems == ["daily_standup", "weekly_progress_review", "weekly_review"]  # cruft & broken excluded


def test_all_templates_dedupe_repo_wins(tmp_path, monkeypatch):
    import review
    repo = tmp_path / "repo"; bundled = tmp_path / "bundled"
    repo.mkdir(); bundled.mkdir()
    _write_tpl(repo / "shared.json", "Repo Shared", marker=True)
    _write_tpl(bundled / "shared.json", "Bundled Shared")
    monkeypatch.setenv("MEETILY_APP_TEMPLATES", str(bundled))
    monkeypatch.setenv("MEETILY_APP_USER_TEMPLATES", str(tmp_path / "nope"))   # missing dir -> skipped
    rows = [r for r in review.all_templates(repo) if r["stem"] == "shared"]
    assert len(rows) == 1 and rows[0]["name"] == "Repo Shared"                  # repo wins


def test_resolve_template_finds_app_stem(tmp_path, monkeypatch):
    import review
    repo = tmp_path / "repo"; bundled = tmp_path / "bundled"
    repo.mkdir(); bundled.mkdir()
    _write_tpl(bundled / "retrospective.json", "Retrospective (Agile)")
    monkeypatch.setenv("MEETILY_APP_TEMPLATES", str(bundled))
    monkeypatch.setenv("MEETILY_APP_USER_TEMPLATES", str(tmp_path / "nope"))
    assert review.resolve_template(None, "retrospective", repo) == str(bundled / "retrospective.json")
    with pytest.raises(SystemExit):
        review.resolve_template(None, "does_not_exist", repo)
```

Update the existing Phase-1 `test_sync_templates_mode_reads_local_and_calls_quorum` so the app dirs don't pollute its exact-rows assertion — add at the top of that test (after `import review`):

```python
    monkeypatch.setenv("MEETILY_APP_TEMPLATES", str(tmp_path / "no-bundled"))
    monkeypatch.setenv("MEETILY_APP_USER_TEMPLATES", str(tmp_path / "no-user"))
```
(both nonexistent → app sources empty → the test still sees only its stubbed repo template). It already takes `tmp_path` and `monkeypatch`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest test_review.py -k "all_templates or resolve_template_finds_app or sync_templates_mode" -v`
Expected: FAIL — `AttributeError: module 'review' has no attribute 'all_templates'` / `_app_template_dirs`.

- [ ] **Step 3: Implement the source layer in `review.py`**

Add near the template helpers (after `DEFAULT_TEMPLATE`, and import `os`/`Path` already present):

```python
DEFAULT_APP_TEMPLATES = Path("/Applications/meetily.app/Contents/Resources/templates")
DEFAULT_APP_USER_TEMPLATES = Path.home() / "Library" / "Application Support" / "meetily" / "templates"


def _app_template_dirs():
    """Meetily app template dirs (user first, then bundled), env-overridable; existing only."""
    user = Path(os.environ.get("MEETILY_APP_USER_TEMPLATES", DEFAULT_APP_USER_TEMPLATES))
    bundled = Path(os.environ.get("MEETILY_APP_TEMPLATES", DEFAULT_APP_TEMPLATES))
    return [d for d in (user, bundled) if d.is_dir()]
```

Change `_read_template_meta` to take the flag (keep the default so existing callers are unchanged):

```python
def _read_template_meta(paths, requires_marker=True):
    """Parse template JSON files -> [{stem, name, description}].
    From the repo (requires_marker=True) only files with a truthy "registry" key;
    from the app folders (requires_marker=False) every valid name+sections object."""
    rows = []
    for p in paths:
        p = Path(p)
        try:
            d = json.loads(p.read_text())
        except Exception as e:
            print(f"skip {p.name}: not valid JSON ({e})", file=sys.stderr)
            continue
        if not isinstance(d, dict):
            continue
        if requires_marker and not d.get("registry"):
            continue
        if not d.get("name") or "sections" not in d:
            if requires_marker:
                print(f"skip {p.name}: marked registry but missing name/sections", file=sys.stderr)
            continue
        rows.append({"stem": p.stem, "name": d["name"], "description": d.get("description") or ""})
    return rows
```

Add the union + finder (after `_read_template_meta`):

```python
def all_templates(script_dir):
    """Union of templates across sources, deduped by stem (repo > user > bundled)."""
    seen, out = set(), []
    repo_rows = _read_template_meta(_local_templates(script_dir), requires_marker=True)
    app_rows = []
    for d in _app_template_dirs():
        app_rows += _read_template_meta(sorted(d.glob("*.json")), requires_marker=False)
    for row in repo_rows + app_rows:
        if row["stem"] in seen:
            continue
        seen.add(row["stem"])
        out.append(row)
    return out


def _find_template_path(stem, script_dir):
    for d in [Path(script_dir), *_app_template_dirs()]:
        cand = d / f"{stem}.json"
        if cand.exists():
            return cand
    return None
```

- [ ] **Step 4: Point `resolve_template` and the sync paths at the union**

`resolve_template` (replace the `meeting_template` branch + error):

```python
def resolve_template(explicit, meeting_template, script_dir):
    """explicit -t > meeting's stem (found across repo + app dirs) > DEFAULT_TEMPLATE."""
    if explicit:
        return explicit
    if meeting_template:
        cand = _find_template_path(meeting_template, script_dir)
        if cand is None:
            avail = ", ".join(r["stem"] for r in all_templates(script_dir)) or "(none)"
            sys.exit(f"template '{meeting_template}' not found in any source. Available: {avail}")
        return str(cand)
    return str(Path(script_dir) / DEFAULT_TEMPLATE)
```

The `--sync-templates` mode (currently `rows = _read_template_meta(_local_templates(script_dir))`):

```python
        rows = all_templates(script_dir)
```

The auto-sync on generate (currently `_sync_templates_via_quorum(_read_template_meta(_local_templates(script_dir)))`):

```python
                _sync_templates_via_quorum(all_templates(script_dir))
```

- [ ] **Step 5: Run the new tests, then the whole suite**

Run: `./.venv/bin/python -m pytest test_review.py -k "all_templates or resolve_template or sync_templates" -v`
Expected: PASS.
Run: `./.venv/bin/python -m pytest test_review.py test_quorum.py test_meetily_app.py test_local.py test_bridge.py -q`
Expected: all pass (Phases 1–7 unaffected; the updated sync test still asserts its single repo row).

- [ ] **Step 6: Commit**

```bash
git add review.py test_review.py
git commit -m "feat: unified template pool — sync + resolve across repo (registry) + Meetily app bundled/user templates"
```

- [ ] **Step 7: Manual E2E (real app templates → real registry)**

```bash
set -a && . ./.env && set +a
./.venv/bin/python review.py --sync-templates          # should sync 9 (2 repo + 7 app)
./.venv/bin/python review.py --list-meetily >/dev/null # sanity: unrelated path still fine
```
Then confirm in Supabase (or MeeTeam's dropdown) that all 9 appear, and
`./.venv/bin/python review.py --meetily-app <id> --meeting <q> -t retrospective.json --dry-run`
resolves the app template (prints its sections in the prompt). Record the count synced.

---

## Self-Review

**Spec coverage:**
- Union of repo (`registry`) + app bundled + app user, deduped repo>user>bundled — Task 1 `all_templates`. ✓
- Marker gate only on the repo folder; app folders include all valid — `_read_template_meta(requires_marker=...)`. ✓
- App dirs env-overridable + optional/skipped if missing — `_app_template_dirs`. ✓
- `--sync-templates` + auto-sync upload the union → MeeTeam dropdown lists all — Task 1 Step 4. ✓
- `resolve_template` finds a stem from any source; unknown → error listing all stems — Task 1 Step 4. ✓
- No MeeTeam/quorum/meetily_app change; read-only on app files — no such edits. ✓
- Phases 1–7 green; existing `_read_template_meta` default preserved; the one exact-rows sync test updated to isolate app dirs — Task 1 Steps 1/5. ✓

**Placeholder scan:** No TBD/TODO. `<id>`/`<q>` are runtime values. Every step ships real code.

**Type consistency:** `all_templates(script_dir) -> [{stem,name,description}]` matches `_read_template_meta`'s row shape, the sync upload, and the `resolve_template` error listing. `_find_template_path(stem, script_dir) -> Path|None` feeds `resolve_template`. `_app_template_dirs() -> [Path]` is consumed by both `all_templates` and `_find_template_path`. `_read_template_meta(paths, requires_marker=True)` keeps its existing single-arg callers valid. ✓
