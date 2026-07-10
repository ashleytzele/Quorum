# Per-file captions in pre-meeting attachments + Present

**Date:** 2026-07-09
**Status:** approved (design), implementing

## Problem
In Present, each team's pre-meeting note is one slide and every attached file is its own separate slide. When a note describes a specific picture, the note and the picture land on different slides — it reads disjointed. Users want a note attached *to a specific file* so they present together.

## Decision
Add an optional **per-file caption** (chosen over auto-pairing or a section+caption model). Each attachment carries its own short note; in Present the caption shows on the same slide as the file. The team's overall pre-meeting note is unchanged.

## Data
Add one nullable column to `submissions`:
```sql
alter table public.submissions add column if not exists caption text;
```
Non-breaking, reversible. Existing rows get `caption = null`. Both team.html and present.html already `select('*')`, so the column flows through with no query change.

## Authoring — team.html
- Each file row (`.file-item`, incl. links) gains an inline caption input: placeholder "Add a note for this file…", prefilled from `f.caption`.
- Autosaves debounced (~600ms) via `supa.from('submissions').update({ caption }).eq('id', f.id)`. Silent (low-stakes); errors go to `console.error` + a friendly toast.
- `.file-item` restructures from a single flex row to a column: a `.file-main` row (icon + name + remove) above the caption input.

## Present — present.html
For each included file, render its caption with the content:
- **Image + caption → adaptive**: on image load, compare `naturalWidth`/`naturalHeight`; landscape → side-by-side (`.capslide.wide`: image left, caption right), portrait/square → stacked (image on top, caption below).
- **PDF / Office / HTML embed** → caption as a header line above the full-screen embed (if present).
- **Link** → caption as the note, link beneath.
- **No caption** → renders exactly as today (no regression).

## Bonus fix (same code path)
Audit P2 regression: `classifyFile` routes `.key/.odt/.rtf` to the Office Online viewer, which only renders Word/PowerPoint/Excel → broken embed. Fix: only `ppt/pptx/doc/docx/xls/xlsx` → `'office'`; `key/odt/rtf` → link fallback.

## Verification
- `lib.test.js`: office set = ppt/pptx/doc/docx/xls(x); key/odt/rtf → `'other'`.
- Render the adaptive image+caption slide (landscape → side-by-side, portrait → stacked) via a headless Chrome harness with the real styles.
- Render a team file row with a caption input.
- Migration applied to Supabase before the caption save path is exercised.
