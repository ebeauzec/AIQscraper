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

## Session handoff -- 2026-09-27/28 (Windows dev station, v5.6.134 -> v5.6.150 + docs)

Continues the same stretch's earlier v5.6.85 -> v5.6.134 work (rear-panel accuracy program, hardware-docs
harvester -- see git log / CHANGELOG.md for that range). All code changes below are pushed to `main` through
`d2c2839`; the competitive-analysis doc update (below, no code/version change) is pending commit as of this
handoff -- push it before starting new work if it isn't already in `git log`.

**Also today, docs-only, no version bump:** asked to compare ARIA against NetApp's own Digital Advisor
product and update docs to reflect it. Researched live via NetApp's docs/community pages (not from training
memory), then verified every claim against ARIA's actual code before writing anything down -- full writeup
is in `CONTEXT.md`'s new "Competitive positioning vs NetApp Digital Advisor" addendum (near the end), with
a pointer from section 1. Don't re-derive this from scratch next time; read that addendum first.
**Headline finding**: `runIMTInteropCheck()` (`app.js` ~13441) is a complete, sophisticated engine --
cross-references fleet ONTAP versions against `IMT_INTEROP_MATRIX` (VMware/OTV, Trident, SnapCenter, with
min/max ONTAP versions and baked-in CVEs) -- with **zero call sites anywhere**. Its `detectedSignals` input
is also never built. This is the highest-value, lowest-effort next feature: wiring it into the upgrade-plan
deliverable would let ARIA flag third-party compatibility breaks Digital Advisor's own Upgrade Advisor
doesn't check (it's ONTAP-internal-prerequisite-only). Not yet implemented -- user was asked whether to do
it now and the session moved to docs first; **this is the natural next task to pick up**.
Also corrected a claim from the first pass of this analysis: sustainability scoring was wrongly listed as an
ARIA strength -- `computeHonestSustainabilityScore()` is a pass-through of Active IQ's own field, not an
independent model. Parity at best, not an edge. Don't repeat that claim in any deliverable copy.

**Also today, part 6 (v5.6.150):** the shelf-firmware investigation from part 5 led to a screenshot of "0/42
unknown" on the Firmware Currency Shelf FW tile -- turned out to be demo/mock mode, not live data, once asked.
No curated `MOCK_SYSTEMS` profile ever carried `shelvesSummary` (some have real, detailed `shelves` hardware,
just never paired with the separate firmware-currency field `_resolveShelfModules()` reads) -- every demo
system showed unknown regardless. Added `_demoSynthShelves()`/`_demoShelfSummaryForModule()` (`app.js` ~8014),
synthesizing shelf module + firmware from the same `REFERENCE_LIBRARY_FIRMWARE_BASELINES` table the real
feature uses -- derives from existing curated shelf hardware's own module name when present (so the two
fields can't disagree), synthesizes both together when neither exists. **Caught by testing, not inspection**:
first pass gave Cloud Volumes ONTAP demo systems fake physical shelves -- added an explicit virtualized-
platform exclusion (CVO/ONTAP Select/Astra) before fixing forward. Verified live: 108/108 physical ONTAP demo
systems now have shelf firmware (was 0/108), realistic 55/40/13 current/behind/unknown split, 0 virtualized
systems wrongly populated. **Also answered directly when asked**: yes, real (non-demo) shelf firmware IS
being harvested correctly -- 107/1393 live ONTAP systems, verified with real installed-vs-recommended
version numbers (e.g. IOM12 0401 installed vs 0412 recommended) -- the earlier sparse-data finding (part 5)
was real upstream telemetry gaps for specific customers, not a harvest bug, already correctly not touched.

