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

## Session handoff -- 2026-09-30 (Windows dev station, v5.6.191 -> v5.6.196)

Five threads this session, all triggered by screenshots of generated deliverables.

**18. Table swallowing the line right after it in Word exports (shipped, v5.6.196).** User screenshot: TAM
Success Plan's Risk Posture Summary table (`_dfTable(['Critical','High','Medium'], ...)`) rendered fine, but
the very next line -- "Security-Related Risk Findings: 74 (...)" -- came out sliced into fragments ("Securit"
/ "y-Relat" / "ed Risk Findings: ..."). Root cause, in `_dxParse()`'s segmented-rule table branch (app.js
~34368-34379): once a segmented-rule header/rule pair is detected, the continuation loop kept consuming ANY
non-blank line as another table row and slicing it at the header's column offsets -- it had no way to tell
"another real data row" apart from "the next paragraph, which just happens to follow with no blank line in
between." Real trigger: several deliverables put a one-row `_dfTable()` immediately before a plain summary
line with no blank line separating them. Fixed by requiring a genuine data row (from `_dfTable()`'s
`padEnd()`+`join(' ')`) to have a literal space character at every internal column boundary; prose that
merely overflows past that offset doesn't, so it now correctly stops the table there. First fix attempt
(reject lines starting with `- `) was too narrow -- caught the TAM Success Plan instance but missed QBR Pack's
"Security-Related Risk Findings: ..." / "Support Cases: ..." lines, which use plain indentation with no dash;
replaced with the general word-boundary check. **Verified exhaustively, not just the one screenshot**: wrote a
harness (`_dxParse()` called directly on each deliverable's real generated text, scanning every table block
for cells starting mid-word) and ran it against all 15 downloadable deliverable types (SUCCESS_PLAN,
QBR_PACK, PROBLEM_STATEMENTS, SOLUTION_PROPOSAL, SALES_PROPOSAL, MSP_REPORT, SECURITY_BRIEF,
RISK_REMEDIATION_BRIEF, SUSTAINABILITY_REPORT, HANDOVER_BRIEF, VALUE_REPORT, CUSTOMER_REPORT, TICKET,
IMPLEMENTATION, EMAIL) against the real 1052-system fleet -- zero remaining instances of this bug; confirmed
the fix doesn't over-trigger by checking a genuine 3-row segmented table (Feature Adoption Scorecard) still
parses as 3 real rows, not 1. Also built and validated a REAL .docx end-to-end (not just the parsed
intermediate form): captured `_buildDocx()`'s output via a `_dlBlob` monkeypatch, moved the bytes out of the
browser as chunked base64 (a direct real-file-download attempt didn't land in any locatable folder in this
sandboxed preview browser -- worth remembering if this comes up again, don't rely on triggering the actual
save dialog for verification, capture the Blob instead), decoded with Python, and opened it with `python-docx`
(223 paragraphs, 38 tables, no errors) per this repo's standing OOXML-verification rule. **LibreOffice
(`soffice`) is NOT installed on this machine** -- the docx skill's visual PDF-render step doesn't work here;
python-docx/openpyxl structural validation is the only verification available locally, consistent with
CLAUDE.md's existing standing note. Found and deliberately did NOT fix a much smaller, different
inconsistency while sweeping: a support-contract inventory table has 2 rows (StorageGRID systems, which have
no service-level field at all) with one fewer field than the rest -- confirmed benign by reading
`_docxTable()`'s renderer, which always emits the max column count across all rows and fills a missing cell
with an empty string, so this just shows one blank cell for those two systems, not corrupted text.
**Also hit and resolved a self-inflicted false alarm while debugging**: spent significant time chasing why a
direct call to the real `triggerFileDownload` produced no `_dlBlob`/`_buildDocx` calls and no error -- turned
out `window.__origTFD2 = window.__origTFD2 || triggerFileDownload` had captured one of my OWN earlier
capture-only stub functions (from a previous browser-console monkeypatch in the same session) instead of the
real original, because I'd left `window.triggerFileDownload` overridden at the time that line ran. Not an app
bug; reloading the page for a clean reference resolved it. Lesson for next time doing this kind of
monkeypatch-and-capture verification: reload before capturing an "original" reference if the global may
already be patched from earlier in the same session, or capture it once at the very top of the session before
any overrides.

