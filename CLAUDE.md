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

## Session handoff -- 2026-09-28 (Windows dev station, v5.6.153 -> v5.6.156)

Continues the same multi-day stretch (v5.6.85 -> v5.6.153 -- rear-panel accuracy program, hardware-docs
harvester, Digital Advisor competitive-differentiation work, VMware Inventory section, trend redesign; see
git log / CHANGELOG.md for that range, don't re-derive). Everything below is pushed to `main`.

**v5.6.154 -> v5.6.155: sortable Capacity Breakdown table + Customer column.** See CHANGELOG.md for the
detail; the one thing worth repeating here since it cost real time: v5.6.154's sort fix was applied to
`index.html` only, and "verified" by calling `sortTamTable(th)` directly from the console, which proves the
function works but NOT that the page wires it up. **`server.py`'s `do_GET()` (~line 8294) rewrites every
request for `/` to `/index_src.html`** specifically so dev-mode edits take effect without recompiling --
`index.html` is only the compiled artifact `build/AIQscraper.spec` bundles into the packaged exe, never what
`python server.py` actually serves. User correctly reported the columns were still unsortable. v5.6.155 fixed
it for real in `index_src.html` (kept `index.html` in sync too) and re-verified with an actual `th.click()`.
**Rule for this codebase going forward: any HTML change must land in BOTH `index.html` and `index_src.html`,
and "verified" means a real DOM event, not a direct function call from the console.**

**v5.6.156, this session's main work: asked to "think more about further differentiating from AIQ Digital
Advisor," then "do both" on the two ideas offered.** Both lean on the same already-established structural
edge -- multi-tenant fusion (`_merge_account_results()`, `server.py` ~1237) -- which every earlier portfolio
feature (EOS overlap, SLA benchmark) surfaced *inside* a single customer's deliverable. These two instead
surface the cross-account view directly.
1. **Portfolio Executive Dashboard** (`app.js`: `computePortfolioExecutiveDashboard()` / `_renderPortfolioExecutiveDashboard()`,
   right before `_renderVMwareInventorySection()`). New Action Planner section (`data-tab-index`/`data-section-index`
   22, in the Overview tab group) -- reads `state.systems` directly, ignores the scope selector entirely, since
   the whole point is seeing every managed customer at once. KPI tiles, fleet-wide 30/60/90-day risk trend
   (`_dfTrendWindows(null)` -- confirmed `_get_fleet_trend()` on the server side already treats a null
   `customer_name` as fleet-wide, no server change needed), an "Accounts Needing Attention" table ranked by an
   urgency score (critical*10 + high*3 + openCases*5 + eosSoon*4), Shared CVE Exposure (CVEs hitting 2+
   customers), Shared Refresh Opportunities (hardware models nearing EOS for 2+ customers). Gated on >=2
   customers existing in `state.systems`, same pattern as `_dfPortfolioBenchmark()`. Verified live against the
   real 78-customer, 2,898-system fleet: 385 critical risks, 109 systems <=1yr from EOS, real per-account
   ranking, a real CVE (CVE-2026-4747) affecting 74 of 78 customers, real FAS8200/AFF-A300/AFF-A220 refresh
   overlaps shared by up to 16 customers -- and confirmed sorting works via a real header click, learning
   applied from the v5.6.155 lesson above.
2. **Cross-customer CVE exposure** (`_dfCveIndex()` extended with a `customers` Set per CVE; new
   `_dfPortfolioCveExposure()` / `_dfPortfolioCveExposureText()`, right after `_dfPortfolioBenchmark()`).
   Unlike the benchmark, this needs no minimum-portfolio-size gate -- even one other exposed customer is
   directly actionable. Rendered as a "Portfolio Exposure" table inserted into the existing Security Advisories
   Action Planner section (data-section-index 3, right after the advisories loop), and as text appended to the
   Security Posture Brief and MSP Service Delivery Report deliverables. Verified live: scoped to one real
   customer (STC), a real CVE found to also affect 73 other customers across 805 systems.

**Build/release housekeeping done this session:** three versions shipped (`APP_VERSION`/`APP_CHANGELOG` in
`app.js`, `version.json`, `CHANGELOG.md`, all bumped each time): 5.6.154 (sortable table, first attempt),
5.6.155 (the real fix + Customer column), 5.6.156 (Portfolio Dashboard + CVE exposure). PyInstaller rebuilt
to a fresh temp dir each time (`aiqbuild5`/`6`/`7` under `%LOCALAPPDATA%\Temp` -- per standing rule below,
never `build/build_windows.bat`), exe + `_internal/base_library.zip` + `_internal/app.js` + `_internal/index.html`
+ top-level `dist/app.js` copied into the committed `dist/NetApp_AIQ_Advisor/` tree each time.

**Still open / not done:** rear-panel program still has no layout for FAS8000, older FAS25xx/26xx, unnamed
StorageGRID models, or cloud platforms. LEGAL.md/ARIA_FIX_PLAN.md still not content-audited. Only the
Capacity Breakdown by Node table (CSM tab) is sortable -- the rest of `index.html`/`index_src.html`'s other
`<th>` elements are still not, out of scope unless asked again. The Portfolio Dashboard's "Accounts Needing
Attention" urgency score is a simple hand-picked weighting (critical*10/high*3/openCases*5/eosSoon*4), not
validated against real TAM triage priorities -- worth a second look if a TAM says the ranking feels off.
Whether the packaged `.exe` itself actually serves correctly given `do_GET()`'s unconditional
`index_src.html` rewrite (which isn't bundled into the exe per `AIQscraper.spec`) is still unconfirmed --
flagged last session, still not checked.

**Git:** branch `main`. v5.6.154, v5.6.155, and v5.6.156 all committed and pushed. Working tree also shows
harvest data files modified by the running server (`data/*.json`) -- not part of this work, never commit
those with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart (kill the running
python process, relaunch) -- app.js is served fresh on every page load and needs neither. **HTML changes must
land in both `index.html` and `index_src.html`** -- `do_GET()` serves `index_src.html` at `/` in dev mode;
`index.html` is only what the packaged exe bundles. **Verify UI wiring with a real DOM event** (`.click()`,
not calling the handler function directly) -- calling the function proves the logic works, not that the page
actually wires it up.
