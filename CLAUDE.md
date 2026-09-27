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

## Session handoff -- 2026-09-27 (Windows dev station, v5.6.134 -> v5.6.136 + repo rename + docs audit)

Continues the same day's earlier v5.6.85 -> v5.6.134 work (rear-panel accuracy program, hardware-docs
harvester -- see git log / CHANGELOG.md for that range). Everything below is pushed to `main` except the
CONTEXT.md/version.json fixes made at the very end of this handoff, which are about to be committed.

**What was asked, in order:** (1) fix the mock/demo data, which was putting the wrong controller's ports
and wrong LIF-to-port roles onto systems; (2) rename the GitHub repo to ARIA and update in-repo references;
(3) audit the documentation (README/CONTEXT/CLAUDE/version.json) for staleness, starting from a broken
anchor link the user found.

**Demo data fixes (`app.js`, client-side only):**
- v5.6.135: `_demoPortBucket()` + `_DEMO_PORT_TEMPLATES` / `_demoSynthPorts()` -- mirrors the rear panel's
  own platform-family dispatch so a fictional demo system's `networkPorts` come from the same chassis shape
  its drawing uses, instead of a loosely-regex-matched, structurally different real profile.
- v5.6.136: the LIF remap that's supposed to keep demo data LIFs (NFS/CIFS/iSCSI/etc.) off cluster-interconnect
  ports was checking a flattened `v.lifs`/`l.homePort` shape that doesn't exist on the raw objects -- it silently
  did nothing. Real shape is nested: `v.logicalInterfaces[].serviceConfiguration.dataProtocols` /
  `.failoverConfiguration.{homePort,currentPort}`. Rewritten against the real shape; excludes FC LIFs (non-Ethernet
  port names) and ifgroup LIFs (`a0a`-style home ports are legitimate, not a mismatch). Verified: 205 data LIFs
  across 108 mock ONTAP systems, 0 mismatches after the fix.

**Repo rename:** GitHub repo `ebeauzec/AIQscraper` -> `ebeauzec/ARIA` (old URL redirects). Local folder name
unchanged (`AIQscraper`). `AIQSCRAPER_FIX_PLAN.md` -> `ARIA_FIX_PLAN.md` (`git mv` + H1 update). README clone
URL and folder-tree root updated. Used the git-credential-manager's push token for the rename API call, not
`aiq_config.json`'s `githubToken` (that one is scoped read-only for enrichment fetches and 403'd on the rename).

**Docs audit (v1d6ab79 + this handoff):**
- README.md: fixed a genuinely broken anchor (`#6-action-planner--all-18-sections` -> `...-19-sections`, the
  tab reorg years ago renumbered sections but the link text/anchor weren't updated) plus three related stale
  numbers ("13 deliverables" -> 15, "5 feature checks" -> 4, one worked example rewritten for consistency).
- `version.json`: `notes` field said "IOM6 upgrade-target check" (that was actually v5.6.105) while attached to
  v5.6.136 (the LIF-remap fix above) -- corrected to match.
- `CONTEXT.md`: header version bumped 4.1.0 -> 5.6.136; file-inventory table sizes/line-counts refreshed
  (app.js is now 38k lines, not 24.9k); Section 4 rewritten for the current 8-tab nav (added Risk & Recommendation
  Tracker and Success Plans, neither existed when Section 4 was last written) instead of the old 6. Sections 5-12
  are still a frozen v4.0.7 snapshot (130+ versions behind) -- flagged with a note at the top rather than rewritten
  wholesale, since fully re-deriving "what's done" for a 38k-line app wasn't in scope this pass. The two dated
  addenda at the end of CONTEXT.md (Deliverables v5.6.83-104, rear panels v5.6.105-134) are current and are now
  the pointed-to source of truth for anything sections 5-12 contradict.
- Not yet done: LEGAL.md and ARIA_FIX_PLAN.md haven't been content-audited this pass. ARIA_FIX_PLAN.md in
  particular is an old "Round 3" enrichment-scheduler fix-tracking doc that may be entirely obsolete/completed --
  worth a look next session for archival rather than just the rename it already got.

**Gotchas hit this session (in addition to the ones below from earlier in the day):** GitHub anchor slugs
replace each space with a hyphen one-for-one and do NOT collapse consecutive hyphens -- a naive `re.sub(r'\s+',
'-', ...)` audit script collapses a double-space (left behind after stripping an em-dash) into one hyphen and
produces false "broken link" reports. My own test harness also produced two false positives while verifying the
demo-data fix: testing `_demoHydrateSystem`/`applyDemoDataset()` without first setting `state.mockMode = true`
(the function no-ops silently otherwise), and initially flagging FC LIFs and ifgroup LIFs as port mismatches
when they're legitimately not on a plain `eNx` Ethernet port.

**Still open / not done (rear-panel program, from the earlier v5.6.85-134 work):** no layout yet for FAS8000,
older FAS25xx/26xx, unnamed StorageGRID models, or cloud platforms.

**Git:** branch `main`. Everything through `1d6ab79` (anchor-link fix) is pushed. This handoff's CONTEXT.md/
version.json edits are uncommitted as of writing -- commit and push them (and this file) together. Working tree
also shows harvest data files modified by the running server (`data/*.json`) -- not part of this work, don't
commit them with code changes.

**Earlier in the day, for reference (v5.6.85-134):** shared-fact deliverable helpers (`_dfContractFacts`,
`_dfArpFacts`, `_dfCveIndex`, `_dfSustain`, etc.), SnapMirror count-only semantics, invented figures removed,
IOM6 upgrade-target cap, Plan-button fix (modals nested in hidden Settings tab), Technical Audit rear panels as
SVG scale drawings for all ONTAP/E-Series/StorageGRID platforms, `hw_docs_harvester.py` (scanner 9) +
`data/platform_hardware.json` + documentation panel, `tools/verify_rear_panels.py`, `tools/audit_deliverables.py`.
Standing rule: rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Full detail in git log / CHANGELOG.md for that range.
