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

## Session handoff -- 2026-09-27 (Windows dev station, v5.6.134 -> v5.6.138 + repo rename + docs audit)

Continues the same day's earlier v5.6.85 -> v5.6.134 work (rear-panel accuracy program, hardware-docs
harvester -- see git log / CHANGELOG.md for that range). Everything below is pushed to `main`.

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

**Still open / not done:** rear-panel program has no layout yet for FAS8000, older FAS25xx/26xx, unnamed
StorageGRID models, or cloud platforms (unchanged from earlier). LEGAL.md/ARIA_FIX_PLAN.md still not
content-audited (ARIA_FIX_PLAN.md looks obsolete, worth archiving).

**Git:** branch `main`, pushed through `88b453e`. Working tree also shows harvest data files modified by the
running server (`data/*.json`) -- not part of this work, don't commit them with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart (kill the running
python process, relaunch) -- app.js is served fresh on every page load and needs neither.
