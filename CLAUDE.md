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

## Session handoff -- 2026-09-29 (Windows dev station, v5.6.177 -> v5.6.179)

Three separate threads this session; the second and third shipped.

**1. Security scare, unresolved.** User installed ARIA fresh on a Mac (unzipped straight from a GitHub
download, no Google Drive involved) and it came up already connected to Active IQ with a refresh token,
account filters, and watchlist IDs visible in the GUI. Did exhaustive git forensics on `ebeauzec/ARIA`
(`git ls-files`, `git ls-tree -r HEAD`, `git log --all --diff-filter=A --name-only`, `git grep` for
secret-like patterns, direct inspection of every `data/*.json`) -- **the repo itself is clean, nothing
committed.** Leading theory: `localStorage` for `http://localhost:8080` is scoped by origin, not by which
files are served from it, so stale watchlists/credentials from a prior run on the same origin could look
"pre-connected" regardless of which code deployed there. Gave the user Brave cache-clearing steps to test.
**Not confirmed fixed or even correctly diagnosed -- follow up if it recurs.** Also flagged but not fixed:
`.gitignore` has `aiq_config.json$` -- gitignore is glob syntax, the trailing `$` is a literal character,
not an anchor, so that line doesn't actually match the file. Harmless today only because the file was never
`git add`ed; worth fixing for real given this thread was about credential hygiene.

**2. ASA (All-SAN Array) capacity bug, fixed (shipped, v5.6.179 then properly fixed v5.6.180).** User: no
capacity/reporting for any ASA systems. First pass (v5.6.179) found Active IQ genuinely returns null for
usedKiB/utilizationPercentage/rawMarketingKiB at both system and cluster level for some ASA r2 clusters, and
shipped an honest "no capacity data" note (same pattern as StorageGRID/E-Series) instead of a misleading
"0.0 TB / N/A" card. **The user pushed back — "i am positive that it is possible to view asa capacity in
aiq.. there must be a way to get this" — and was right.** Ran a live GraphQL introspection against the real
Active IQ API (`__schema` query via a one-off script reusing `server.py`'s own `_gql`/token-exchange
functions, NOT through the app) and found: `ontapPersonality` is a real, queryable field (values `Unified` /
`ASAR2` / `AFX`, confirmed live — casing is inconsistent between the enum's declared name `ASAR2` and the
value the API actually returns, `ASAR2`... but written `Unified` not `UNIFIED` for the other case, so compare
case-insensitively), and ASA r2 systems (`ontapPersonality: "ASAR2"`) have `capacity{physical{...}}` genuinely
null but DO report capacity per LUN/namespace via `luns`/`namespaces` GQL fields the harvester queried
`{ totalCount }` on but never fetched `capacity` for. Cross-checked the LUN `capacity.usableKiB` field against
a working system's known-good usable capacity and confirmed it's **mislabeled — actually bytes, not KiB**
(the KiB interpretation gave an impossible 150 PB of LUNs on a 2-node ASA-A70; the bytes interpretation gave a
plausible ~146 TiB). Added a small standalone "ASA r2 capacity merge" GQL pass in `server.py` (~line 2036,
same pattern as the existing `ESERIES_CAP_FIELDS`/`SHELVES_SUMMARY_FIELDS` small-query-merged-by-serial
approach — inlining into the main query would hit Active IQ's "Maximum height (field count)" limit and
degrade the whole harvest), scoped to `ontapPersonalities: [ASAR2]` (only ~8 systems fleet-wide, confirmed
live, so this is cheap even unscoped by watchlist). Sums LUN+namespace usable bytes into a new
`asaLunUsableKiB` field (kept deliberately separate from the pre-existing, still-unconfirmed `saz*` fields —
don't conflate "LUN/namespace capacity" with "Storage Availability Zone capacity", they're different, and the
saz* fields already had a **dead duplicate-key bug**: a second `"sazTotalRawKiB": 0` / `"sazUsedKiB": 0` later
in the same Python dict literal silently overwrites any real value the first one sets, since Python dict
literals are last-key-wins — left as-is since nothing sets those fields to non-zero, but do not reuse those
field names for new data without also removing the duplicate). app.js (`enrichSystemTelemetry`, ~19038-19048,
~19296-19312, ~19372-19383): `isASAr2` now also matches `"ASAR2"`; a new fallback fills raw/usable capacity
from `asaLunUsableKiB` (tracked via `_asaLunFallbackUsed` so the platform note only claims "LUN/namespace
derived" when that's actually true, not when Active IQ's own cluster-level fallback already supplied a real
raw/usable number); `_capacityUnavailable` only stays true when there's truly nothing, not even LUN data.
Verified with `enrichSystemTelemetry()` called directly (not the UI) against three cases: a synthetic
genuinely-all-zero ASA r2 system (correctly shows the honest note), a synthetic zero-cluster-capacity-but-
real-LUN-data system built from the exact live 62-LUN CLKDRNACLUS01-02 numbers (correctly derives 146.2 TB
raw/usable with the accurate platformNote), and a real live system from a fresh harvest, serial 952541000528
/ Dept of Home Affairs - KZN (`ontapPersonality` came back `"ASAR2"` live, 403 LUNs, `_capacityUnavailable:
false`). Required a full `server.py` restart mid-session (killed the running PID on :8080, relaunched) since
harvester changes don't hot-reload like app.js does.

