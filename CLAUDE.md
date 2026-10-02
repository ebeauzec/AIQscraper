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

## Session handoff -- 2026-09-30/10-02 (Windows dev station, v5.6.191 -> v5.6.203)

Eleven threads this session (spanning midnight into 2026-10-01); the first ten were all triggered by
screenshots of generated deliverables, the last one wasn't.

**25. Full StorageGRID awareness (shipped, v5.6.203).** User asked whether Active IQ exposes StorageGRID grid
topology, nodes, roles, ILM rules; then "ARIA needs to be fully storagegrid aware". Live schema introspection:
`StorageGrid.gridSites{nodes}`, `.tenants{buckets}`, `.ILMDetails{rules{...placements{storagePool{name sitesAndGrades}}}}`
all exist and are populated on the real fleet (2 grids found in the first 300 systems: UWC_SG_1, NETAPP_SG; bucketName came back
null in samples). Replicated placement `schema` = copy count ("2"), Erasure `schema` = EC scheme. Harvest: fields added to the
`... on StorageGrid` fragment of `ESERIES_CAP_FIELDS` in server.py (tested live with the exact fragment, fits the field limit),
merged by serial into `s["gTopology"]`, output as `storagegridTopology`, carried through `enrichSystemTelemetry`
(round-trip tested). app.js: `_dfSgRulePlacements`, `_dfStorageGridView` (grids + findings), `_dfStorageGridSummaryLine`,
`_dfStorageGridText` (right after `_dfSystemIssueRankingText`); GUI `renderStorageGridStatus`/`_storageGridHtml`/
`_renderStorageGridSection` (card `tamStorageGridCard` in both HTML files; Action Planner tab index 26); demo data in the
`fam === 'storagegrid'` branch of `_demoHydrateSystem`; tracker import items (`sourceType: 'storagegrid'`). Deliverables: TAM Success
Plan, QBR, Exec Risk Assessment, Handover 7c, MSP 7a, Risk & Remediation, Security Brief 6a, Customer Report 7b (markdown),
Solution/Sales proposals (findings). NOT added: Sustainability, Value, Problem-statement-style docs beyond Exec Risk. Verified by
injecting real-shaped topology into a real StorageGRID system in the loaded fleet: all deliverables render it, `_dxParse` yields 5
real tables per doc, Action Planner tab and Technical Audit card render via real clicks/DOM. **The running dev server's cached
harvest has no topology until a server restart + `/api/harvest?force=1`**; findings are heuristics (e.g. "single-site grid" is high
severity by design) and should be sanity-checked against a real grid with the user. `time period start/end` units are not shown.

**24. Real performance regression: unbounded DOM growth in the Overview "Needs Attention" card (shipped,
v5.6.202).** User, NOT from a screenshot this time: "since the last few commits i'm noticing a clear delay
when clicking anywhere in the interface. it used to be a lot more responsive." Investigated rather than
guessing: grepped for anything that could run on every click (global `document.addEventListener('click'/
'mouseover', ...)` handlers -- found two, both trivial/unrelated), then reasoned about what changed recently
that scales with fleet size and runs on a common path. Found it: point 21's (v5.6.199) `renderNeedsAttention()`
rewrite built a `<details>` "Show N more systems" expander by eagerly `.map(rowHtml).join('')`-ing EVERY system
with any issue into the card's `innerHTML` -- each row a `<div>` with inline `onclick`/`onmouseover`/
`onmouseout` handlers -- not just the ones actually visible before the (collapsed) `<details>` was opened.
**Confirmed live, not just read the code and assumed**: on the real 1052-system fleet, this card was building
964 row divs (5 visible + 919 inside a collapsed `<details>`) on every single visit to the Overview tab, which
is the TAB THE APP LANDS ON. A ~900-extra-node DOM rebuild on a page the user returns to constantly, combined
with a generally large DOM already (the Overview table itself lists every system), is a textbook cause of
"everything feels sluggish" -- large DOM = slower event dispatch/reflow globally, not just on that one card,
which matches "delay when clicking ANYWHERE" better than a localized bug would. Fixed by capping the card to
50 systems total (5 visible + 45 in the expander), with an explicit "+N more -- see a deliverable's 'Systems
Ranked by Issue Severity' section for the full list" pointer to where the COMPLETE list already properly lives
(capped, tabular, from v5.6.199/200) -- a GUI "quick glance" card was never meant to hold nearly the entire
fleet. Verified live: re-measured the same real fleet after the fix -- exactly 50 `div[onclick]` row elements
now, down from 964. **Not yet confirmed this was the user's actual full felt experience** (couldn't measure
click-to-paint latency directly from this environment) -- but it's a real, substantial, newly-introduced
unbounded-DOM-growth bug on the landing tab, fixed and verified at the DOM-node-count level; worth asking the
user to confirm the app feels responsive again after updating, and treating as NOT fully closed out until
they do.