**Also today, the biggest one, part 5 (v5.6.149):** user noticed a node showed no LIFs on its rear panel.
Traced it all the way down: 0 vservers -> the cluster's SVM/capacity/HA data was entirely missing ->
`server.py`'s `clusters()` GraphQL query (~2062) takes NO watchlist argument at all, unlike `systems()`
(explicitly per-watchlist) -- it only sees the token's default privilege scope. Once watchlist auto-discovery
started finding a real account's full set (v5.6.142), that unscoped call kept returning a real but badly
incomplete count (109 clusters for 2900+ systems -- ~27/cluster, implausible for real HA pairs). An existing
"retry scoped to each watchlist" fallback for exactly this only fired when the unscoped call returned exactly
0 -- never for non-zero-but-incomplete, so it never kicked in. Fixed: now always runs when watchlists are
known, merging by cluster id. **Verified live, the payoff**: NetApp account's cluster count 43 -> 313; ONTAP
systems with SVM/LIF data 14% -> 64% of the fleet (196/1393 -> 890/1393). Several watchlists that were
COMPLETELY empty (Vodacom Tanzania, IEC ONTAP, Mauritius Commercial Bank) are now fully populated.
Asked explicitly to check for other silent caps -- found one more, already close to being hit: the loop that
resolves each watchlist's system membership for the sidebar was hard-capped at `[:20]`; a real account now
has 23 watchlists, so the last 3 (Barclays/AXA/Orange, 97/148/116 systems) silently never resolved. Cap
removed (risks/cases loops elsewhere already had none). Also investigated a related report (shelf/motherboard
firmware showing unknown for many systems) with direct standalone GraphQL probe scripts against the live
API, not just reading code -- confirmed it's real data, isolating to ONE customer (Google: 0/30 systems with
firmware reported, clean empty responses, no errors) while a same-day newly-discovered watchlist for a
DIFFERENT customer (STC) reports perfectly (30/30) -- restricted AutoSupport telemetry on that one customer's
side, not a scoping bug, nothing changed. Systematically swept the rest of the file for the same cap-class
bug: systems/risks/cases/E-Series-capacity/shelf-summary loops all already iterate every watchlist with no
cap -- only generous pagination safety bounds (5,000 systems/watchlist) remain, not a real-world risk.
**Lesson for next time**: watchlist auto-discovery (v5.6.142) exposed a LOT of latent scoping assumptions
elsewhere in the harvester that were written back when accounts only ever had a handful of watchlists (or
effectively zero, since discovery was broken) -- if something looks like sparse/missing data after a big
watchlist-count jump, check whether the query touching it takes a watchlist argument at all before assuming
the upstream data is just sparse.

**Also today, part 4 (v5.6.148):** user hit a "Sync failed: Sync timed out after 6 minutes" alert telling
them to check the launcher. Checked `/api/sync-status` live while it was showing -- `isSyncing: true`, well
past 6 minutes -- the server was harvesting correctly the whole time, the client poll just gave up and threw
a scared, wrong message. Root cause: this session's OWN earlier fix (watchlist auto-discovery, v5.6.142) now
correctly finds a real account's full watchlist set (20 combined across 2 accounts, confirmed live in
`aiq_config.json` -- both accounts' `watchlistId` now blank, relying entirely on auto-discovery, up from
silently finding 0 before). 20 real watchlists x their own paginated queries x tier-fallback retries is
genuinely more work than the pre-existing 6-minute timeout (written before this fix existed) was ever sized
for. Fixed two ways: raised `POLL_TIMEOUT` to 20 minutes, and changed what a timeout DOES -- the harvest runs
server-side independent of the browser tab, so a client timeout was never really "sync failed", only this
page giving up watching. It now falls back to loading the current cache and shows "still refreshing in
background" instead of an alarming failure alert. **Also fixed, same session, user request**: the sidebar's
Active IQ Watchlists list was in harvest/discovery order (meaningless to a reader, much more noticeable now
that a real account's full 20-watchlist list is visible for the first time) -- sorted alphabetically.
**Worth remembering**: any future feature that increases legitimate per-harvest work (more watchlists, more
accounts, richer per-system queries) should be checked against this same client-side poll timeout before
shipping -- it's not auto-scaling, it's a hardcoded constant that can silently fall behind reality.

**Also today, part 3 (v5.6.147):** user said to go ahead and fix the HCI gap flagged in v5.6.146. Added a
4th `_platformFamily()` bucket, `'element'`, for NetApp HCI storage nodes (Element OS/SolidFire) -- detected
via NetApp's own naming convention (`H<model>S`/"SolidFire" = storage node = Element OS; `H<model>C` =
compute node = a real ONTAP Select instance, correctly stays `'ontap'`, confirmed live via its real ONTAP
9.12.1 version). Audited every `_platformFamily(s) === ...` call site (~90 matches) first: almost all of
them already filter explicitly on `=== 'ontap'` for feature scoring/CLI/reports, so the new bucket was
excluded from ARP/SnapMirror/FabricPool/HA/etc. automatically, no changes needed there. Only the genuinely
three-way branches needed explicit updates: `_nonOntapVerifyLines()`/`_nonOntapRollbackLines()` (were giving
Element OS nodes StorageGRID guidance -- now SolidFire-specific), `enrichSystemTelemetry()`'s `isONTAPBased`
(now excludes `'element'` too, so its `ontapVersion` field returns `null` instead of a bogus Element OS
version), the security-bulletin auto-match (excluded, same false-CVE risk E-Series had), and a handful of
cosmetic family-label maps. Verified live: 9 of 15 real HCI systems (storage nodes) now classify as
`'element'`; the 6 compute nodes stay `'ontap'`; 0 false positives elsewhere in the fleet. Deliberately left
the rear-panel renderer alone -- HCI's missing physical chassis layout is a different bug class, not part of
what was asked.