**3. Deliverable filenames standardized (shipped, v5.6.178).** User: downloaded filenames should be
`<Document Title> - <Customer> - <DD Month YYYY>` for every deliverable, uniformly. Added
`_dlFilename(title, scope, ext)` in `app.js` (right before `triggerFileDownload`, ~line 32780) and wired it
into every download call site: all ~16 types in `downloadDeliverable()` (~line 32791, each with its own
title string -- e.g. `'Executive Risk Assessment'`, `'TAM Quarterly Business Review Pack'`), the As-Built TXT
branch of `downloadPlanSection(19)` (~line 32281), and `downloadAsBuiltXlsx()`. `cleanScope`
(underscore-mangled name) is now unused in those spots -- left alone in `downloadPlanSection`'s other
section indices (1-18), which still use it. Since the filename `base` string also becomes the Word title
block via `_buildDocx()`, this fixed the in-document title to match the filename for free. Verified against
real production data (2898 systems, real customer "Liberty Group Ltd.") by monkey-patching `_dlBlob` to
capture names instead of triggering save dialogs -- confirmed correct output across txt/docx/md/csv/xlsx,
e.g. `"TAM Quarterly Business Review Pack - Customer Liberty Group Ltd. - 29 September 2026.docx"`.
`generateCVRPptx` (PPTX export, ~line 33021) was checked and confirmed to be dead code (no call sites) --
left untouched.

**4. LUN/NAS SAN reporting, shipped (v5.6.181).** User, right after the ASA fix landed: wants LUN inventory
(sizes, capacity, mappings) and NAS volume inventory built into "all existing tooling, reporting and
deliverables", best-practice alignment, and new Action Planner sections if needed; a follow-up added "lun to
igroups mapping, capacities, paths, best practices, multipathing etc." **Checked the live schema first (same
introspection as the ASA fix) before committing to anything:** LUN and NAS Volume capacity both exist and are
rich; **igroups, initiator groups, and multipathing do NOT exist anywhere in the schema** — confirmed live,
not assumed. Asked the user via AskUserQuestion how to handle that gap and what to prioritize; they said
proceed LUN/NAS-capacity-only, and build all three of harvester+data model, an Action Planner section, and
deliverable integration.
- **server.py** (~line 2131, "LUN / NAS volume inventory summary merge", same small-query-merged-by-serial
  pattern as ESERIES_CAP_FIELDS/the ASA r2 merge): fetches `luns`/`storageVolumes` (pageSize 50 each, capped
  to bound cost — `lunFetchTruncated`/`volumeFetchTruncated` flag when a system has more than that) for every
  ONTAP system across the configured watchlists, and computes per-system LUN count/capacity, volume
  count/capacity, thin-provisioning count, zero-efficiency count, high-snapshot count, and protocol mix, into
  a new `lunVolumeSummary` field.
  **Caught a second units bug before shipping** (same class as the LUN `usableKiB` mislabeling from the ASA
  fix): Volume `capacity.sizeKB`/`availableKB`/`usedSnapshotsKiB` are ALSO mislabeled — actually bytes, not
  KB. Caught by a sanity check on real data: one system's raw sum implied a single 420 TiB NAS volume on a
  cluster with 2.4 PB raw capacity total — divided by 1024 (treating as bytes) it became a plausible ~420 GiB
  volume, and the system's total volume footprint dropped from 72x its raw cluster capacity to a sane ~7%.
  Fixed before shipping (server.py now divides by 1024 when reading these three fields).
