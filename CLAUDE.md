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

## Session handoff -- 2026-09-30 (Windows dev station, v5.6.191 -> v5.6.192)

Single-thread session: user gave a screenshot of the Security Advisories report (flat "Sa-Id: CVE-... -
SYSTEMNAME" entries, no structure) and asked to reformat it grouped by system, drop the Sa-Id label, and
under each system list CVE/Title/Mitigation/Status. That escalated in three follow-up messages to: group
tasks/actions by system in **all** other deliverables, then "scan all of the downloadable, formatted
documents, and fix the logic and legibility in the same way."

**What shipped (v5.6.192):** every place in the codebase that rendered a flat, un-grouped list of
risks/cases/security-advisories/switch-firmware-findings now groups them under a `SYSTEM: <name>` header, one
system at a time, before moving to the next system. Concretely, in `app.js`:
- `downloadPlanSection()` (the quick per-section TXT downloads driven by the Action Planner's per-tab
  "Download ..." buttons): sections 2 (Prioritized Technical Risks), 3 (Security Advisories -- also dropped
  the "SA-ID:" label in favor of the bare CVE number, e.g. `CVE: CVE-2024-42516 [Severity: CRITICAL]`), 4
  (Support Cases), and 6 (Switch Validation) now group by system via a `Map` built from the flat array, sorted
  by severity within each system where a severity exists. Section 5 (OS Upgrades) and 7 (Site Logistics) were
  already one-row-per-system and needed no change.
- `generateActionPlan()` (the live in-app Action Planner HTML, source of what gets shown in the tabs and of
  what `downloadFullActionPlan()`'s DOM-to-Markdown converter later exports): the same grouping applied to the
  Prioritized Technical Risks cards (section index 2), the Security Bulletins cards (section index 3, dropped
  `s.systemName` from the card title since it's now under a system header), and the Switch Remediation cards
  (section index 6). The OS Upgrade Roadmap cards (index 5) were already one-card-per-system.
- `compileCustomerSuccessPlanText()` (TAM Success Plan): `casesText` (the "ACTIVE SUPPORT TICKETS" list) now
  groups by system. Left `risksText` (built from `fixGroups` / `_filterAndDeduplicateRisks()`) **alone,
  deliberately** -- that section is intentionally organized by FIX (dedupes an identical remediation across N
  systems into one entry with a system list) rather than by system, which is a different and still-valuable
  organizing principle used identically across ~5 other deliverables (Top Corrective Actions-style sections).
  Restructuring that shared helper to be system-first was judged out of scope for this pass since it would
  affect every consumer of `_filterAndDeduplicateRisks()`/`_dfCollapseFindings()`, not just this one document;
  flag it to the user before touching it if they explicitly want that changed too.
- `compileAccountHandoverBrief()`: section 7 "RECENT ACTIVITY" used to be three separate flat lists (open
  cases, pending upgrades, active field actions) that each had to be cross-referenced by system name to see
  everything about one system. Rewrote it to build one combined per-system map (`_activityBySystem`) and emit
  a `SYSTEM: <name>` block containing all three categories together, only including the sub-headings that
  actually have entries for that system.
- Left alone (checked, not applicable): `compileExtendedDeliverables()`'s Technical Solution Proposal
  "OS & FIRMWARE UPGRADES" / "SAN/NAS STORAGE" blocks inside `solutionProposals` -- that section is
  deliberately organized by workstream/phase (a project-plan/SOW structure), not by system, and forcing it
  system-first would break its own narrative; `compileMSPServiceReport()`'s per-customer dashboard tally
  (`allRisks.forEach` at what's now ~line 24607-ish) -- that's an aggregate counter into a per-customer table,
  not an itemized list, nothing to group.

**Verified against real production data** (not synthetic): used the already-open browser preview
(`localhost:8080`, real fleet, 1052 systems loaded, NOT demo mode -- this was read-only verification, no
customer data was screenshotted or saved anywhere), selected `Customer: Liberty Group Ltd.` in the Action
Planner's scope selector, clicked the real "Generate Operational Action Plan" button via a real DOM event, and
confirmed via DOM inspection that all three HTML sections (Risks/Advisories/Switches) render `SYSTEM:` header
divs with the right entries nested under each. Then monkey-patched `triggerFileDownload` (via
`window.__dlFmtOverride='txt'` to skip the format-choice modal) to capture text instead of triggering a save
dialog, and confirmed the actual generated text for: Security Advisories (matches the user's requested format
exactly -- `CVE: ... [Severity: ...]` / `- Title:` / `- Mitigation:` / `- Status:`, no more Sa-Id, grouped by
system), Prioritized Risks, Switch Validation, the TAM Success Plan's support-ticket list, and the Account
Handover Brief's merged Recent Activity section. Also syntax-checked the whole edited `app.js` by fetching it
fresh from the running server and running `new Function(src)` in the browser (parses without a SyntaxError --
no Node available on this machine per the standing note below) before calling it verified.

**Also resolved, incidentally:** a stale-looking bug from earlier this session (browser showed the OLD,
pre-rewrite flat-`<div>` version of the Operations & Security scorecard's collapsible-by-category rendering,
`_renderCheckColumn`/`_renderCheckItem` inside `renderCSMTab()`, despite the source on disk clearly containing
the new `<details>`-based code) turned out to be a plain stale-page issue -- a fresh `location.reload()` of
the already-open tab picked up the new code correctly (confirmed via DOM: `csmAdoptionChecklist.innerHTML`
now contains real `<details>` elements). The earlier suspicion that `dist/app.js` / `dist/NetApp_AIQ_Advisor/
_internal/app.js` were being served instead of the source `app.js` was checked and ruled out (`curl`'d
`/app.js` from the running `:8080` server and diffed byte-length against the source file -- identical; the
running `python server.py` process's cwd is the repo root, not `dist/`). The `dist/` copies WERE stale at the
time (confirmed: they still had the pre-rewrite `_renderCheckColumn` with no `_renderCheckItem` helper), but
that was irrelevant to what the dev-mode browser was actually loading -- it only matters for the packaged EXE,
which the standard rebuild-and-sync step at the end of this session addressed anyway.

**Git:** branch `main`. v5.6.192 committed after this session's work (app.js, CHANGELOG.md, version.json,
CLAUDE.md, and the synced `dist/app.js` + `dist/NetApp_AIQ_Advisor/_internal/app.js` + `.exe`). Exe rebuilt via
PyInstaller (`build/AIQscraper.spec`, note the spec lives under `build/`, not the repo root) to
`%LOCALAPPDATA%\Temp\aiqbuild192`, never `build/build_windows.bat`. No `server.py` or HTML changes this
session, so only `app.js` + the exe + `base_library.zip` needed re-syncing into `dist/`.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir via
`build/AIQscraper.spec`, never `build/build_windows.bat` -- destructive). Server.py changes need an actual
server restart -- app.js is served fresh on every page load and needs neither. **HTML changes must land in
both `index.html` and `index_src.html`.** **Verify UI wiring with a real DOM event**, never a direct function
call. **Any hand-rolled OOXML (docx/xlsx) change must be validated by reproducing the file structure in Python
and loading it with `python-docx`/`openpyxl`** (installed via pip, not present by default) **before calling it
verified.** **Any screenshot of this app for documentation must block `/api/**` (or otherwise force demo mode)
and verify the resulting system count before saving** -- the app's default loaded state is the real fleet, not
demo data. **No Node.js on this machine** -- to syntax-check a JS edit, fetch the live-served `app.js` in the
browser preview and run `new Function(src)` (throws `SyntaxError` on a real parse error, and since it's never
called, nothing in the file actually executes).
