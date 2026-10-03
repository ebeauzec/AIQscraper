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

## Session handoff -- 2026-10-03 (Windows dev station, v5.6.230)

**State:** `main`, v5.6.221 (APP_VERSION + version.json + CHANGELOG.md + top APP_CHANGELOG entry all bumped together). `dist/` synced
(app.js, `_internal/server.py`, rebuilt exe + base_library.zip from `%LOCALAPPDATA%\Temp\aiqbuild221`). See `git log` for pushed state.
Full history for v5.6.203-221 is in CHANGELOG.md and the new CONTEXT.md addendum ("StorageGRID, Platform Insights, Word exports and
restricted-account scoping"); README.md was audited and brought up to date (27 Action Planner tabs, StorageGRID, Platform Insights,
Word export of every view, restricted accounts, "Data Active IQ does not provide").

**Most important lesson of this range -- restricted accounts.** An Active IQ account without `unfiltered_system_access` (the "NetApp"
account, 18 watchlists, 1,181 systems) rejects every unscoped query with "At least one mandatory argument is required". Code that ignored
that error produced silent zeros and "Unknown". v5.6.221 fixed the rest: shelf-firmware summary, risk instances, cases, customers,
recommendations, sites, sustainability, official health score, renewals. Per-watchlist reference data (customers, recommendations, sites,
renewals) is merged across ALL `_early_watchlists`; sustainability/health score take the first watchlist that reports one
(`_all_scopes`, `_scope_arg`, `_restricted_scope` in `_do_full_harvest`). Verified live: risk instances 0->33,274, cases 0->1,167,
recommendations 111, sites 68, renewals 578, sustainability 28, health score 75. **Any new top-level query must be checked against the
restricted account, not only the privileged one.** Known remaining limit: renewals query is `pageSize: 200` per watchlist with no paging.

**Also fixed this session:** Firmware Currency Word report (`compileFirmwareWordMd`); Risk Trend chart and deliverable 30/60/90-day trend
now follow watchlist/group scope (`POST /api/history/trend` with serials; `_dfTrendData` accepts a serial array); Success Plan affected-
systems list lists each system once with findings beneath, single-line findings (`_fmtAffectedSystemsBlock`); Word export of every
Action Planner view; StorageGRID latest-version; MetroCluster card follows the selected node.

**v5.6.222:** fleet capacity double-counted StorageGRID storage-node E-Series arrays (inside the grid's own `gridCapacity`); `_dfCapacityUniqueSystems()` fixes the Overview charts, Value & ROI chart/runway and `computeFleetCapacitySummary`. Used capacity 167,260 -> 127,920 TB on the live fleet. Still to apply: per-node capacity breakdown table and deliverable capacity totals.

**v5.6.223:** systems with no capacity history (43) drew a projection from zero using a default 1 GB/day 'estimate'; chart/growth/runway now show no-data and they add no growth to the aggregate. The default estimate may still feed other per-system capacity lists.

**v5.6.224:** capacity-history spikes (Active IQ monthly rows with one month at 1.5-4x capacity, 111 systems, mostly 2026-08; Sep blank for nearly all) -> `_dfCleanMonthlyCapacity()` builds six calendar months, interpolates spikes/gaps, growth measured over the same window; footnote under the chart. Not probed against the raw API.

**v5.6.225:** 593 systems (all StorageGRID/E-Series + 248 ONTAP) had growth 'estimated' = invented from raw capacity (0.5%/month) with back-filled history/projection; now `growthSource:'unavailable'`, no projection, aggregate says 'measured on N of M systems', runway N/A when none. TODO: derive real growth for StorageGRID from `gridCapacity` QoQ/YoY.

**v5.6.226:** Technical Audit used to auto-select only the first 20 systems of a scope (`TAM_AUTO_SELECT_CAP`), hiding nodes (one half of a MetroCluster pair); now unlimited (672 systems render in ~340 ms); node strip grouped by cluster/grid (`e.group`/`e.order` from `_dfNodeStrip`); MetroCluster card completes clusters. The browser pane was hidden at the end, so the grouped strip was verified from the DOM, not a screenshot.

**v5.6.229:** headings. Plain-text deliverables go through `_dxParse`; a title line after a blank line that introduces a table/list/rule/labelled lines is now a sub-heading; the DOM export (`_domToMarkdown`) recognises styled bold/small-caps labels (`headingLike`) and drops empty ones. To audit after changing generators: parse each deliverable and list short `p` blocks directly above a `table`/`bullet`/`num` block.

**v5.6.230:** Word downloads per Action Planner tab. Tabs 2/3/5 have dedicated generators (`compileRisksWordMd`, `compileAdvisoriesWordMd`, `compileUpgradesWordMd`); the rest go through `_domToMarkdown` (now: tile tables, stat cards, case/system/switch headers, label bolding, label/value runs -> tables). Audit recipe: generate the plan for a customer, call `downloadPlanSectionWord(i)` with `triggerFileDownload` stubbed, `_dxParse` the text and flag lone numbers / label-before-table / empty last column; also `_buildDocx` each. Known leftovers: Portfolio Dashboard trend rows, Site Logistics contact table.

**Open / not done:**
- Word layout was judged from generated Markdown/structure, never rendered in Word -- open one before sending to a customer.
- Success Plan create/update mutations verified only with bogus-NAGP and invalid-enum probes, never written live.
- CONTEXT.md sections 5-12 are a v4.0.7 snapshot (known-stale items struck through, the rest not audited).
- Genuine Active IQ limits (do not re-investigate): no E-Series/StorageGRID controller/port/WWPN, VMware StorageGRID node detail, per-model
  StorageGRID EOS dates, ILM active-policy flag, depot/hub logistics, SP/BMC/BIOS/DQP for StorageGRID/E-Series.

**Process notes.** Write JS/Python edit scripts with the Write tool (heredocs mangle `\n`). The Claude preview wrapper detaches from the
server when it exits, hiding its log: for long harvests run `python server.py > log` yourself and monitor with a selective grep (per-page
case lines are far too noisy). The startup auto-refresh collides with a forced harvest ("Sync already in progress") -- harmless.
Rebuild the exe with `python -m PyInstaller --noconfirm --distpath <dir>/dist --workpath <dir>/work build/AIQscraper.spec`, then copy
the exe + `_internal/base_library.zip` into `dist/NetApp_AIQ_Advisor/` and copy `server.py`/`app.js` into `_internal/` by hand.