- **app.js**: `_sanNasStorageSummary(systems)` (~line 26316, right before `_dfActionPlan`) aggregates
  `lunVolumeSummary` across a scope into totals + best-practice findings (thin-provisioning adoption rate,
  volumes with 0% measured data-reduction, volumes with snapshot reserve over 30% of used capacity).
  `enrichSystemTelemetry` passes `lunVolumeSummary` through unchanged (~line 20547).
- **Action Planner**: new section 25, "SAN & NAS Storage" (tab button + `_renderSanNasStorageSection`,
  ~line 29313) — KPI tiles, best-practice findings, per-system inventory table (capped to top 50 by capacity).
- **Deliverables**: new per-system "LUN & Volume Inventory" subsection in the As-Built Configuration Document
  (`_renderAsBuiltSection`, inserted after the existing VMware Integration subsection) — this section's DOM
  content is what `downloadPlanSection(19)` reads for txt/docx export, so it flows into that download for free.
- **Verified**: `enrichSystemTelemetry()` called directly (not the UI) with a synthetic system built from the
  corrected real numbers (405 volumes, 165.3 TB total vs. 2403 TB raw cluster capacity) produces sane
  aggregate stats and the two expected best-practice findings. The Action Planner tab was verified via real
  DOM events (`.click()` on the actual tab-nav button, not `switchPlanTab()` called directly) rendering the
  empty-state correctly for a scope with no data.
  **Follow-up (resolved): the "harvest-cache staleness" gap above was not a real bug.** Multi-account setup
  (`aiq_config.json` has an `accounts` array with two real accounts, "Sithabile" and "NetApp" — `_sync_all_accounts`
  harvests each sequentially via `_do_full_harvest(account=...)`, ~15-20+ seconds just for token exchange +
  per-watchlist paging, ~110s total for one account in this fleet). My verification fetch ran immediately
  after clicking the sync button, before the background harvest had actually finished and called
  `_save_harvest_account` — so it read the previous (pre-fix) cached blob, which looked like staleness but was
  just impatience. Confirmed by: (1) reading the raw SQLite row (`harvest_cache_accounts`, `result_json` column)
  directly — already had the correct, fixed value; (2) calling `_get_merged_harvest(db)` directly in a fresh
  Python process — also correct; (3) re-fetching `/api/harvest` from the browser after the harvest genuinely
  finished (watch for `[HARVEST] Done in ...ms` in the server log, or poll `/api/sync-status` until
  `isSyncing: false`, before trusting any `/api/harvest` read) — 165.3 TB, sane. Also verified the Action
  Planner section itself end-to-end via real DOM events (real `.click()` on the tab-nav button and the actual
  customer-select dropdown, not calling `switchPlanTab()`/`generateActionPlan()`'s internals directly) against
  the real "Dept of Home Affairs - KZN" scope: 669.2 TB LUN / 282.2 TB volume capacity across 4 systems, with
  the two expected best-practice findings rendering correctly. No code change was needed for this follow-up —
  **lesson for next session: after triggering a sync (`triggerManualSync()` or `/api/harvest?force=1`), always
  wait for the harvest to actually complete (poll `/api/sync-status` or grep the server log for "Done in") before
  reading `/api/harvest` to verify a fix — a premature read looks exactly like stale/broken caching.**

**5. Feature Adoption Score extended (shipped, v5.6.182).** User asked how dedup/data-reduction applies to
ASA (answered: same real ONTAP efficiency engine as AFF for classic ASA, confirmed live at `1.3:1` on a real
ASA-A800; ASA r2 has no measured ratio available from Active IQ at all right now, only NetApp's marketed 4:1
guarantee, which the app already labels as a guarantee not a measurement). That prompted a look at the
Success Plan checklist screenshot (Operations & Security / Data Protection & Lifecycle, `_leftChecks`/
`_rightChecks` in `renderCSMTab()` ~line 17010-17046) — agreed two new SAN/NAS checks were worth adding
(thin-provisioning adoption, volume efficiency) but explicitly **rolled into `computeFeatureAdoptionScore()`**
(~line 18582) rather than added as new standalone checklist rows, since the user flagged the checklist as
already dense — see point 6 below for the follow-on plan on that. Verified against real data (serial
952541000528): total checks 4→6, both new ones correctly fail (0% thin-provisioned, 404/405 volumes with no
measured efficiency), no crash.

**6. Scorecard density — plan requested, NOT drafted yet.** User: "the scorecard is getting pretty dense....
make a plan about that", referring to the same Operations & Security / Data Protection & Lifecycle checklist
(`_leftChecks`/`_rightChecks` inside `renderCSMTab()`, rendered by `_renderCheckColumn()`, ~lines 17010-17070,
13 rows in the left column alone). **This was interrupted before a plan was actually produced** -- the very
next user messages redirected to the Action Planner download-button change (point 7 below) and the session
ended there. Next session: this still needs a real plan (ideas worth considering: collapsible categories,
promoting only failing/at-risk items to a "needs attention" view with the rest collapsed, splitting into a
tab of its own instead of two dense columns on the Success Plan page, or merging near-duplicate checks the
way Feature Adoption absorption just did) -- don't assume any direction was chosen.

**7. Action Plan download button (shipped, v5.6.183).** User: change the Action Planner's "Print / Save Action
Plan (PDF)" button to the standard txt/md/docx dialog, then "in fact, make that the default" (replace the
print behavior entirely, not add an option alongside it). Added `downloadFullActionPlan()` (app.js, right
before where `printActionPlan()` used to be, ~line 34080): walks every `.plan-section` child of
`#generatedPlanBody` (whatever's currently generated, all tabs/sections at once), swaps textarea values into
their text (same trick the old print function used, since `.innerText` doesn't reflect a textarea's live
value), strips buttons/selects, and feeds the combined Markdown-ish text through the existing `_askFormat()` +
`triggerFileDownload()` pipeline every other deliverable uses. **Deleted `printActionPlan()` entirely** (was
~90 lines building a standalone print-window HTML/CSS document) since nothing referenced it anymore after the
button's `onclick` changed -- confirmed via grep across app.js/index.html/index_src.html before removing.
Button relabelled "⬇ Download Action Plan" in **both** `index.html` and `index_src.html` (per the standing
HTML-dual-file rule). Verified via real DOM events: clicked the actual button, confirmed the format dialog
opened with txt/md/docx options, clicked the docx option for real, and confirmed a real 210KB .docx blob built
with the correct `<Title> - <Scope> - <Date>` filename (monkey-patched `_dlBlob` to capture instead of
triggering a save dialog, same technique as the earlier filename-standardization verification).

**8. LUN/volume data missing for one account -- real bug, found via the user's live debugging (shipped,
v5.6.184).** User reported the new SAN & NAS Storage tab (point 7's sibling feature, shipped v5.6.181) showed
nothing, even after a relaunch and manual sync. Traced live, with the user relaunching their own app instance
while I inspected the same `aiq_cache.db` this session's dev server also uses:
- Root cause, confirmed live: the "NetApp" account (918 of this fleet's 1083 systems -- the majority) lacks
  Active IQ's `unfiltered_system_access` privilege. Both the v5.6.180 ASA r2 merge and the v5.6.181 LUN/volume
  merge queried `systems(...)` with no `watchlistId` argument at all, which the API flatly rejects for that
  account: `"At least one mandatory argument is required for users without the unfiltered_system_access
  privilege"`. Both merges swallowed this (checked for exceptions, not GraphQL `errors` in a 200 response) and
  silently produced 0 hits every harvest since those features shipped -- no error surfaced anywhere, which is
  exactly why it looked like a caching/staleness issue at first rather than a real gap.
- The main system harvest already had a working fallback for this (REST-based watchlist auto-discovery,
  `_early_watchlists`, populated near the top of `_do_full_harvest` at ~line 1828) -- neither of my two merges
  reused it.
- **First fix attempt was wrong and made the privileged account (Sithabile) WORSE**: unconditionally preferring
  `_early_watchlists` whenever `watchlist_ids` was empty dropped Sithabile's LUN/volume hits from 143 to 24,
  because `_early_watchlists` is auto-discovered from a different, incomplete source (4 watchlists / 27
  systems) than what that account's unfiltered query actually covers (165 systems, since it DOES have the
  privilege). Caught by re-running the fix and comparing hit counts before/after, not assumed correct on the
  first pass.
- **Correct fix**: both merges now try unfiltered first (one cheap query, correct for privileged accounts)
  and only fall back to per-watchlist scoping via `_early_watchlists` on an actual privilege-error response
  (checked via the same `_PRIVILEGE_PHRASES` tuple the main harvest's `_fetch_systems_for_scope` already uses,
  ~line 1870). The ASA r2 merge (raw `_gql` calls, not `_fetch_systems_for_scope`) got its own small
  `_asar2_fetch_scope()` helper that returns `(rows, privilege_blocked)` to mirror the same pattern.
- Verified live end-to-end, twice (first attempt's regression caught and fixed before shipping): after the
  correct fix, a fresh multi-account sync gave Sithabile 143/165 (restored) and NetApp 703/918 (was 0) systems
  with LUN/volume data; `/api/harvest` merged total 846/1083. **Re-hit the same "read /api/harvest before the
  harvest actually finished" trap from point 2 one more time while verifying this** -- worth internalizing as
  a real recurring hazard in this codebase's multi-account setup (NetApp's harvest alone took ~300s), not
  re-documenting as if new each time.

Also shipped in v5.6.184, smaller and unrelated:
- **Action Plan download formatting** (user: "make the action plan docx formatting match the formatting of
  all the other deliverables"): `downloadFullActionPlan()` (point 7) was extracting `.innerText` from each
  section, which flattens tables/lists/headings to unstructured text. Added `_domToMarkdown(root, headingLevel)`
  (app.js, right before `downloadFullActionPlan()`): walks the cloned section DOM and emits real Markdown --
  `<table>` -> pipe table, `<ul>/<ol>` -> `-`/`1.` lists, `<h1-6>`/`<details><summary>` -> `#`-headings,
  `<textarea>` -> its live value -- so `_dxParse()`'s markdown mode (triggered by the `# ` the text already
  starts with) renders real Word tables/bullets/headings instead of squashed paragraphs. Caught and worked
  around a real hazard while verifying: generating this for the "Total Portfolio" (all 1052+ systems) scope
  produced a 48 MB Markdown string / 351 MB claimed blob size, because the As-Built section's DOM for that
  scope is already ~144 MB of HTML (a full per-system detail card for every system at once) -- pre-existing to
  this session's change, not something `_domToMarkdown` introduced (its output is smaller than the raw
  innerText/HTML, not larger). Verified instead against a realistic single-customer scope (413 KB text, 2.3 MB
  docx) -- this whole-plan download is not really usable at true fleet-wide "ALL" scope and that's a
  pre-existing limitation of the As-Built section's rendering approach, not something fixed this session.
