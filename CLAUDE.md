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

## Session handoff -- 2026-09-26 (Windows dev station, v5.6.85 -> v5.6.97)

Overlaps the cloud session's v5.6.83/84 (merged in 5.6.85). Everything below is pushed to `main`.

**What was asked:** audit the Action Planner deliverables for contradictions and invented numbers, make them
copy/paste-ready for customers, then keep reviewing them against real accounts.

**What changed (all in `app.js`, client-side only -- no server restart needed):**
- One definition per fact, used by every document: `_dfContractFacts` (active / expiring / lapsed),
  `_dfArpFacts` (tri-state ARP), `_dfCveIndex` (real CVE ids only, systems de-duplicated), `_dfSustain`
  (per-system score, never the account-wide "all tenants" one), `_dfRunwayText`, `_osKnown/_osIsCurrent`
  (OS currency over systems it can be judged for), `_dfCollapseFindings`, `_dfCleanCause`.
- SnapMirror: Active IQ gives a relationship COUNT only. `snapMirrorReported` flag; count-only relationship;
  "unprotected" = confirmed no replication (unreported is "not reported", HA is not DR).
- Corrective-action grouping (`_filterAndDeduplicateRisks`): an OS upgrade is the fix only for CVE / software-version
  findings; groups no longer borrow the first finding's cause/steps. CVE findings get a CVE-specific plan in
  `generateDynamicRemediationPlan`. Risk 506 flags pre-release ONTAP (RC/beta) as high.
- Invented figures removed (TCO, savings, power/CO2, admin-time, 45% premium, "$X/TB"). FabricPool removed from the
  adoption score, scorecards, dashboards and action lists.
- New deliverable `customerReport` (`compileCustomerReport`): paste-ready Markdown health & lifecycle report.
  Change Tickets / Implementation Plans skip systems with nothing to do and list them once ("not assessed" when no AutoSupport).
- IMT interoperability: only from vCenter versions Active IQ reports (no substring guessing).
- Documents are prepared by the TAM when assigned (was the sales rep).

**Tooling:** `tools/audit_deliverables.py` generates every deliverable for every customer scope in parallel headless
browsers (44 scopes in ~35 s) and flags placeholders, invented-figure phrases, NaN/undefined, cross-document
disagreements, negative counts and other customers' names. Run it after any deliverable change:
`ARIA_URL=http://127.0.0.1:8080/ python tools/audit_deliverables.py 8`. Known benign hits: an account's own ASP / site
names that contain another customer's name.

**Gotchas hit this session:** heredoc Python scripts mangle backslashes (`\b` -> backspace, `\n` -> newline): write patch
scripts with the Write tool and use `chr(92)` or raw strings. app.js is CRLF. A dropped line inside a template
literal broke the whole page once (check the browser console after every edit).

**Still open / not done:**
- `.exe`: rebuilt with `build/build_windows.bat` at the end of the 5.6.97 session (see git log for the build commit).
- Reviewed line by line: Vodacom (all documents), MIC Tanzania (about half), Saudi Telecom (health report),
  Clicks (E-Series only), Shoprite (MetroCluster), Unemployment Insurance Fund (small). Others only by the audit tool.
- The PPTX Customer Value Report was opened and corrected in 5.6.97 (Vodacom deck); other scopes not opened.
- Source-data limits, not bugs: SnapMirror destination/lag not exposed; systems with no AutoSupport cannot be assessed;
  Active IQ's own recommendation text can disagree with our facts (a note explains it in the QBR); effort estimates,
  SLA targets and the cost-per-TB rate are defaults; some hardware EOA/EOS dates come from a maintained reference list.

**Git:** branch `main`, pushed. Working tree also shows harvest data files modified by the running server
(`data/*.json`) -- not part of this work, do not commit them with code changes.

**Added in 5.6.96-97:** `_dfActionPlan` / `_dfUpgradeWaves` / `_dfRefreshPlan` / `_dfCapacityTrend` (planning helpers before `compileCustomerReport`); 'Decisions needed' block inserted into every narrative document via `_bannerInsert`; capacity trend flags drained clusters.