**Also today, part 2 (v5.6.146):** asked explicitly to check for other misclassified systems beyond "560".
The v5.6.145 fix only touched `_platformFamily()` itself -- the exact same E-Series/StorageGRID guessing was
independently reimplemented (copy-pasted, not shared) in three more places, none checking `platformType`
either: `enrichSystemTelemetry()` (`app.js` ~18022, the core per-system enrichment pass -- drives
`isONTAPBased`, support-level labels, capacity multipliers for EVERY system) and two near-identical
TAM-tab node-visualizer functions that toggle the E-Series Hardware Audit card when switching nodes. All
three now check `platformType`/`_platformFamily()` first, old guessing kept as fallback. Verified live
across the full real fleet (2,450 systems): 0 misclassify now (was 13). Also confirmed no real ONTAP system
false-positives into E-Series from the broadened check. **Found but explicitly NOT fixed**: NetApp HCI
storage nodes (`platformType: "HCI"`, models "H410S-2"/"SolidFire", 9 real systems) run Element OS, not
ONTAP -- `_platformFamily()` has only 3 buckets (storagegrid/eseries/ontap), none for Element OS, so these
fall into `'ontap'` and get scored on ARP/SnapMirror/FabricPool/HA they don't have. Active IQ also reuses
`ontapVersion` to carry Element OS version strings for these (e.g. "12.3.2.3", a format real ONTAP never
uses). The 6 "H410C" compute nodes are fine (real ONTAP Select version reported, correctly ONTAP-based).
Needs a 4th family bucket + a feature-check audit -- bigger than a classification patch, flagged for the
user to decide whether it's worth doing.

**Also today, part 1 (v5.6.145):** a user screenshot of ANOTHER blank rear panel (model "560",
`platformType: "E-SERIES"`) led to a deeper bug than a missing chassis layout. `_platformFamily()`
(`app.js` ~17707) -- which decides ONTAP vs. E-Series vs. StorageGRID for feature scoring
(ARP/SnapMirror/FabricPool/HA), CLI generation, change-verification steps, AND the rear-panel renderer --
**never checked Active IQ's own authoritative `platformType` field**, only guessed family from the
platform/model string (numeric-model regex required exactly 4 digits starting with 28/29/40/57). A 3-digit
E-Series model ("560", an EF560/E5600-family board) fell through every check and was silently treated as
ONTAP everywhere in the app, not just the rear panel. Fixed by adding `platformType` as one more signal to
the same test (kept the old guessing as a fallback). Auditing the blast radius found a second, bigger
instance of the same bug: `_isPlatformStorageGRID()`'s substring list was missing `sg58`, so 12 real
StorageGRID SG5800-family appliances ("SG5860") were ALSO silently misclassified as ONTAP. Fixed. Verified
live: 13 of 215 real E-Series-platformType systems misclassified before the fix, 0 after. **Worth
remembering**: any "why does this non-ONTAP system look wrong" report from now on should start by checking
`_platformFamily(sys)` against the system's own `platformType`, not by assuming it's a missing-layout issue
like the two before it.