- **Word palette lightened** (user, twice, converging on "just a tick lighter"): `_DX.NAVY`/`_DX.ACC`
  (app.js ~line 33394) went from `1F3864`/`2E5597` to `2A4D82`/`3D6BB3` -- affects every deliverable's Word
  export (heading text color, solid-fill card title bars and table header rows, all white-text-on-fill so kept
  dark enough for contrast).

**9. Word document column-table audit (shipped, v5.6.185).** User, after seeing the Feature Adoption Scorecard
corruption fixed: "recheck the rendering and formatting of ALL the documents downloadable as docx... make sure
there is none of this nonsense going forward." Delegated to a background `general-purpose` agent with a very
precise brief (the exact bug shape: a plain-text table with a header + a `_dxSegRule`-style segmented
box-drawing-dash rule line, then a data row whose interpolated value has variable character width followed by
more literal/interpolated content on the same line -- `_dxParse`'s column cutter reads boundaries from the
rule line's dash-segment positions, so anything after a variable-width value silently shifts per row).
Found and fixed three more real instances beyond the one already fixed this session: MSP Service Report's
per-customer health dashboard (`compileMSPServiceReport`, an operator-precedence bug --
`String(asupP)+'%'.padEnd(7)` only pads the literal `'%'`, not the combined value, because `.padEnd()` binds
tighter than `+`), the Security Posture Brief's Feature Gap Matrix (`_fGap`/`_fRatio` helpers sitting unused
right above the bug -- looked like a prior half-finished fix attempt, left the dead helpers alone since wiring
them up wasn't in scope), and the Sustainability Report's per-system trend column. Grepped the whole file for
the same `X + '...'.padEnd(n)` precedence anti-pattern afterward -- no further instances. Left several
similar-looking tables alone after confirming they're NOT at risk (already use `.padEnd()` correctly, or use a
single unbroken dash rule / dynamic-width split that tolerates variable content) -- see the agent's full report
in this session's transcript if auditing further. **Only checked plain-text/Markdown table alignment** -- did
not re-verify every deliverable's visual layout in an actual generated Word document end-to-end; if the user
finds more corruption, it's a different bug class, not this one recurring.

