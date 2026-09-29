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

## Session handoff -- 2026-09-28/29 (Windows dev station, v5.6.153 -> v5.6.162 + docs pass)

Continues the same multi-day stretch (v5.6.85 -> v5.6.153 -- rear-panel accuracy program, hardware-docs
harvester, Digital Advisor competitive work; see git log / CHANGELOG.md for that range, don't re-derive).
This handoff covers v5.6.153 through v5.6.162 (all shipped/pushed individually, see CHANGELOG.md for the
version-by-version detail) plus a docs-only pass at the end. Highlights, not a full re-derivation:

- **v5.6.154/155**: sortable Capacity Breakdown table + Customer column. Real lesson: a fix landed in
  `index.html` alone is never live -- `server.py`'s `do_GET()` serves `index_src.html` at `/` in dev mode;
  `index.html` is only what the packaged exe bundles. Both files need every HTML change.
- **v5.6.156/157**: Portfolio Dashboard (`computePortfolioExecutiveDashboard()`/`_renderPortfolioExecutiveDashboard()`,
  Action Planner tab/section 22) and cross-customer CVE exposure (`_dfCveIndex()`'s `customers` Set,
  `_dfPortfolioCveExposure()`) -- both genuine differentiators built on the multi-tenant fusion edge, since a
  single-tenant dashboard structurally can't produce either. v5.6.157 fixed the 4 new tables sorting their own
  header into the data (missing `<thead>`/`<tbody>`).
- **v5.6.158-161**: As-Built Excel export (`_buildXlsx()` etc., next to `_buildDocx()`), shipped broken three
  times in a row -- repair prompt (missing `styles.xml` relationship), invisible white-on-nothing headers
  (non-standard fill-index layout), then blank risk titles/contract dates/firmware (all three read fields --
  `r.title`, `sys.contracts.hwEndDate/swEndDate`, `sys.firmware.*` -- that never existed, copied in from the
  pre-existing As-Built TXT generator which had carried the same bugs undetected for years since it was
  write-only). Every one of these was caught by the user actually opening the file, not by anything I verified
  beforehand until partway through.
- **v5.6.160**: Deliverables Suite split into 3 tabs (Risk & Remediation A-C, Customer & Sales D-I, TAM/MSP
  J-O) along its own pre-existing category dividers, per explicit user-specified category names. New
  `_DELIVERABLE_CATEGORIES` map also fixed `downloadAllDeliverables()`, which was silently missing 2 of 15
  real deliverables.
- **v5.6.162**: TAM Success & Posture Optimization Plan made genuinely executable -- removed a "+N more"
  truncation on affected-system lists, named actual systems in ACTION 3.2 (Capacity) and ACTION 4.3 (ARP)
  instead of counts/percentages. Checked and confirmed Active IQ's GraphQL schema has no per-volume
  identifiers at all (only per-system/cluster counts) -- named the system, the deepest real identifier that
  exists, nothing fabricated deeper. Separately confirmed the *other* Success Plans feature
  (`SUCCESS_PLAN_TEMPLATES`, real Active IQ write-back via Adopt) already named systems correctly from an
  earlier session's fix -- not the same bug.

**Documentation + screenshots pass (this session's tail, docs-only commit `fd565da`)**: asked to focus on
docs and differentiators, then to refresh screenshots with more examples and obfuscate customer details.
- `README.md`: version badge/line-count/template-count refreshed; the "Action Planner -- All 19 Sections"
  table was fully stale (actually 24 sections, still numbered 1-19 in the doc despite numbers being removed
  from the real UI entirely in a prior session) -- rewrote it grouped by the real 5 tab groups, no numbers.
  Fixed every stale "Tab N" cross-reference across the use-case walkthroughs (there were ~10). Added Portfolio
  Dashboard and cross-customer CVE exposure rows to the Digital Advisor comparison table. Documented the
  As-Built Excel export.
- `CONTEXT.md`: updated edge #1 (multi-tenant fusion) to point at the now-shipped Portfolio
  Dashboard/CVE-exposure features; added a full addendum for the v5.6.153-162 range.
- **New screenshots -- one real mistake worth remembering**: first attempt used a *fresh* Playwright browser
  context (no shared session with the interactive browser tool) to set demo mode and screenshot the Action
  Planner. It silently captured **real fleet data** (2,898 systems, not demo's 152) because a fresh page load
  kicks off `server.py`'s own real background sync/cache-restore before the demo-mode script finishes running,
  and that real data wins the race. Caught before anything was committed (checked the systems count in the
  saved PNG), deleted immediately. Fixed by adding `page.route("**/api/**", route => route.abort())` before
  `page.goto()` -- demo mode loads from a static local JSON file, not an `/api/` endpoint, so blocking real API
  calls entirely starves the real sync without breaking demo mode. Re-verified every subsequent screenshot's
  system count in Python (`state.systems.length === 152`) before treating it as safe to embed.
  **Rule for next time**: never screenshot this app from a browser session that hasn't had its API calls
  blocked or demo mode explicitly re-applied and re-verified immediately before the shot -- a real customer
  fleet is the default state the app loads into, not an opt-in.

**Build/release housekeeping done this session:** nine versions shipped (`APP_VERSION`/`APP_CHANGELOG` in
`app.js`, `version.json`, `CHANGELOG.md`, bumped every time): 5.6.154 through 5.6.162. PyInstaller rebuilt to
a fresh temp dir every time (`aiqbuild5` through `aiqbuild13` under `%LOCALAPPDATA%\Temp` -- per standing rule
below, never `build/build_windows.bat`), exe + `_internal/base_library.zip` + `_internal/app.js` (+
`_internal/index.html` on the versions that touched it) + top-level `dist/app.js` copied into `dist/` each time.

**Still open / not done:** rear-panel program still has no layout for FAS8000, older FAS25xx/26xx, unnamed
StorageGRID models, or cloud platforms. LEGAL.md/ARIA_FIX_PLAN.md still not content-audited. Only the
Capacity Breakdown by Node table (CSM tab) is sortable among `index.html`/`index_src.html`'s other `<th>`
elements. The Portfolio Dashboard's urgency-score weighting is hand-picked, not validated against real TAM
triage priorities. Whether the packaged `.exe` itself serves correctly given `do_GET()`'s unconditional
`index_src.html` rewrite (not bundled into the exe per `AIQscraper.spec`) is still unconfirmed -- flagged
four sessions running now, genuinely worth just checking directly next time. Only 4 of the ~65+ static
`<th>` elements across `index.html`/`index_src.html` got new screenshots refreshed this pass; the older
screenshots (`dashboard-overview.png`, `value-insights.png`, `remediation-tracker.png`, `cabling-audit.png`,
rear-panel images) were spot-checked for real-data leaks (none found, all already safely anonymized/redacted)
but not retaken -- fine as-is unless the features they show have changed.

**Git:** branch `main`. v5.6.154 through v5.6.162, plus the docs-only commit `fd565da`, all committed and
pushed individually. Working tree also shows harvest data files modified by the running server
(`data/*.json`) -- not part of this work, never commit those with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart -- app.js is
served fresh on every page load and needs neither. **HTML changes must land in both `index.html` and
`index_src.html`.** **Verify UI wiring with a real DOM event**, never a direct function call. **Any hand-rolled
OOXML (docx/xlsx) change must be validated by reproducing the file structure in Python and loading it with
`python-docx`/`openpyxl`** (installed via pip, not present by default) **before calling it verified.**
**Any screenshot of this app for documentation must block `/api/**` (or otherwise force demo mode) and verify
the resulting system count before saving** -- the app's default loaded state is the real fleet, not demo data.
