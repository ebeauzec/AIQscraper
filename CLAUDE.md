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

## Session handoff -- 2026-09-27/28 (Windows dev station, v5.6.134 -> v5.6.144)

Continues the same stretch's earlier v5.6.85 -> v5.6.134 work (rear-panel accuracy program, hardware-docs
harvester -- see git log / CHANGELOG.md for that range). Everything below is pushed to `main`.

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