**Also today (v5.6.144):** asked explicitly to check for other virtualized platform types beyond ONTAP
Select. Enumerated all 7 `platformType` values in a real fleet -- two needed a look: ASTRA (1 system, has a
real `ontapVersion` despite the odd model name) and HCI (15 systems, models H410S-2/H410C). **ASTRA is
NetApp Astra Data Store, Kubernetes-native ONTAP, no physical chassis** -- hit the identical blank "not built
in" rear panel as ONTAP Select, for the identical reason (`isCloud` didn't match `platformType === "ASTRA"`).
Fixed the same way: `isCloud` now also matches `ASTRA`, card gets Astra-specific copy ("Astra Data Store
(Kubernetes-Native)" / "vNICs provisioned by the Kubernetes cluster network (CNI)"). Verified live. **HCI is
real physical rack hardware, correctly left alone** -- it still shows the blank panel today, but that's the
*other* bug class (missing chassis layout for real hardware, like FAS50/AFX2K earlier), not something this
fix should touch. Noted but not fixed: `_platformFamily()` (`app.js` ~17691) only returns
`storagegrid`/`eseries`/`ontap` -- ASTRA and HCI both fall into the `ontap` catch-all wherever else that
function is used (upgrade paths, CLI generation), not just the rear panel.

**Also earlier today (v5.6.143):** ONTAP Select systems (`platformType: "ONTAP-SELECT"`, model reported as a
VM size like "M300"/"FDvM300", not a real chassis) hit the rear-panel's `isCloud` detection, which only
matched "cloud" in the platform string/type -- so they fell through to the physical-chassis engine and
rendered a blank panel. Fixed by broadening `isCloud` in `renderNodeVisualLayout()` to also catch
`ONTAP-SELECT`, and fixing the "Virtual Appliance" card's provider-label logic (it defaulted to "GCP" for
anything that wasn't AWS/Azure -- would've been wrong for Select) to say "ONTAP Select (Software-Defined)" /
"the VM's hypervisor (VMware/KVM)" instead. Asked explicitly to sweep for other broken REST endpoints using
the same find-the-real-endpoint technique -- found none; everything else is either the confirmed-working
token exchange or GraphQL (a different technique entirely).

**Yesterday's finding (v5.6.142):** Watchlist auto-discovery in `server.py` was
silently broken since it was written -- every candidate REST path/header combo it tried (five of them, across
three call sites) returned 404 or 401. User supplied the real endpoint from NetApp's internal API catalog:
`GET /v2/watchlist/list`, header `authorizationToken` (raw token, **no** `Bearer ` prefix, **not** the
standard `Authorization` header every other call in this file uses) -- that header mismatch is exactly what
produced the 401s on paths that DO exist (e.g. `/v2/watchlist/action`, which turned out to be a *create*
endpoint anyway, not list). Response shape is `results.watchlist[]` with snake_case fields
(`watchlist_id`/`watchlist_name`), different from every shape previously guessed. All three call sites fixed;
confirmed live against a real account whose own `watchlistId` config was always blank (it relied entirely on
this broken auto-discovery) -- now correctly finds all 4 of its real watchlists. **Lesson for next time an API
integration seems unfixable by guessing**: ask the user for the internal API catalog/docs link before trying
more path variations -- this took minutes to fix once the real spec was in hand, versus the prior sessions'
worth of guessing that never found it.

**Yesterday's headline finding (v5.6.141):** `loadConfig()` (reads auth tokens/settings from
localStorage) also unconditionally re-hydrates `state.systems` from localStorage as an undocumented side
effect, EVERY time it's called -- not just at boot. `loadProductionData()` calls `updateStatusIndicators()`
at its own end just to refresh the connection dot; that called `loadConfig()` just for the token; that
silently reloaded the whole system list from localStorage, overwriting the correct, freshly-harvested
in-memory data with whatever `saveSystems()` had just written to localStorage MOMENTS EARLIER in the SAME
sync. That localStorage write is quota-limited (full dataset is 69.6MB on one real fleet, localStorage is
~5-10MB), so `saveSystems()`'s fallback strips `switches`, `vservers`, `risks`, `supportCases`,
`fieldActions`, `securityBulletins`, `hypervisors`, `projections`, `logistics`, `contacts`, `salesHealth`,
`autosupport`, `lifecycleEvents` before writing. Net effect: every single harvest correctly populated ALL of
these fields, then silently wiped them seconds later on the SAME page load, for the whole session. This is
very likely the real explanation behind most "flaky/thin data" reports across the app, not just switches.
Fixed with a `restoreSystemsFromCache` param on `loadConfig()` (default true for the one genuine boot caller;
`updateStatusIndicators()`/`runAPIDiagnostics()` now pass `false`). Confirmed live: switches (295 systems)
and vservers (360 systems) both persist correctly through a full page load now, holding stable over 20+
seconds of polling where they previously always landed on 0. If something STILL looks thin/flaky after this,
check whether it's in that STRIP_KEYS list and whether some other caller reaches `loadConfig()` un-flagged --
that's now the first thing to check, not the harvest query.

