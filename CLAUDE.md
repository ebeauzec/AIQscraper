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

## Session handoff -- 2026-10-02 (cloud session, repo renamed + StorageGRID API audit)

**UPDATE (Windows dev station, same day, v5.6.203 shipped): the StorageGRID audit below WAS completed live and
acted on.** Live introspection confirmed Active IQ exposes `StorageGrid.gridSites{nodes{storageNodeType applianceModel
raidMode driveType driveSizeGB osVersion}}`, `.tenants{buckets{versioning isS3ObjectLockingEnabled isCloudMirror ...}}`
and `.ILMDetails{rules{ruleName filter isDefaultRule referenceTime ingestBehavior timePeriodsAndPlacements{placements{
schema placementType storagePool{name sitesAndGrades{siteName}}}}}}` -- all populated on real grids -- so the app's old
"ILM not reported by Active IQ" claims were WRONG (check `app.js` for any leftover). v5.6.203 harvests them (server.py
`ESERIES_CAP_FIELDS` StorageGrid fragment -> `storagegridTopology`, carried through `enrichSystemTelemetry`), analyses them
(`_dfStorageGridView` in app.js, right after `_dfSystemIssueRankingText`), and reports them in a new Technical Audit card,
a new Action Planner tab (index 26), and the TAM Success Plan, QBR, Exec Risk Assessment, Handover 7c, MSP 7a, Risk &
Remediation, Security Brief 6a, Customer Report 7b, plus findings in the Solution/Sales proposals and tracker import. Replicated
placement `schema` = copy count, Erasure = EC scheme. Verified by injecting real-shaped topology into a real StorageGRID system
(all deliverables render, 5 real tables per Word doc, GUI via real clicks). **The running dev server's cached harvest has no
topology until a server restart + `/api/harvest?force=1`.** The probe script `tools/probe_storagegrid_schema.py` from the cloud
session is now superseded by this live check but harmless. Full detail: CHANGELOG.md 5.6.203. The rest of this section is the
cloud session's handoff, kept as written.

**FOLLOW-UP (v5.6.204 + v5.6.205, same day): Platform Insights + all open items.** Live introspection found unharvested, populated fields on
ONTAP/E-Series/StorageGRID (energy, hardwareCapabilities, drivesSummary, osUpgradeHistory, securityFiles/systemFiles, nvsRAM, gridSites.siteCapacity;
v5.6.204) and ONTAP adapterInterface (FC adapters/WWNN), cloudInsightsHosts/Tenants, talking points (v5.6.205, separate ONTAP-only query because the
combination exceeds the field-count limit). Harvest: `_build_platform_extras` / `_build_ontap_extras2` (server.py) -> `platformExtras`; analysis:
`_dfPlatformInsights` (app.js); Action Planner tab 27. **Real bug found and fixed:** the Success Plans harvest query was INVALID (`objectives` without
sub-fields, non-existent `tamNotes`) so Success Plans silently never loaded; now fixed, with real milestone/action progress (`_cspProgress`) replacing the
'Outcomes Lift: Coming soon' tile. The privileged test account has 0 plans, so real plan data is untested; the NetApp account needs a nagp/watchlist arg.
**Confirmed genuine API limits (do not re-investigate):** E-Series (SantricitySystem) and StorageGRID nodes have no controller/port/WWPN fields; no
parts-logistics hub/depot status (only RMAPart); ILM time periods are days; `energyConsumptionMetrics` is per concrete type (not on `System`); E-Series
reports actual power 0 (projected only). StorageGRID per-node risks: node systems are not listed separately with includeStorageGridNodes (same count), so
risks are on the grid system. Restart the server + `/api/harvest?force=1` to see any of this from a real harvest.
**v5.6.206-207:** StorageGRID in the GUI needed (a) merging duplicate systems across accounts (client dedupe was first-wins and dropped the copy carrying topology), (b) resolving node systems to their grid, (c) `includeStorageGridNodes: true` on the systems query (node systems were never harvested), and (d) grid-based node counts (`_dfStorageGridView` -> `nodeTotal`, `_dfEffectiveSystemCount`, `_dfPlatformMix`, `_dfSgForm`: VMWARE=virtual, STORAGE_GRID_APPLIANCE/SG-model=physical, BARE_METAL). Harvest now returns ~1350 systems incl. ~155 StorageGRID records. NOTE: shell heredocs mangled `\\n` escapes when generating JS edits (broke app.js once) -- write edit scripts with the Write tool and use chr(92)+'n' for JS newlines.
**v5.6.208:** ROOT CAUSE of most missing StorageGRID/platform data: the extras merges ran unscoped, which fails with a privilege error for the restricted 'NetApp' account (watchlist-scoped only) and was ignored; fixed via `_fetch_rows_all_scopes`. Now 12 grids (STC 43 nodes, Airtel up to 70, K+N 34) and `platformExtras` on ~1300 systems. StorageGRID findings are injected into the risk engine (`applyStorageGridRisks`, called after each `state.systems = ...map(enrich)`; ids `sg-<serial>-<slug>`, `ariaGenerated:true`, category StorageGRID) with recommendations from `_SG_RECS`. Node reporting = serial/name found among ANY system in scope (appliance nodes appear as E-Series controller systems; VMware nodes have UUID serials and never appear). Not done: StorageGRID checks against NetApp's published best-practice/EOS data per appliance model; node-level health beyond what the topology carries.
**Release rule:** bump `APP_VERSION` (app.js line ~30) together with version.json and the top APP_CHANGELOG entry. It was stuck at 5.6.191 through v5.6.205 (nav footer showed the wrong version); fixed, and a console warning now fires if they diverge. Success Plan mutations were also broken
(sent non-existent `tamNotes`; real input field is `notes: [{message}]`) and are fixed -- NOT exercised live (writes to the customer account).


