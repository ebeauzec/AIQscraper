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

## Session handoff — 2026-09-26 (cloud session → Windows)

**What happened:** the user asked for an audit of the Action Planner
deliverables (`app.js`'s `compile*` functions — CSP, QBR Pack, MSP
Service Report, Risk & Remediation Brief, Account Handover Brief,
Security Brief, Sustainability Report, Extended Deliverables) because
pasted deliverable output showed numbers that didn't agree with each
other. Found and fixed two real, current bugs; shipped as **v5.6.83**,
already fast-forwarded onto `main` (commit `a53d2c9`). Nothing is
pending review — this is done, not in progress.

### Bug 1 — fake capacity runway (`runwayDays` doesn't exist)

`compileCustomerSuccessPlanText` and `compileMSPServiceReport` averaged
`sys.projections.runwayDays`. That field has **never** been set anywhere
in the harvest — the real field (used everywhere else, including where
the harvester writes it) is `sys.projections.daysToLimit`. The dead
field always failed its `typeof === 'number'` guard, so both documents
silently printed the hardcoded fallback of **120 days**, always,
regardless of real data — directly contradicting their own correct
capacity-forecast/at-risk sections a few lines below (which did use
`daysToLimit`), and contradicting the Risk & Remediation Brief /
Extended Deliverables, which already used the real field. Fixed by
switching both to `daysToLimit`. Traced via `git log -S runwayDays` to
v5.6.40 (`f0679d8`) — a ~40-release-old latent bug, not a regression.

### Bug 2 — efficiency ratio scope mismatch (ONTAP-only vs. all platforms)

The dedupe/compression efficiency ratio must be ONTAP-only (E-Series and
StorageGRID report logical == physical capacity — no real dedup to
count); CSP and Extended Deliverables already did this correctly. QBR
Pack, MSP Service Report (two separate accumulation loops in that one
function), and Risk & Remediation Brief summed physical/logical capacity
across *all* platforms, diluting the ratio toward 1:1 for any account
that also has E-Series/StorageGRID systems — so the same mixed-platform
account could show two different efficiency ratios depending which
deliverable was opened. Fixed by adding the same
`_platformFamily(s) === 'ontap'` filter to all four spots.

### `dist/` — no PyInstaller rebuild was needed or possible here

The cloud session is Linux; PyInstaller doesn't cross-compile, and the
Windows build path needs `pywin32`/`pythonnet` (Windows-only), so a real
`.exe` rebuild can only happen via `build/build_windows.bat` on Windows.
It wasn't needed this time: `launcher.py` serves `app.js`/`index.html`/
`styles.css`/`chart.js` as loose files straight off disk (`sys._MEIPASS`
in the frozen build, i.e. `dist/NetApp_AIQ_Advisor/_internal/`) rather
than compiling them into the `.exe`, and no Python/native code changed.
So only `app.js` had drifted from root in `dist/app.js` and
`dist/NetApp_AIQ_Advisor/_internal/app.js` — both were copied over and
committed (`a53d2c9`). The shipped `.exe` is untouched and will serve
the fixed logic as-is. **Only run `build_windows.bat` if `launcher.py`,
`server.py`, or another Python file changes** — pure `app.js`/
`index.html`/`styles.css`/`chart.js`/`data/*.json` edits just need the
same copy-into-`dist/` step this session did.

### If the user brings more "numbers don't match" examples

This was a targeted audit (traced every shared metric — health score, DR
coverage, risk counts, warranty, MTTR, capacity, efficiency — back to
its source field across all 8 `compile*` functions), not a full line
read of every deliverable. The two bugs above were the only confirmed
issues; risk counts, DR coverage, health score/grade, and warranty all
route through shared helpers (`computeAccountHealthScore`,
`computeFleetDRSummary`, `computeFleetWarrantyStatus`, etc.) consistently
already. If the user pastes a specific deliverable excerpt with a number
that looks wrong, trace that exact figure back through its `compile*`
function rather than assuming it's already covered by this pass.

### Git state as of hand-off

- `main` and `claude/gallant-lovelace-zlrhei` both at `a53d2c9`, pushed,
  clean working tree. No open PR (never asked for one).
- `dist/` binary bundle (`dist/NetApp_AIQ_Advisor/NetApp_AIQ_Advisor.exe`,
  DLLs, etc.) is tracked in git ("pre-built for no-install deployment"
  per `.gitignore`'s comment) but was not recompiled — see above.