**17. Cross-site version parity recommendation added on top of point 16 (shipped, v5.6.195).** Immediate
follow-up to point 16 below, same conversation: user first asked to make a "minimum ONTAP recommendation"
for the non-CVE NetApp issues per customer/system; when reminded that individual findings don't cleanly map to
one version (see point 16), user clarified the actual ask -- keep the per-system finding detail as-is, and ADD
a separate, single customer-wide statement: all systems for a customer should converge on one version for
cross-site parity. Implemented as `_dfNonCveParityVersion(systems)` (app.js, right after
`_dfCriticalHighNonCveIssuesSummary`, ~line 19241): for systems with an outstanding non-CVE critical/high issue
(from point 16's `_dfCriticalHighNonCveIssuesSummary`), takes each one's REAL Active-IQ-recommended target
version (`sys.upgrades.targetVersion` where `source === 'active-iq'` only -- never the heuristic fallback,
which is a guess Active IQ never made) and picks the highest per platform family (ONTAP/StorageGRID/SANtricity
kept separate -- version numbers aren't comparable across product lines). This reuses a trusted, already-
harvested field rather than parsing free text, so it doesn't reintroduce the version-fabrication risk flagged
in point 16. Wired in as an ADDITIONAL statement (not a replacement) alongside the existing per-system detail
in all 3 of the same places: a new banner at the top of the OS Upgrade Roadmap section (before the per-system
cards), a "Cross-Site Version Parity Recommendation" block inside the Executive Risk Assessment's existing
"CRITICAL NETAPP ISSUES (Non-CVE)" section (still followed by the per-system SYSTEM: breakdown), and one
sentence appended to the TAM Success Plan's existing summary line. Verified live against a real account
(Telkom SA Ltd.): 8 affected systems all converge on one ONTAP recommendation (9.16.1P15); a larger scope
correctly drove a 9.19.1P2 recommendation from 111 affected systems while still listing all 111 individually
below it. Confirmed via real DOM events (Action Planner) and captured text downloads (both compilers) that the
per-system detail was NOT lost -- both the parity statement and the individual findings render together.

**16. Critical CVEs vs. critical non-CVE NetApp issues split (shipped, v5.6.194).** User, from a screenshot of
the OS Upgrade Roadmap card: asked to distinguish "critical CVEs" from "critical NetApp issues" since each

**16. Critical CVEs vs. critical non-CVE NetApp issues split (shipped, v5.6.194).** User, from a screenshot of
the OS Upgrade Roadmap card: asked to distinguish "critical CVEs" from "critical NetApp issues" since each
needs a different minimum version to fix, then "this needs to carry through the entire ARIA suite." **Before
building anything, checked real fleet data for what non-CVE critical/high Active IQ risk findings actually
look like** (`_dfCriticalHighFixFloor()`'s CVE-only floor has a real "Fixed In" release database behind it;
non-CVE findings do not) -- sampled 30 real critical/high non-security findings across the fleet and found the
fix vector is NOT a single ONTAP version the way CVEs are: drive/shelf/BMC firmware updates, config changes,
hardware refreshes (EOA/EOS), or "move off a pre-release build." Worse, two real findings explicitly describe
a version to AVOID or a version where a bug TRIGGERS, not one that fixes it (`"ONTAP 9.16.1 and newer releases
do not support IOM6 Modules"`; `"...after upgrade to 9.12.1P4 or 9.13.1"` describing when a bug manifests).
Naive regex version-extraction from this text would risk recommending an upgrade INTO a version a finding
warns against. Asked the user via AskUserQuestion how to handle un-extractable findings; they asked to review
a sample first, which confirmed the above, so implemented count-only (no fabricated version) for the non-CVE
side: `_dfCriticalHighNonCveIssues(sys)`/`_dfCriticalHighNonCveIssuesSummary(systems)` (app.js, right after
`_dfCriticalHighFixFloorSummary`, ~line 19180) filter to critical/high risks that aren't CVE-tagged (no
`cveDetails`, no CVE regex match, category isn't security/best-practice) and return a count + finding list,
deliberately never a version. Wired into the same 3 places the CVE floor already existed (confirmed via grep
these were the only 3 -- did NOT add the Security Fix Floor concept to documents that never had it, e.g. QBR/
MSP/Security Brief, since that's a different, unasked-for scope expansion): the OS Upgrade Roadmap card
(`generateActionPlan()`, a new sibling block right after the existing Security Fix Floor block, listing up to
5 findings with a "+N more"), the Executive Risk Assessment (new "CRITICAL NETAPP ISSUES (Non-CVE)" section,
grouped by system per this session's earlier grouping work), and the TAM Success Plan (one summary line).
Renamed the existing CVE floor's label to "Security Fix Floor (Critical/High CVEs)" in the TAM Success Plan for
clarity now that there are two figures. Verified live against a real account (Telkom SA Ltd.): 16 CVE-floor
occurrences and 8 non-CVE-issue occurrences rendered correctly in the same Action Plan; the TAM Success Plan
and Executive Risk Assessment text downloads both show the two figures side by side with no version fabricated
for the non-CVE side, and a real example (`"Updating to BMC FW 19.3 resolves unexpected cluster node
shutdown"`) confirms even findings that DO name a fix version don't necessarily mean ONTAP -- reinforcing why
this stays count-only rather than attempting selective extraction.

**14b. User gave a screenshot of the Security Advisories report (flat "Sa-Id: CVE-... -
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

**15. Cisco Nexus/MDS interop findings cross-attributed (shipped, v5.6.193).** Second thread, same session:
user gave a screenshot of the Technical Solution Proposal's "Interop Compatibility Warnings" table asking "why
are switches still showing ontap?" -- the Finding column for BOTH a Cisco Nexus row and a Cisco MDS row was
prefixed with the same raw serial number (`90820130000000001272:`). Root cause, confirmed live:
`IMT_INTEROP_MATRIX`'s `cisco_nxos` and `cisco_mds` entries (app.js ~12379-12403) both key off one fleet-wide
`signal: "cisco_san"` (set true in `_buildDetectedSignals()` whenever ANY Cisco switch of ANY model exists
anywhere in the fleet), and `runIMTInteropCheck()` (~14205) then ran BOTH integrations' checks against every
system's ONTAP version with no per-system check of which switch, if any, that system actually has. Confirmed
live: the flagged system (`90820130000000001272`) has `switches: []` -- zero switches attached -- yet appeared
in both a Nexus and an MDS finding purely because its ONTAP version (9.12.1) fell inside both integrations'
trigger ranges. Fixed by adding a `switchMatch` regex to each integration (`/nexus/i`, `/mds/i` -- matched
against both `sw.model` and `sw.firmware`, since a real switch's model field can be a generic classification
while firmware reliably names the product) and filtering to `scopedSystems` (systems with a matching switch)
before running the below-minimum and EOL-imminent checks for that integration. Verified live: the zero-switch
system now produces 0 Nexus/MDS findings (its 2 remaining findings are legitimate VMware/OTV ones, unaffected);
two synthetic systems (Nexus-only, MDS-only) each produce exactly one finding, for their own switch type only,
none for the other. Only `cisco_nxos`/`cisco_mds` shared a signal -- checked, no other integration in the
matrix does.

**Git:** branch `main`. v5.6.192 through v5.6.196 each committed individually after this session's work
(app.js, CHANGELOG.md, version.json, CLAUDE.md, and the synced `dist/app.js` +
`dist/NetApp_AIQ_Advisor/_internal/app.js` + `.exe` each time). Exe rebuilt via PyInstaller
(`build/AIQscraper.spec`, note the spec lives under `build/`, not the repo root) to
`%LOCALAPPDATA%\Temp\aiqbuild192`..`aiqbuild196`, never `build/build_windows.bat`. No `server.py`
or HTML changes this session, so only `app.js` + the exe + `base_library.zip` needed re-syncing into `dist/`.

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
