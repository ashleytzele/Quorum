# Meeting Minutes App — SDD Progress

Plan: docs/superpowers/plans/2026-07-03-meeting-minutes-app.md
Branch: feat/meeting-minutes-app

- Tasks 1–4 (lib.js + tests): complete (commit 119f9a89, review clean — Spec ✅, Quality Approved)
  - Minor (deferred): splitSlides won't split when `---` is the first/last line (inherited from plan). Revisit only if real slides start/end with a separator.
- Tasks 5–8 (index.html, style.css, app.js): complete (commit 517d30b, Spec ✅). 3 Important findings fixed in commit a128965 (escape names, init reveal while visible, re-entrancy guard), verified by controller.
  - Minor (won't fix): object-URL not revoked (must stay live to display; freed on page close); unawaited initialize() promise (harmless).

- Final whole-branch review: READY TO MERGE (commit 4bac765). One Important finding (notes wiped on folder re-pick) fixed in 4bac765.

## Status: COMPLETE — all tasks done, 4/4 tests pass, branch feat/meeting-minutes-app not pushed.

## Remaining
- Human browser smoke test with sample-team/ folder (not committed; gitignored)

---

# Meeting Models — SDD Progress

Plan: docs/superpowers/plans/2026-07-06-meeting-models.md
Branch: feat/meeting-models

- Task 1 (DB: model column + admin-write RLS on notes/submissions + hide-VIP read policy): complete
  (migration `meeting_models` applied; verified via SQL + CDP: admin authors note/sub on behalf OK,
   admin sees VIP OK, 10 existing meetings backfilled to model='team'). No repo files changed.
- Task 2 (storage: admin-writes-submission-objects policy): complete
  (migration applied; existing write/delete were team-scoped with no admin exception. Verified via CDP:
   admin upload+delete into R&D team folder (non-own) OK). No repo files changed.
- Task 3+4 (admin.html: model dropdown + persist + VIP/Hybrid tab badge; drawer "Edit this team" for
  admin/hybrid): complete. Implemented by subagent (commits 784f6cb, bbfff6e), CDP-verified by controller:
  set hybrid -> DB model=hybrid, badge "Hybrid" shows, edit button flex(hybrid)/none(team), no exceptions.
  CONCERN (flagged): nothing was committed earlier this session, so 784f6cb also swept in prior uncommitted
  session work (multi-meeting tabs, links, etc.). Cache-version skew: styles.css ?v=3 on admin/index/dev-login/route,
  ?v=2 on team/present/minutes/history. Reconcile at end (uniform bump + commit remaining working-tree work).
  Per-task commit review consolidated into final whole-branch review (commit boundaries not clean).
