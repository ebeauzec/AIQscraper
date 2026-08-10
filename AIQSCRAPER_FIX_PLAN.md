# AIQscraper Fix Plan — Round 3: enrichment optimizations implemented

Rounds 1 (contract-null cascade, asup_parser, mock badge, sustainabilityScore/
osVersions/recommendations wiring) and 2 (native `Risk.cves` wiring) are done —
see git history / prior versions of this file. This round implements the
three enrichment-scheduler optimizations from the last audit. All changes are
uncommitted in the working tree (`server.py`, `app.js`) — nothing pushed.

**Mid-session conflict note:** partway through this round, my Round 2 `app.js`
edits (the `cveDetails` wiring) were found reverted to the last commit — some
activity in your other Antigravity session overwrote them. I flagged it,
reapplied all three edits cleanly against the current file state, and
verified nothing else in `app.js` had changed underneath them. Wanted you
aware in case that revert was intentional on your end and I've now
re-introduced something you meant to remove.

---

## Implemented

### 1. Staleness check before every scanner

Added `EnrichmentScheduler._file_age_hours(path)` — reads a target file's
`lastUpdated` field (falls back to file mtime) and returns its age in hours.
Every scanner group now checks this before running and skips with a logged
reason (`{'skipped': 'fresh'}`) if the file is already newer than the
configured interval. Confirmed live: `[ENRICH] [5] version_catalog.json is
5.7h old (< 6h interval) — skipping`.

This directly fixes the redundant-rescan problem from the audit — a desktop
app opened/closed several times within one interval window no longer
re-triggers full scans of data that's already fresh.

### 2. Scanner 6 (KB crawl) split onto its own long interval

`EnrichmentScheduler` now runs **two independent timers**:
- Fast group (scanners 1-4: CISA KEV, PSIRT, NVD, EPSS) — default 6h,
  configurable via existing `enrichIntervalHours` config key.
- Slow-crawl group (scanner 6: KB/doc crawl) — new, default **168h (7 days)**,
  configurable via new `kb_interval_hours` param on `update_config()`.

This was the "long pole" problem from the audit: scanner 6 alone could run
80-150+ sequential HTTP requests. It no longer blocks the fast, high-value
security scanners, and a short desktop session now reliably gets fresh
security data even if it never reaches the slow crawl.

### 3. Mid-implementation discovery: scanner 7 had the same problem

While implementing #2, live testing revealed **scanner 7 (reference library —
firmware/EOA/IMT harvest via `reference_harvester.py`) is itself a multi-
minute crawl** (docs.netapp.com + GitHub + PyPI + kb.netapp.com, ~2s/request,
100+ requests) — comparable to scanner 6, not "fast" as originally grouped.
I hadn't fully appreciated this when scoping the original plan. Fixed by
moving it onto the same slow-crawl timer as scanner 6, each independently
staleness-gated against its own target file (`knowledge_base.json` for
scanner 6, `security_bulletins.json` for scanner 7).

### 4. Parallelization (safe scope) + correctness fix for the new topology

Investigated running scanners 1-4 concurrently via `ThreadPoolExecutor`.
**Discovered a real correctness constraint**: scanners 1, 2, 3, 4, and 7 all
do a load→mutate-in-memory→write cycle on the *same* `security_bulletins.json`
file. True concurrent execution of these against each other would race —
whichever writes last silently clobbers the other's additions. A clean
fetch/persist-phase split across all five functions would be a much larger,
riskier refactor, so I did not attempt full parallelism within that group.

What *is* now genuinely and safely parallel: scanner 5 (version catalog,
writes only `version_catalog.json` — fully disjoint from bulletins) runs
concurrently with the whole bulletins-writing group via a 2-worker
`ThreadPoolExecutor`.

To keep this safe now that bulletins.json can be touched by **two
independent timers** (the fast group, and scanner 7 on the slow-crawl timer),
added a module-level `_bulletins_lock` and wrapped every bulletin-touching
scanner call in it — so the fast group and scanner 7 can never race each
other even if their timers happen to fire close together, at the cost of a
brief mutual block only in that rare overlap case (uncontended 99%+ of the
time given the 6h vs 168h interval mismatch).

---

## Live-verified results

Restarted the server three times during implementation (killing stale
processes carefully each time to avoid port conflicts) and confirmed via log
output and the `/api/enrich/status` endpoint:

- **Fast group runtime: 325.8s → 8.5s** once scanner 7 was correctly moved out
  — a ~38x reduction, since scanner 7's multi-minute crawl was the actual
  long pole hiding inside what I'd originally called the "fast" group.
- Staleness skip fired correctly for `version_catalog.json` (5.7h old) and
  `knowledge_base.json` (5.7h old) in the same run.
- Scanner 7 (reference library) started independently on the slow-crawl timer
  *after* the fast group had already finished and reported results — confirms
  it's no longer blocking the fast path.
- `server.py` compiles cleanly (`py_compile`, `doraise=True`) after every edit.
- Full app load in-browser (earlier round) showed no console errors; this
  round's changes are server-side scheduling logic plus a small, previously-
  verified `app.js` CVE-wiring diff — not re-tested in-browser this round
  since the UI-facing behavior didn't change, only backend scan timing.

## Not implemented — needs your input

**Full parallelization of scanners 1-4 against each other** (not just against
scanner 5) would require splitting each of those four functions into a
"fetch" phase (safe to run concurrently, no file access) and a single
combined "persist" phase (runs once, after all four fetches complete). This
is the *correct* way to get real speedup on the bulletins-writing group,
since the network-bound fetches are what actually dominate their runtime —
but it touches the internals of `scan_and_persist_advisories()` (also used by
other callers I'd want to check don't break) plus three other scanner
methods. I scoped this out as a larger, separate piece of work rather than
force it into this pass.

## Config surface (for reference)

`EnrichmentScheduler.update_config()` now accepts:
- `interval_hours` — fast group cadence (existing, unchanged default 12,
  overridden to 6 via `aiq_config.json` → `enrichIntervalHours`)
- `nvd_api_key` — unchanged
- `kb_interval_hours` — **new**, slow-crawl cadence, default 168 (7 days).
  No existing config key wires this up yet — if you want it user-configurable
  from Settings & Config, that's a small additive UI change I haven't made.
