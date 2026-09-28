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

## Session handoff -- 2026-09-28 (Windows dev station, v5.6.153 -> v5.6.158)

Continues the same multi-day stretch (v5.6.85 -> v5.6.153 -- rear-panel accuracy program, hardware-docs
harvester, Digital Advisor competitive-differentiation work, VMware Inventory section, trend redesign; see
git log / CHANGELOG.md for that range, don't re-derive). Everything below is pushed to `main`.

**v5.6.154 -> v5.6.155: sortable Capacity Breakdown table + Customer column.** Repeating the lesson because it
cost real time twice this stretch: v5.6.154's sort fix landed in `index.html` only, "verified" by calling
`sortTamTable(th)` directly from the console -- which proves the function works, not that the page wires it
up. **`server.py`'s `do_GET()` (~line 8294) rewrites every request for `/` to `/index_src.html`** so dev-mode
edits take effect without recompiling; `index.html` is only the compiled artifact `build/AIQscraper.spec`
bundles into the exe. v5.6.155 fixed it for real in `index_src.html` (kept `index.html` in sync) and
re-verified with an actual `th.click()`.

**v5.6.156: asked to "think more about further differentiating from AIQ Digital Advisor," then "do both" on
the two ideas offered.** Both lean on the multi-tenant fusion edge (`_merge_account_results()`, `server.py`
~1237) that earlier portfolio features only surfaced *inside* a single customer's deliverable:
1. **Portfolio Executive Dashboard** (`computePortfolioExecutiveDashboard()`/`_renderPortfolioExecutiveDashboard()`,
   right before `_renderVMwareInventorySection()`). New Action Planner section (tab/section index 22, Overview
   group) -- reads `state.systems` directly, ignores the scope selector, since the point is seeing every
   managed customer at once. KPI tiles, fleet-wide 30/60/90-day trend (`_dfTrendWindows(null)` -- confirmed
   `_get_fleet_trend()` already treats `customer_name=None` as fleet-wide), an urgency-ranked Accounts
   table, Shared CVE Exposure, Shared Refresh Opportunities. Gated on >=2 customers.
2. **Cross-customer CVE exposure** (`_dfCveIndex()` extended with a `customers` Set per CVE; new
   `_dfPortfolioCveExposure()`/`_dfPortfolioCveExposureText()`, after `_dfPortfolioBenchmark()`). No
   minimum-size gate -- even one other exposed customer is actionable. New "Portfolio Exposure" table in the
   Security Advisories section (data-section-index 3), plus text in the Security Posture Brief / MSP Report.

**v5.6.157: the four new tables from v5.6.156 sorted their own header row into the results** -- screenshot
showed the header dropping to the bottom mid-sort. Root cause: those four tables built their header as a
plain `<tr>` with no `<thead>`/`<tbody>` split, unlike every other sortable table in the app -- the browser's
implicit tbody caught the header row too, so `sortTamTable()`'s `table.querySelector('tbody')` sorted it
along with the data. Wrapped all four in explicit `<thead>`/`<tbody>`. **Rule reinforced again**: verify
sorting with a real `th.click()`, not a direct `sortTamTable(th)` call -- the latter can't catch a missing
`<thead>` since it only ever looks at whatever `querySelector('tbody')` finds, header row included.

**v5.6.158: asked "does it make sense to have the As-Built document downloadable as xlsx?", then "do it all."**
Scoped to the As-Built Configuration Document only (not the narrative deliverables -- QBR pack, briefs,
proposals -- which stay txt/md/docx, since reflowing prose into cells isn't more useful than the document).
New `_buildXlsx()`/`_xlsxSheetXml()`/`_colLetter()` (`app.js`, right after `_buildDocx()`): a from-scratch
minimal XLSX writer, same hand-rolled-OOXML-in-a-zip approach as the existing docx writer, reusing its
`_zipStored()`/`_xe()` helpers -- no library. New `downloadAsBuiltXlsx()` (right after) reads the exact same
fields the As-Built TXT export (`downloadPlanSection(19)`) already uses, reshaped into 4 sheets: Systems (one
row per system), Shelves, SVMs & LIFs, Risks (one row each of the latter three). New "📊 Export Excel" button
next to the As-Built section's existing Print/Download buttons.
**Caught and fixed a real bug before shipping**: first version of `_xlsxSheetXml()`'s column-width
calculation had a paren-counting mistake (9 open, 10 close on one line) that broke ALL of app.js -- caught via
`read_console_messages` showing a page-wide `Uncaught SyntaxError`, confirmed the exact line via a Python
`.count('(')`/`.count(')')` sweep (no `node` binary available in this Bash environment to just run `node -c`),
rewrote the expression as a small named-variable block instead of one deeply nested one-liner to make it
harder to miscount next time. Verified live after the fix: real 4-sheet zip (checked local file headers
byte-by-byte for the `PK\x03\x04` signature and file names), real cell data (system name, serial, customer,
cluster, model, site, ONTAP version) for a real customer scope.

**Build/release housekeeping done this session:** five versions shipped this stretch (`APP_VERSION`/
`APP_CHANGELOG` in `app.js`, `version.json`, `CHANGELOG.md`, bumped each time): 5.6.154, 5.6.155, 5.6.156,
5.6.157, 5.6.158. PyInstaller rebuilt to a fresh temp dir every time (`aiqbuild5` through `aiqbuild9` under
`%LOCALAPPDATA%\Temp` -- per standing rule below, never `build/build_windows.bat`), exe +
`_internal/base_library.zip` + `_internal/app.js` (+ `_internal/index.html` on the two versions that touched
it) + top-level `dist/app.js` copied into the committed `dist/NetApp_AIQ_Advisor/` tree each time.

**Still open / not done:** rear-panel program still has no layout for FAS8000, older FAS25xx/26xx, unnamed
StorageGRID models, or cloud platforms. LEGAL.md/ARIA_FIX_PLAN.md still not content-audited. Only the
Capacity Breakdown by Node table (CSM tab) is sortable among `index.html`/`index_src.html`'s other `<th>`
elements -- out of scope unless asked again. The Portfolio Dashboard's urgency-score weighting
(critical*10/high*3/openCases*5/eosSoon*4) is hand-picked, not validated against real TAM triage priorities.
Whether the packaged `.exe` itself serves correctly given `do_GET()`'s unconditional `index_src.html` rewrite
(not bundled into the exe per `AIQscraper.spec`) is still unconfirmed, flagged two sessions running now.

**Git:** branch `main`. v5.6.154 through v5.6.158 all committed and pushed individually. Working tree also
shows harvest data files modified by the running server (`data/*.json`) -- not part of this work, never
commit those with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart -- app.js is
served fresh on every page load and needs neither. **HTML changes must land in both `index.html` and
`index_src.html`** -- `do_GET()` serves `index_src.html` at `/` in dev mode; `index.html` is only what the
packaged exe bundles. **Verify UI wiring with a real DOM event** (`.click()`, not calling the handler function
directly) -- calling the function proves the logic works, not that the page actually wires it up, and can't
catch a missing `<thead>`/`<tbody>` split either. **No `node` binary in this Bash environment** -- can't run
`node -c file.js` to syntax-check; a `new Function(text)` eval against the fetched file in the browser
console works as a substitute, or a Python paren/brace/bracket-count sweep to narrow down a bad line.
