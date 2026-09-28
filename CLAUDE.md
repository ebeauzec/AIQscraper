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

## Session handoff -- 2026-09-28 (Windows dev station, v5.6.153 -> v5.6.155)

Continues the same multi-day stretch (v5.6.85 -> v5.6.153 -- rear-panel accuracy program, hardware-docs
harvester, Digital Advisor competitive-differentiation work, VMware Inventory section, trend redesign; see
git log / CHANGELOG.md for that range, don't re-derive). Everything below is pushed to `main`.

**Investigated, turned out NOT to be a bug:** user reported "i also see nothing listed when i click vmware
inventory" (the section added last session). Traced `generateActionPlan()` -> `_renderVMwareInventorySection()`
end to end, live. Root cause: the Action Planner's target-scope selector was set to a single system that
genuinely has `vcenters: []` -- the honest empty-state message was correct, not broken. Verified the feature
actually works against a real vCenter-bearing customer and the full 2,898-system fleet. No code change.

**v5.6.154, then found to be INCOMPLETE by the user in this same session -- read this before touching
`index.html`/`index_src.html` again:** user screenshotted the Capacity Breakdown by Node table (CSM tab) and
asked to make all its columns sortable. First pass added click-to-sort headers to `index.html` only, reusing
the existing `sortTamTable()`/`_sth()` mechanism, plus extended `sortTamTable()` (`app.js` ~27063) to pin any
row with a `tam-total-row` class at the bottom instead of sorting it like data (applied to
`renderNodeBreakdownTable()`'s TOTAL footer row). Verified "live" -- but the verification only ever called
`sortTamTable(th)` directly in the browser console, which works regardless of whether the onclick attribute
actually made it into the served page. It hadn't: **`server.py`'s `do_GET()` (~line 8294) rewrites every
request for `/` (and `/index.html`) to `/index_src.html`** -- a comment there explains this is deliberate, so
dev-mode edits take effect without recompiling. `index.html` is only the *compiled* artifact
`build/AIQscraper.spec` bundles into the packaged exe; it is never what `python server.py` actually serves.
User correctly reported "columns are not sortable" after v5.6.154 shipped, because the real served file was
never touched. **Lesson for next time:** on this codebase, a fix to `index.html` alone is not verified until
tested with a real `th.click()` (or equivalent DOM event) against `http://localhost:8080/` specifically --
calling the target function directly from the console proves the function works, not that the page wires it
up. And remember `index_src.html` is the file that matters for anything server.py serves at `/`.

**v5.6.155 (this fix, done right):** applied the identical sortable-header markup to `index_src.html`;
`index.html` kept in sync since the exe still bundles it. Re-verified with a genuine `th.click()` against the
live-served page (not a direct function call) -- sorts correctly on Used TB and Runway (mixed "> 10 Yrs" /
numeric text), TOTAL row stays pinned last in both directions. Also added the Customer column the user asked
for in the same message: `renderNodeBreakdownTable()` (`app.js` ~17490) now emits `s.customerName` in a new
`<td>` between Node/System and Model, sortable like every other column; both HTML files' TOTAL footer row
colspan widened 2 -> 3 to still span the three identity columns.

**Noted, not fixed -- possible pre-existing packaging gap, unconfirmed, out of scope for what was asked:**
`do_GET()`'s `/` -> `/index_src.html` rewrite is unconditional, but `build/AIQscraper.spec`'s `web_datas` only
bundles `index.html` into the packaged exe, not `index_src.html`. Whether the shipped .exe actually serves
correctly (falls back somehow) or has always 404'd on its own HTML was not checked this session -- worth a
quick look next time the exe itself (not `python server.py`) is being tested, since it predates this session's
changes and isn't something today's fix touched either way.

**Build/release housekeeping done this session:** `APP_VERSION`/`APP_CHANGELOG` bumped to 5.6.154 then
5.6.155 (`app.js` ~30), `version.json`, `CHANGELOG.md` updated for both. PyInstaller rebuilt twice, once per
version, to fresh temp dirs (`%LOCALAPPDATA%\Temp\aiqbuild5`, then `aiqbuild6` -- per standing rule below,
never `build/build_windows.bat`), exe + `_internal/base_library.zip` + `_internal/app.js` + `_internal/index.html`
+ top-level `dist/app.js` copied into the committed `dist/NetApp_AIQ_Advisor/` tree each time.

**Still open / not done:** rear-panel program still has no layout for FAS8000, older FAS25xx/26xx, unnamed
StorageGRID models, or cloud platforms. LEGAL.md/ARIA_FIX_PLAN.md still not content-audited. Only the
Capacity Breakdown by Node table is sortable -- the rest of `index.html`/`index_src.html`'s ~59 `<th>`
elements (and whatever app.js generates dynamically elsewhere) are still not, deferred by explicit user choice
last session, only in scope if asked again.

**Git:** branch `main`. v5.6.154 and v5.6.155 both committed and pushed. Working tree also shows harvest data
files modified by the running server (`data/*.json`) -- not part of this work, never commit those with code
changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart (kill the running
python process, relaunch) -- app.js is served fresh on every page load and needs neither. **New this
session:** `index.html` edits alone are NOT sufficient for anything the dev server serves at `/` -- always
mirror the change into `index_src.html` too (that's the file `do_GET()` actually serves), and verify with a
real DOM click/event, not a direct function call.
