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
- Task 5 (team.html: admin edits any team via ?meeting=&team=; effectiveTeamId + banner + tab suppression):
  complete (controller-implemented; caught+fixed a sed over-replacement of the effectiveTeamId definition).
  CDP-verified: admin edits R&D (non-own) -> banner "Editing as R&D · admin", team-name=R&D, no tabs,
  pre-note saved to R&D. Uniform styles.css?v=4. Commit 8556326.
- Task 6 (regression + visibility): normal member path renders tabs + no banner (CDP OK). VIP-hidden
  enforced by read-meetings policy qual = (model<>'admin' OR is_admin()). DB restored: all 10 meetings model='team'.
- Commits on branch feat/meeting-models: 784f6cb, bbfff6e, 8556326, ff3668f. Working tree clean.

- Final whole-branch review (opus): 1 Critical + 3 Minor. Critical = stored XSS via unescaped link url
  in href (admin drawer/history/present); member->admin through the normal link UI. FIXED commit 4dfcabc
  (esc(url) at all 3 render sites + team.html esc now escapes "). CDP-verified: payload inert, no attr
  injection, no script exec. Minor #2 (team.html esc missing ") fixed same commit. Minor #3 (model badge/
  edit-btn reflect page-load model; needs reload) and #4 (single-threaded dev server) accepted as documented.

## Status: meeting-models tasks 1-6 COMPLETE + reviewed + XSS fixed. Branch feat/meeting-models: 5 commits.
## FOLLOW-UP (new user requirement) — admin-run (VIP) single inline workspace: COMPLETE (commit 85270c4).
   - admin.html: model='admin' -> hide Teams card, embed team.html?embed=1 (iframe, postMessage auto-height),
     keep Present/Export. team.html: embed mode strips chrome + banner, posts height. Content stored under
     admin's own team slot (no schema change). present.html + minutes.html: VIP branch drops team badges/
     headings, renders single content.
   - CDP-verified: teams hidden + workspace embedded; in-frame edit saves to VIP slot; present='Meeting
     content' no badges; minutes no 'Team updates'; embed mode hides topbar/grid-head/banner; non-VIP
     present/minutes regress clean. DB restored (cleaned __CDP_EMB__; left user's real 'New meeting').
   - Cache: styles.css?v=5 uniform across pages.

## Status: meeting-models (tasks 1-6) + XSS fix + admin-run VIP workspace all COMPLETE & CDP-verified.
## Branch feat/meeting-models: 6 commits, working tree clean. Ready for finishing-a-development-branch.
