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

## Session handoff -- 2026-09-28 (Windows dev station, v5.6.153 -> v5.6.154)

Continues the same multi-day stretch (v5.6.85 -> v5.6.153 -- rear-panel accuracy program, hardware-docs
harvester, Digital Advisor competitive-differentiation work, VMware Inventory section, trend redesign; see
git log / CHANGELOG.md for that range, don't re-derive). Everything below is pushed to `main`.

**Investigated, turned out NOT to be a bug:** user reported "i also see nothing listed when i click vmware
inventory" (the section added last session). Traced `generateActionPlan()` (`app.js` ~30013) ->
`_renderVMwareInventorySection(targetSystems)` (~28330) end to end, live. Root cause: the Action Planner's
target-scope selector (`planTargetSelect`) was set to a single system (serial `952250002843`), which
genuinely has `vcenters: []` -- the section's honest empty-state message was correct, not broken. Verified
the feature actually works: scoped to a customer with real vCenter systems (Breede Valley Municipality) and
to the full "ALL" scope (2,898 systems), the table renders real vCenter names/versions/customers and a real
IMT compatibility finding both times. Also incidentally confirmed `generateActionPlan()` takes ~25s for the
full 2,898-system fleet (all 21 sections build correctly, just slow) -- not a hang, just heavy; a couple of
my own live checks mid-run looked like a stuck/partial DOM because I queried before the synchronous call
finished, not because anything was actually broken. No code change came out of this -- false alarm, closed.

**Shipped, v5.6.154:** user screenshotted the Capacity Breakdown by Node table (CSM tab, Per-Node capacity
view) and said "make all columns always sortable." Asked to confirm scope (this one table vs. every table
app-wide, since `index.html` alone has 59 `<th>` elements and none were sortable) -- user confirmed just this
table. Added click-to-sort on all 8 columns (`index.html` ~627-634) by reusing the existing
`sortTamTable()`/`_sth()` mechanism (`app.js` ~27063/~27115) already used across the Action Planner's other
tables, rather than writing a second sort implementation. One real wrinkle: `renderNodeBreakdownTable()`
(`app.js` ~17430) appends a TOTAL summary row into the same `<tbody>` as the data rows -- naively reusing
`sortTamTable()` would have sorted that row into the middle of the table like a data row. Fixed by extending
`sortTamTable()` itself to recognize a `tam-total-row` class and always pin matching rows at the bottom
(sorted separately, re-appended after every other row, in both directions) -- applied that class to the
footer row. Verified live against the real 2,898-system fleet: ascending Used TB sorts correctly (0.0 ->
1917.0), descending too, TOTAL row stays last both times; Runway (mixed "> 10 Yrs" text and numeric "2.8 Yrs"
/ "121 days" values) sorts without throwing, same pinning holds.

**Also shipped, v5.6.154:** finished the still-uncommitted work from the end of the *previous* session --
removing all display numbers from the Action Planner's 21 tab buttons/section headings (`app.js`, the
`switchPlanTab`/tab-header block ~31355-31411 and each `secN` block). That fix had only been verified live
against the dev server before this session started; nothing new was done to it here beyond confirming it
still renders correctly, then shipping it in this version.

**Build/release housekeeping done this session:** `APP_VERSION`/`APP_CHANGELOG` bumped to 5.6.154 (`app.js`
~30), `version.json`, `CHANGELOG.md` updated. PyInstaller rebuilt to a fresh temp dir
(`%LOCALAPPDATA%\Temp\aiqbuild5`, per standing rule below -- never `build/build_windows.bat`), exe +
`_internal/base_library.zip` + `_internal/app.js` + `_internal/index.html` + top-level `dist/app.js` all
copied into the committed `dist/NetApp_AIQ_Advisor/` tree.

**Still open / not done:** rear-panel program still has no layout for FAS8000, older FAS25xx/26xx, unnamed
StorageGRID models, or cloud platforms. LEGAL.md/ARIA_FIX_PLAN.md still not content-audited
(ARIA_FIX_PLAN.md looks obsolete, worth archiving). The other 58 `<th>` elements across `index.html` (and
whatever else app.js generates dynamically) are still not sortable -- explicitly deferred this session, only
in scope if asked.

**Git:** branch `main`. This session's changes (index.html, app.js, version.json, CHANGELOG.md, CLAUDE.md,
dist/) committed and pushed together as the v5.6.154 release. Working tree also shows harvest data files
modified by the running server (`data/*.json`) -- not part of this work, never commit those with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart (kill the running
python process, relaunch) -- app.js is served fresh on every page load and needs neither.
