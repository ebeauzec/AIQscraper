# Notes for Claude Code sessions on this repo

This file is read automatically by Claude Code at the start of every
session in this repo, on any machine. Its job is to carry context between
sessions/machines (this project is worked on both from a Claude Code
cloud session and from a Windows dev station) — treat it as a handoff
note, not user-facing documentation. See `CONTEXT.md` for the full
architecture/feature writeup and `CHANGELOG.md` / the in-app
`APP_CHANGELOG` (`app.js` near the top) for the release history.

## Standing instruction: maintain this handoff note

**This is default behavior for every session on this repo, not a one-off.**
Before ending a session (or handing off to another machine/session), replace
the "Session handoff" section below with a fresh one summarizing that
session's work: what was asked, what was found/changed (with file/line
references where useful), what's fixed vs. still open, and current git
state (branch, whether it's merged/pushed, whether a PR is open). Keep it
to one section — overwrite the previous handoff rather than appending, so
this file stays a short "where things stand now" note rather than a growing
log; the full history already lives in git log and CHANGELOG.md. Commit and
push it (to `main` when the work itself was pushed to `main`) as part of
wrapping up the session, the same way you'd commit code.

## Session handoff — 2026-09-26 (cloud session, v5.6.83 → v5.6.84)

**Correction to the previous handoff:** it assumed the next session would
be on the user's Windows station. It wasn't — "closing this session" and
"picking up on this system" both turned out to still be the same Linux
cloud container (`/home/user/AIQscraper`, hostname `vm`). **This
environment cannot compile the Windows `.exe`** (PyInstaller doesn't
cross-compile, and the Windows path needs `pywin32`/`pythonnet`, which
don't exist on Linux) — that genuinely requires an actual Windows
machine running `build/build_windows.bat`. If a session ever needs to
know which machine it's actually on, check `hostname`/`uname -a` and
`pwd` rather than trusting what the user calls it — this cost one
clarifying round-trip. Everything below is real, done, and pushed.

### v5.6.83 (previous handoff, now superseded) — deliverable-consistency fixes

Fixed two real bugs in the Action Planner deliverables (`app.js`'s
`compile*` functions): (1) `compileCustomerSuccessPlanText` and
`compileMSPServiceReport` averaged a dead field, `sys.projections.
runwayDays` (never set anywhere — real field is `daysToLimit`), always
printing a fake 120-day capacity runway; (2) QBR Pack, MSP Service
Report, and Risk & Remediation Brief computed the storage efficiency
ratio across all platforms instead of ONTAP-only, disagreeing with CSP/
Extended Deliverables on mixed-platform fleets. Both fixed; full detail
in `git log` on commit `10e3ff1` and `CHANGELOG.md` [5.6.83]. Not
re-summarized further here per the "overwrite, don't append" rule above.

### v5.6.84 — merged a 3-week-old unmerged branch, completed its wiring

The user asked to pull in "changes done on the mac." No new commits had
been pushed anywhere since the last handoff — but `git ls-remote --heads
origin` turned up two branches that were never in this conversation's
context: `ebeauzec-remove-claude-contributor` (already fully merged into
`main`, an ancestor — harmless, could be deleted, didn't bother) and
**`ebeauzec-add-kb-interval-config`** (NOT merged, 3 real commits, authored
by the user directly, dated early September — this was almost certainly
the "mac" work). **Lesson: when a user says work exists elsewhere and a
fetch of the branch you're on shows nothing new, check `git ls-remote
--heads origin` for branches outside the current conversation's memory
before concluding there's nothing to pull in.**

Merged it (`f67e8b5`): adds a "KB Crawl Interval" dropdown in Settings >
Enrichment (24h-14d, default 7 days) alongside the existing Security Scan
Interval. Conflicts in `README.md`, `app.js`, `server.py` resolved by
combining both sides (this branch's kb-interval wiring +
since-added `autoHarvestEnabled`/`autoHarvestInterval` wiring that didn't
exist when the branch was cut) — `index_src.html` merged cleanly.

**Found and fixed while merging:** the original branch only wired
`GET /api/config` to return `kb_interval_hours` — saving the dropdown did
nothing, silently. Completed it: `POST /api/config` now persists
`kb_interval_hours` from the request body, `_enrichment_scheduler.
update_config()` is now called with it on every save (not just at
startup), and the scheduler's initial construction at server startup now
reads the saved value instead of always defaulting to 168h. All 54 tests
in `tests/run_tests.py` pass; `node --check app.js` and
`python3 -m py_compile server.py` both clean.

**Note:** `index.html` (production) has no enrichment-settings section
at all (only `index_src.html`, the dev shell, does) — this is a
pre-existing, documented gap (see `CONTEXT.md` §"index.html vs
index_src.html"), not something this merge introduced or needed to fix.

### `dist/` sync — same pattern as last time, still no `.exe` rebuild

Only `app.js` changed among the files `dist/` ships (`server.py` isn't
bundled into the frozen app at all — `launcher.py` has its own smaller,
self-contained proxy and doesn't implement `/api/config`, background
schedulers, etc., so the kb-interval backend fix only applies to
`python server.py` mode, not the packaged desktop app; `index_src.html`
isn't bundled either — `dist/` only ships `index.html`). Copied the
updated `app.js` into `dist/app.js` and
`dist/NetApp_AIQ_Advisor/_internal/app.js` as before. Still true: only a
`launcher.py`/native-code change would require an actual Windows rebuild.

### Git state as of hand-off

- `main` and `claude/gallant-lovelace-zlrhei` both at `f67e8b5`... then
  the changelog/version-bump/dist-sync commit on top for v5.6.84 — check
  `git log --oneline -5` on `main` for the exact current tip, push both
  branches together (fast-forward `main` from this branch) as usual.
  Clean working tree, no open PR.
- Stray fully-merged branch `ebeauzec-remove-claude-contributor` still
  exists on GitHub (harmless, safe to delete whenever, not urgent).