**10. Snapshot best-practice reporting -- requested, NOT started.** User, immediately after the column-table
audit shipped: "also look at snapshots... align with best practices, and look for, for example, snapshots that
are stale, large, etc." This is a new, similarly-sized feature request to the LUN/NAS work (point 7/8/9's
sibling) -- **before writing any code, repeat the same discipline that worked for LUN/volume**: check the live
GraphQL schema (the same `__schema` introspection technique, reusing `server.py`'s own `_gql`/token-exchange
functions in a one-off script) for what snapshot fields Active IQ's API actually exposes (per-volume snapshot
count/age/size, snapshot policy/schedule, snapshot reserve %, orphaned/locked snapshots, etc.) before assuming
anything is buildable. Session ended before this was scoped or started.

**Git:** branch `main`, v5.6.178 through v5.6.185 committed and pushed individually (exe rebuilt each time via
PyInstaller to `%LOCALAPPDATA%\Temp\aiqbuild178`..`aiqbuild185`, synced into `dist/NetApp_AIQ_Advisor/` +
`dist/app.js`; v5.6.180-181 and v5.6.184 also synced `dist/NetApp_AIQ_Advisor/_internal/server.py` since those touched the
harvester; v5.6.183 also synced `dist/NetApp_AIQ_Advisor/_internal/index.html` since that's the first fix this
session that touched HTML). Working tree otherwise shows harvest data files modified by the running server
(`data/*.json`) and untracked docs images -- never commit those with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart -- app.js is
served fresh on every page load and needs neither. **HTML changes must land in both `index.html` and
`index_src.html`.** **Verify UI wiring with a real DOM event**, never a direct function call. **Any hand-rolled
OOXML (docx/xlsx) change must be validated by reproducing the file structure in Python and loading it with
`python-docx`/`openpyxl`** (installed via pip, not present by default) **before calling it verified.**
**Any screenshot of this app for documentation must block `/api/**` (or otherwise force demo mode) and verify
the resulting system count before saving** -- the app's default loaded state is the real fleet, not demo data.