**What was asked, in order:** (1) fix the mock/demo data (wrong controller's ports, wrong LIF-to-port roles,
duplicate WWPNs); (2) rename the GitHub repo to ARIA; (3) audit the documentation for staleness; (4) build a
distributable docx of the user-facing docs; (5) another LinkedIn post; (6) make the Action Planner's 19-section
tab row less "lost in the page"; (7) a user screenshot asking why shelf firmware only ever showed the
recommended baseline, never what's installed; (8) propagate that fix through every deliverable and report.

**Demo data fixes (`app.js`, client-side only) -- v5.6.135/136:** `_demoPortBucket()` matches a curated
profile's `networkPorts` to the SAME rear-panel layout bucket as the system's platform label. The LIF remap in
`_demoHydrateSystem` was checking a flattened shape that doesn't exist on the raw objects (real shape is
`v.logicalInterfaces[].serviceConfiguration.dataProtocols` / `.failoverConfiguration.{homePort,currentPort}`) --
rewritten against the real shape. `worldWidePortName` was cloned verbatim from the curated profile with no
per-system substitution, so every demo system sharing a profile had byte-for-byte identical WWPNs (user caught
this from a screenshot: "how can these LIFs all have the same WWPN?") -- now re-derived per system+LIF from a
hash of the serial number, keeping the adapter-index/OUI bytes that already varied.