**23. Feature Matrix header/data misalignment (shipped, v5.6.201).** User screenshot: Action Planner's
Per-System Feature Matrix (`_renderFeatureAdoptionSection()`, GUI-only, not a Word export) showed each row's
ARP/SnapMirror/HA/AutoSupport/Score icon sitting well to the right of its own column header. Root cause: data
cells use `tdStyle` (`text-align:center`), but the `<th>` headers were built via `_sth(thStyle, ...)` where
`thStyle` is always `text-align:left` -- a plain CSS alignment mismatch between header and data, not a
`_dxParse`/docx-table-parsing issue (this table is GUI-only HTML, no Word export path touches it). Added
`thCenter` (`thStyle` with `text-align:center`) and used it for the ARP/SnapMirror/HA/AutoSupport/Score
headers, keeping `thStyle` (left) for 'System' to match its `tdLeft` data cells. Verified live via a real DOM
path (Action Planner > New Clicks scope > Generate Plan > real click on the "✅ Feature Adoption" tab button,
not a direct function call) by reading `getComputedStyle(...).textAlign` on both the header and first-row data
cells for every column -- all 6 now match exactly (System: left/left, the other 5: center/center).

**22. New health-score/issue-ranking sections converted to real tables (shipped, v5.6.200).** User: "make the
changes to the deliverables comply with the standard document formats... we need consistency" -- flagged that
point 21's "Systems Ranked by Issue Severity" list and point 20's per-system Health Score "worst" list were
both comma-joined/one-per-line prose, not real tables, despite being exactly the kind of multi-row numeric
data `_dfTable()` exists for (and despite this session having already fixed several "table rendered as
run-on prose" bugs elsewhere). Converted both to real `_dfTable()` output: `_dfSystemIssueRankingText()` now
returns a table (System/Customer/Crit Risks/High Risks/Crit CVEs/High CVEs/Open Cases/AIQ Score columns) with
the "+N more" truncation note appended after the table rather than inside it; new
`_dfSystemHealthScoreWorstTable(hs)` does the same for the health-score worst-list wherever it appears as its
OWN dedicated multi-line section (Executive Risk Assessment, Account Handover Brief). **Deliberately left
alone** the short ONE-LINE summary-bullet usages in the TAM Success Plan and QBR Pack (e.g. "Active IQ
Per-System Health Scores: 4/4 systems... Lowest-scoring: sys1 (42), sys2 (65)") -- those are single sentences
embedded among sibling one-line prose bullets (Security Fix Floor, Critical NetApp Issues, Support Cases) in
the same section, and forcing a single sentence into a table would be inconsistent with THAT section's own
established convention, not more consistent with it (same judgment call already made and documented earlier
this session for other "single fact in a sentence" lines). Verified live: both new tables parse as real
`_dxParse(...)` table blocks (not prose) against real data with synthetic health scores set on 4 real systems,
across all 3 places they appear (Executive Risk Assessment, Account Handover Brief, and the TAM Success
Plan/QBR Pack's issue-ranking section specifically -- which, unlike the health-score worst list, IS its own
dedicated section in all 4 documents and was always meant to be tabular from point 21).

**21. Systems ranked by issue severity, worst first (shipped, v5.6.199 -- see point 22 above for a follow-up
formatting fix).** User, immediate follow-up to point
20: "give a breakdown in the tool, and the reports/deliverables of the issues identified with the individual

**21. Systems ranked by issue severity, worst first (shipped, v5.6.199).** User, immediate follow-up to point
20: "give a breakdown in the tool, and the reports/deliverables of the issues identified with the individual
systems, worst first." Checked what already existed first (again -- this is now the standing discipline for
every "wire in X" ask this session, after getting burned twice on point 20): found `renderNeedsAttention()`
(Overview tab's "Needs Attention" card) already ranked systems by risk count, but capped at a fixed top 5, GUI-
only, no deliverable equivalent, and using only critical/high RISK counts (not CVEs, cases, or the new Health
Score). Nothing else in the codebase ranked systems by combined issue severity.
- New shared `_dfSystemIssueRanking(systems)` (app.js, right after `_dfSystemHealthScores`): a composite score
  per system -- critical risks x10, high risks x4, medium risks x1, critical CVEs x6, high CVEs x2, open
  support cases x2, plus (when Active IQ reports a Health Score) `max(0, 70 - score) x 0.3` so a system that
  scores badly on Active IQ's own metric for reasons this app's risk list doesn't separately raise (lifecycle,
  firmware currency, uptime, etc.) still surfaces. Same weighting SHAPE as the pre-existing Customer Portfolio
  ranking (`riskScore` at ~line 10724, customer granularity) -- there was no system-granularity equivalent of
  that before this. Only returns systems with score > 0 (a clean system doesn't appear as a trailing zero).
  `_dfSystemIssueRankingText(systems, limit)` is the shared plain-text renderer every deliverable below uses,
  capped (default 15) with an explicit "+N more" rather than dumping a multi-thousand-line list for a large
  fleet -- confirmed live against the real 1052-system fleet this needed (886 systems had at least one issue).
- **GUI**: `renderNeedsAttention()` now uses this same composite score instead of its own simpler risk-count
  sort (so "worst" means the same thing here as everywhere else), and instead of hard-capping at 5, shows the
  top 5 plus a native `<details>`/`<summary>` "Show N more systems" expander revealing the full ranked list --
  deliberately no new DOM element/HTML file change, since a `<details>` block works inside the card's existing
  container. Preserved the pre-existing behavior that a system with ONLY a soon-expiring contract (zero issue
  score) still surfaces here, by merging the ranking back over every filtered system rather than only the ones
  `_dfSystemIssueRanking()` itself returns (contract urgency isn't part of that score).
- **Deliverables**: new "SYSTEMS RANKED BY ISSUE SEVERITY (Worst First)" section added to the TAM Success
  Plan, QBR Pack, Executive Risk Assessment, and Account Handover Brief -- the same 4 documents point 20's
  Health Score work touched, for consistency.
- **Verified against real data**: called `_dfSystemIssueRanking(state.systems)` directly against the real
  1052-system fleet (top-ranked system: CTPNAPROD-N1, 4 critical risks/45 high risks/14 critical CVEs/77 high
  CVEs, score 502) and confirmed via real `downloadDeliverable()` calls that all 4 deliverables and the real
  Overview tab DOM (`renderNeedsAttention()` called via a real function call after `switchTab('overview')`,
  confirming the `<details>` element and its "Show 898 more systems" summary text) render correctly.

**20. Real per-system Active IQ Health Score + two self-inflicted bugs found and fixed (shipped, v5.6.198).**
User: "wire in ONTAPSystem.healthScore... i want to report on this in all the metrics and deliverables."
**Before writing anything, checked whether this already substantially existed** (the exact discipline point
19 below says to follow, and almost didn't this time) -- searched for `healthScore` and found it VERY MUCH
already did: `summary(nagpId).healthScore` (a per-CUSTOMER 0-100 NetApp-calculated score with a 9-factor KPI
breakdown) was already fully wired into the Overview tile, QBR Pack, and Risk & Remediation Brief from an
EARLIER session (state.tamCustomerHealthScores / state.tamOfficialHealthScore, `_officialHs` in app.js). The
genuinely new thing `ONTAPSystem.healthScore` offers is PER-SYSTEM granularity -- the existing customer/fleet
scores can't tell you which specific system is dragging the number down.
- **Checked the field-count limit live before shipping** (the exact hazard this codebase's own comments warn
  about, "Maximum height (field count) limit exceeded"): the full KPI breakdown (same shape already used for
  the per-customer score) pushed BOTH of the harvester's main system-detail query tiers (`SYSTEMS_FIELDS_TAM`
  and `SYSTEMS_FIELDS_EFFICIENCY`) over Active IQ's limit -- confirmed live with a standalone test script
  reusing `server.py`'s `_gql`/token-exchange. Trimmed to just `healthScore { overallHealthScore calculatedAt }`
  (no `kpis`), re-tested live, both tiers pass with real data (81, 86, 64, 60, 70, 77... -- real, varied scores).
  KPI-level detail remains available only at the fleet-wide/per-customer level, which already had it.
- **Found and fixed two real bugs in my OWN v5.6.197 work while doing this** (both would have shipped
  silently broken if this session hadn't continued):
  1. A duplicate Python dict key: v5.6.197 added a second `"downtimeEvents"` key to the `systems_out` dict
     (wrongly shaped -- a plain list) when a CORRECT, pre-existing `"downtimeEvents"` mapping (the real
     `{totalCount, events}` shape `computeFleetUptimeSummary()` already consumes) was already there from an
     even earlier session. Python dict literals are last-key-wins, so the earlier session's correct mapping
     silently won and my new key was dead code -- but the app.js code I wrote to consume it
     (`_lastFailoverEvent`) assumed MY wrong shape, so it would have thrown `.filter is not a function` at
     runtime the first time a real takeover event was encountered. Found by re-discovering that
     `computeFleetUptimeSummary()` (a whole existing, shipped fleet-uptime-rollup feature I hadn't noticed) was
     ALREADY reading `s.downtimeEvents.events`. Removed the duplicate key; fixed `_lastFailoverEvent` to read
     the correct shape.
  2. `enrichSystemTelemetry()` was silently dropping `mcDrClusterName`/`mcDrClusterId` -- that function rebuilds
     an explicit new object rather than spreading the harvested source (documented in its own code comment,
     which I read but the implication didn't register at the time), so any field not explicitly listed in its
     `return {...}` is silently discarded. v5.6.197's whole MetroCluster real-partner fix was tested only
     against hand-built synthetic objects that bypassed this function entirely, so the test passed while the
     real feature was dead on arrival -- `s.mcDrClusterName` was always `undefined` on real enriched systems,
     silently falling back to name-inference every time. Added both fields to the `return` object; re-verified
     by round-tripping a synthetic raw object through the REAL `enrichSystemTelemetry()` this time.
  **Lesson for next session, stated plainly so it isn't repeated a third time: a new harvested field is not
  "verified" until it's been round-tripped through `enrichSystemTelemetry()` (not tested against a hand-built
  object that skips it), and a new query field is not "safe" until tested live against the ACTUAL query tier
  text in `server.py` (not a minimal standalone query) for Active IQ's field-count limit.**
- Wired the (corrected) per-system score into: the Overview tile's health-score subtitle (appended "Lowest
  system: X (N)", no new DOM element needed), TAM Success Plan, QBR Pack, Executive Risk Assessment (new
  "ACTIVE IQ PER-SYSTEM HEALTH SCORES" section), and Account Handover Brief (new section 7a). Shared logic in
  one new function, `_dfSystemHealthScores(systems)` (app.js, right after `_dfNonCveParityVersion`).
- **Verified end-to-end against real data**, not just synthetic: took 4 real systems from a real customer
  scope (New Clicks), temporarily set synthetic-but-realistic `aiqHealthScore` values on them (42/88/65/70,
  average 66), and confirmed via real `downloadDeliverable()` calls that all 4 deliverable text outputs AND
  the real Overview tile DOM element show the correct average and lowest-scoring systems, then cleaned up the
  temporary test values from `state.systems`.

**19. Real MetroCluster DR partners + recorded downtime events (shipped, v5.6.197 -- see point 20 above for two
bugs found in this work and fixed in v5.6.198).** User, from a screenshot

**19. Real MetroCluster DR partners + recorded downtime events (shipped, v5.6.197).** User, from a screenshot
of the MetroCluster Configuration & DR Health card showing all 4 real clusters as "0 + 4 unpaired" / "not
identifiable": "make something meaningful from the metrocluster information. there must be something in the
api" -- pushed back on the app's existing claim that Active IQ doesn't report MC partners. **Did a live
GraphQL schema introspection before assuming the user was right or wrong** (same discipline as every other
live-data feature this session): checked `Cluster` and `System`/`ONTAPSystem` type fields and the root Query
type for anything metro/mediator/switchover/partner/auso-related. Confirmed Mediator/AUSO/switchover
genuinely have NO field anywhere in the schema (the app's claim about those was already correct, unchanged).
**But found `ONTAPSystem.drCluster` (and `drPartner`/`partner`/`cluster`) -- never previously queried by this
app.** Verified live against the real fleet (not just schema presence): queried 16 real MetroCluster systems
and confirmed `drCluster` is genuinely populated and reciprocal (PRDSAN04's `drCluster.name` is "PRDSAN03",
PRDSAN03's is "PRDSAN04"; same for a second real pair, NACLUSA50-A/B). This explains the original bug report
exactly: the old cluster-name-inference heuristic (`s/^[a-z0-9]{2,5}[-_]//` prefix strip) fails for a fleet
named PRDSAN01/02/03/04, which don't follow a "site-prefix + shared suffix" naming convention at all.
(`drPartner`/`partner` turned out to just duplicate the in-cluster HA partner node, not a genuine cross-site
node identity -- not used.)
- **server.py**: added `drCluster { id name }` to the `ONTAPSystem` query (both occurrences,
  `replace_all`), output as `mcDrClusterName`/`mcDrClusterId` on each system.
- **app.js**: new shared `_dfMcPairs(clusterNames, byCluster)` (app.js, right before `_dfMetroClusters`) pairs
  clusters using real `mcDrClusterName` data first, falling back to the old name-inference heuristic only for
  a cluster Active IQ doesn't report a partner for. Returns `[clusterA, clusterB, isRealData]` tuples. Used by
  `_dfMetroClusters()` (deliverable text), `renderMetroClusterStatus()` (the Technical Audit tab's GUI card --
  column renamed "DR partner", each row marked "✓ confirmed" or "(inferred from name)"), and the
  Technical Solution Proposal's MetroCluster markdown table. All three previously had their own separate
  copy-pasted name-inference logic; now share one function.
- User immediately followed up: "do the same for snapmirror, and all the other gaps in the tool." **Checked
  SnapMirror live first**: `Cluster.snapMirrorRelationships` and any root-level SnapMirror field -- confirmed
  the ONLY field anywhere is `SnapMirrorRelationships.totalCount` (an aggregate count). No relationship-level
  detail (destination, lag, health) exists in this API at all. The app's existing "SnapMirror status not
  reported by Active IQ" language was already accurate -- **no fix needed, confirmed a genuine limit, not
  another oversight.**
- While auditing broadly for "other gaps," found two more real, previously-unused fields on `ONTAPSystem`:
  `downtimeEvents` (real recorded downtime/takeover events -- confirmed live: a real system, OOBA-C30-02, had
  a genuine `category: "Takeover"` event on 2026-06-17 with EMS code `wafl_replay_completed_1`, a summary, and
  a 1-second outage duration; rare in practice, only 1 of 165 systems in the test account had any recorded
  events, but genuinely populated where present) and `healthScore` (a real Active-IQ-computed
  `overallHealthScore` 0-100 with a `kpis` breakdown by category -- asup/osFreshness/firmware/
  securityHardening/sustainability/uptime/eos/addon/techRefresh -- confirmed live with real varied values:
  81, 86, 64, 60, 70, 77...). **Wired in `downtimeEvents` this session** (directly fills an explicitly-flagged
  gap in the code itself, `importTrackerItemsFromScope()`'s DR-failover-test tracker items, which used to
  unconditionally say "Active IQ has no record of whether a failover was ever actually tested" -- now cites
  the real event with date/category/outage duration when Active IQ has recorded one). **Did NOT wire in
  `healthScore`** -- that's a bigger, more architectural decision (whether/how to show Active IQ's own
  computed score alongside or instead of this app's locally-computed `computeAccountHealthScore()` and
  similar functions), left for a deliberate follow-up rather than a drive-by change. **"All the other gaps in
  the tool" was NOT exhaustively swept** -- only MetroCluster (fixed) and SnapMirror (confirmed genuine) were
  checked to completion this session; other "not reported by Active IQ" claims in the codebase (port/WWPN
  detail for StorageGRID/E-Series, transit/logistics hub status, Success Plan outcome tracking) were NOT
  re-verified against a live schema and should not be assumed either confirmed-accurate or newly-fixable
  without doing the same live-introspection check first.
- **Verified**: `_dfMcPairs`/`_dfMetroClusters` tested with synthetic data shaped exactly like the real live
  API responses (both a case with real `mcDrClusterName` data confirming a pair, and a case with none falling
  back to "not identifiable") -- correct in both directions. `_lastFailoverEvent`'s detail-string construction
  verified against the exact real event fields returned live. Syntax-checked both `app.js` (`new Function()`
  in the browser) and `server.py` (`python -m py_compile`). **The running dev server's CACHED harvest data
  does not yet have `mcDrClusterName`/`downtimeEvents`/`aiqHealthScore` populated** (the last one added in
  v5.6.198, see point 20 above) -- both were verified via direct one-off GraphQL calls (same `_gql`/token-
  exchange reuse pattern as every other live-schema check this session) and, for the app.js side, by feeding
  synthetic-but-realistic values through the REAL `enrichSystemTelemetry()` and real deliverable-compile
  functions -- not by loading real data through a fresh harvest in the running app. A real harvest re-run
  (server restart + `/api/harvest?force=1`, several minutes) is needed before the running dev instance's own
  UI shows any of this live from a real harvest, though the code is correct and the packaged `dist/` build is
  fully synced.

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

**Git:** branch `main`. v5.6.192 through v5.6.203 each committed individually after this session's work
(app.js, CHANGELOG.md, version.json, CLAUDE.md, and the synced `dist/app.js` +
`dist/NetApp_AIQ_Advisor/_internal/app.js` + `.exe` each time; v5.6.197 and v5.6.198 also synced
`dist/NetApp_AIQ_Advisor/_internal/server.py` since both touched the harvester (v5.6.199 through v5.6.202 were
app.js-only, no server.py sync needed) -- note PyInstaller does NOT produce a loose `server.py` in its own
build output (it's compiled into the exe), so that sync step copies directly from the repo root's `server.py`,
matching what past sessions did). Exe rebuilt via PyInstaller (`build/AIQscraper.spec`, note the spec lives
under `build/`, not the repo root) to `%LOCALAPPDATA%\Temp\aiqbuild192`..`aiqbuild202`, never
`build/build_windows.bat`. No HTML changes this
session.

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