**Repo renamed:** GitHub repo is now `ebeauzec/ARIA` (was `ebeauzec/AIQscraper`). The old
`origin` URL still works via GitHub's redirect (confirmed: a push with the old URL
succeeded and printed the redirect notice), but point new clones/remotes at the new URL
directly when convenient. Could not run `git remote set-url` myself this session -- blocked
by this environment's own permission classifier (not a git/auth problem) -- so `origin` here
is still the old URL; left as-is since the redirect works.

**Picking up after a 166-commit gap:** session started by re-reading the previous handoff
(v5.6.84, which assumed "next session = Windows"), then checking git state before doing
anything -- `git fetch origin main` showed `origin/main` **166 commits ahead** of this
container's last-known state (v5.6.202 vs. v5.6.84: the Windows sessions documented in the
PREVIOUS version of this handoff section, which is now in git history -- see `git log` /
`CHANGELOG.md` for v5.6.85 through v5.6.202, not repeated here per the overwrite rule). Local
branch had zero unique commits, so `git merge --ff-only origin/main` caught this container up
cleanly with no conflict. **Lesson reinforced: always `git fetch` + compare before assuming
"nothing changed since I last looked" -- a long gap between sessions on the same repo is
normal here, not a sign something's wrong.**

**This task: audit the Active IQ API for unharvested StorageGRID data (topology, ILM, etc.) --
could NOT be completed live, only prepped.** User asked to check for more scrapable
StorageGRID info. Confirmed via `ps -ef`/port check/`ls aiq_config.json` that **this cloud
container has no live Active IQ access at all** -- no running ARIA instance, no token file,
and the network proxy explicitly blocks `api.activeiq.netapp.com` (403, policy denial) even
if a token existed. The user mentioned "an instance of ARIA running on this system" mid-task,
then clarified it's running **on a Mac** -- a third physical machine in this project's
rotation alongside this cloud container and the Windows station the previous handoff
documented. Checked and confirmed that instance is NOT in this container (same "which machine
am I actually on" trap as the previous handoff's own mixup -- checked `ps`/ports/`pwd` again
rather than assuming, per that same standing lesson, and this time it genuinely was a
different machine, not a repeat of the earlier false alarm). **Do not assume "Windows station"
is the only other machine this project runs on** -- a Mac is now confirmed in the rotation
too; ask rather than guess which machine has live access when it matters.

**What WAS established (code audit, no live access needed):**
- Currently harvested: `StorageGrid.gridId`, `gridName`, `installedNodeCount` (bare count, no
  per-node name/role/health), `licenseCapacity`, `gridCapacity` (usable/used-data/
  used-metadata/reserved-metadata/physical/QoQ/YoY -- `server.py`'s `ESERIES_CAP_FIELDS`,
  around line 1758). Surfaced in Value & ROI card + deliverables.
- The app's own text (`app.js:24458`, `:29900`) claims ILM policies/rules and cross-grid
  replication are "not reported by Active IQ" -- but per this repo's OWN standing discipline
  (see the now-archived v5.6.197 entry in git history: "other 'not reported' claims... were
  NOT re-verified against a live schema and should not be assumed either confirmed-accurate or
  newly-fixable without doing the same live-introspection check first"), **this claim has
  never actually been checked against a live schema.** It may be true, may not be -- genuinely
  unknown, not confirmed either way.
- The one cached schema-introspection dump in this repo (`data/schema_probe_results.json`)
  never queried the `StorageGrid` type at all (it's an ONTAP firmware/disk/shelf probe).
  `data/tam_probe_results.json` and `data/tam_final_data.json` are also unrelated (TAM/
  sustainability/case types).
- A GUI card title that says "...& Grid Network Topology" (`app.js:40652`) is NOT a real
  multi-node topology feature -- checked the code, it's the generic per-system physical-port/
  cabling rear-panel card's title, reused across platforms (ONTAP/E-Series/StorageGRID each
  get their own title text for the SAME single-system port-diagram card). Don't mistake this
  string for evidence topology was ever investigated.

**What's NOT done, and needs a live-connected environment to finish:** wrote
`tools/probe_storagegrid_schema.py` (follows the existing `tools/probe_schema_types.py`
pattern used by prior live-introspection work) -- a schema-wide keyword sweep
(grid/ilm/tenant/site/bucket/node/topology/policy/etc., so it finds real type names without
guessing), a full `StorageGrid` type field dump, targeted probes of plausible type names
(`StorageGridNode`, `IlmPolicy`, `Tenant`, `S3Bucket`, ...), and a live sample query to confirm
any new field actually carries data, not just schema presence. **Needs to be run** (`python
tools/probe_storagegrid_schema.py` from the repo root) **on the Mac that has the live ARIA
instance running right now** (confirmed by the user this session) -- needs that machine's real
`aiq_config.json` and its network access to `api.activeiq.netapp.com`. Whoever runs it next:
read its output, then decide what (if anything) is worth harvesting and wiring in -- don't
assume the keyword sweep's type names are usable as-is without checking their actual fields
first (same discipline as every other live-schema check documented in this repo's history).

**Git:** `main` only, no feature branch this session (the Windows-only `.exe`-rebuild
situation from the previous handoff doesn't apply here -- this session made no `app.js`/
`server.py`/HTML changes, only added the new standalone probe script, so no `dist/` sync was
needed). Pushed directly to `main` (`fa61ade`). Working tree clean.