**Repo rename:** GitHub repo `ebeauzec/AIQscraper` -> `ebeauzec/ARIA` (old URL redirects). Local folder name
unchanged (`AIQscraper`). Used the git-credential-manager's push token, not `aiq_config.json`'s `githubToken`
(read-only scope, 403'd on the rename).

**Docs audit + distributable docx (v1d6ab79, 8db6268, 43b9fc3):** fixed a genuinely broken README anchor
(section renumbering never updated the link), several stale counts (13->15 deliverables, ~24.9k->38k app.js
lines, 5->4 feature checks), `version.json`'s notes field pointing at the wrong version's change, and three more
stale numbers found only by actually rendering the architecture/workflow SVGs for the docx ("14 outputs" ->15,
"PPTX" -> the real txt/md/docx formats, "~33,000 lines" -> ~38,000). Built `docs/distribution/ARIA_Documentation.docx`
(README + LEGAL + LICENSE, python-docx, SVGs rasterized via Playwright since Word can't place SVG) -- not
committed to git (regenerate rather than maintain as a checked-in artifact; it goes stale on every version bump).

**Action Planner navigation regroup (v5.6.137):** the 19-section tab row was one flat list of look-alike
buttons with two tiny inline labels users couldn't find deliverables in. Regrouped into five bordered blocks
(Overview / Risk & Security / Operations & Health / Account & Commercial / gold ★ Customer Deliverables), each
with a one-line description. Section numbers/links/print output unchanged.

**Shelf firmware currency, live (v5.6.138) -- the big one this session:** current shelf module firmware was
never shown anywhere, only the recommended baseline. Root cause, found via live GraphQL schema introspection
against the running server's `/api/graphql` proxy: `Shelf`/`ShelfModuleHardwareModel`/`Bays` genuinely have no
per-shelf firmware field. The field that has it, `ONTAPSystem.shelvesSummary { firmware { currentVersion
recommendedVersion } } }`, was never queried. First attempt added it inline to the main TAM/Efficiency systems
query and broke it -- Active IQ's GraphQL "maximum height" (query-complexity) limit, which silently degraded
the WHOLE harvest to Minimal tier and lost SP/BMC/motherboard/DQP/shelves for every system. Caught it from the
server log, reverted, re-harvested to confirm TAM tier was restored, then re-added `shelvesSummary` as its own
small paginated pass (`server.py`: `SHELVES_SUMMARY_FIELDS`, merged into `all_systems` by serial, same pattern
as the existing E-Series/StorageGRID capacity merge) -- confirmed live for 135+ real systems this session.
Also found two more shelf-firmware code paths that were dead since they were written (found while wiring this
up, unrelated to the API gap): the As-Built Document's shelf table and the Action Plan's shelf-drift detector
were both keyed on `sh.moduleType`/`sh.firmwareVersion`, neither a real `Shelf` field.
New shared helpers in `app.js`: `_shelfModuleCurrency(modName)` (hoisted out of `_renderFirmwareCurrencySection`,
was a local closure) and `_resolveShelfModules(sys)` (prefers Active IQ's own live `recommendedVersion` over the
local reference-library baseline). `computeFleetFirmwareSummary()`'s composite is now SP 20/MB 20/DQP 15/Shelf
15/Drive 30 (was SP 25/MB 25/DQP 20/Drive 30) and every deliverable that quotes "HW Firmware Currency" shows
the Shelf% component -- new "Shelf FW Current" KPI tile and per-system "Shelf:" badge in the Action Planner UI.
Also fixed on request: cluster node pairs were left in raw harvest-fetch order in the Firmware Currency and
Recommended OS Upgrades system lists (could interleave unrelated clusters); both now sort by cluster then
system name.

**Gotchas hit this session:** GitHub anchor slugs replace each space with a hyphen one-for-one, no collapsing --
a naive `re.sub(r'\s+', '-', ...)` audit script produces false "broken link" reports on a double-space left
behind after stripping an em-dash. `_demoHydrateSystem`/`applyDemoDataset()` no-op silently unless
`state.mockMode = true` is set first. The frontend's GraphQL sandbox (`callActiveIQGraphQL`) needs its own
separately-configured refresh token, distinct from the server's harvest credentials -- use the server's
`/api/graphql` proxy directly (curl) for schema introspection instead. Chrome's built-in standalone-SVG viewer
stretches an SVG to fill the viewport with blank padding when screenshotted directly -- wrap it in a plain HTML
page first. GraphQL `__type()` introspection needs enough `ofType { ofType { ... } }` nesting to reach past
NON_NULL/LIST wrappers to the actual named type, and `Cluster` in this schema is an INTERFACE, not an OBJECT
(its own fields still list `shelves`, but a shallow query can appear to return nothing if you only ask for
`fields { name }` without kind on a type you assume is a plain object).

**Switch reporting audit (v5.6.140), which led to finding the above:** user reported "flaky/thin" switch data.
Found two real, separate bugs in `server.py`'s switch assembly (not the loadConfig one): (1) Active IQ's own
`cluster.switches` field can report the SAME physical switch twice under two different device-name suffixes
from two discovery paths (MAC-suffixed vs serial-suffixed, different IP, differently-phrased firmware string)
-- 14 such pairs in one account's harvest; deduped by normalized device name, keeping whichever duplicate is
actually monitored. (2) Server-side model inference only ever checked the device hostname, never the
firmware STRING (which nearly always names the real platform) -- extended to check both, and to recognize
Huawei/HP/Aruba/Ubiquiti in addition to Cisco/Brocade/NVIDIA/Broadcom (`OTHER`/blank dropped 50->22). Also
added two real switch fields Active IQ exposes but were never queried: `network` (reliable role enum) and
`supportContract` (start/end date -- real switch EOS/warranty tracking, shown as a color-coded badge). A
switch seen only via local port connectivity (never in CSHM's inventory) now gets an explicit "Unknown" row
instead of silent absence; one reported by both sources merges into a single row. New shared helpers in
`server.py`: `_sw_norm()`, the `_by_norm` dedup pass before the main switches loop.

**Still open / not done:** rear-panel program has no layout yet for FAS8000, older FAS25xx/26xx, unnamed
StorageGRID models, or cloud platforms (unchanged from earlier). LEGAL.md/ARIA_FIX_PLAN.md still not
content-audited (ARIA_FIX_PLAN.md looks obsolete, worth archiving). The loadConfig() fix only covers the two
callers found this session (`updateStatusIndicators`, `runAPIDiagnostics`) -- worth a quick grep for any other
`loadConfig()` call site before assuming this class of bug is fully closed.

**Git:** branch `main`, pushed through `2773735` (as of the ONTAP Select commit; the Astra commit lands right
after). Working tree also shows harvest data files modified by the running server (`data/*.json`) -- not part
of this work, don't commit them with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart (kill the running
python process, relaunch) -- app.js is served fresh on every page load and needs neither.
