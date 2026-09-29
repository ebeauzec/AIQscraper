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

## Session handoff -- 2026-09-29 (Windows dev station, v5.6.164)

Two things this session. (1) Asked to restyle a folder of 15 already-generated Word deliverables on the
Desktop into consistent customer-facing documents -- done with a one-off python-docx script (output in
`Desktop\Customer-Ready`, originals untouched; user then said to leave that as is). (2) The real ask:
**make ARIA's own Word deliverables carry that standard so nobody reformats after download** -- shipped
as v5.6.164.

- **What changed:** `_buildDocx()` in `app.js` (Downloads section, ~line 32790) was rewritten from a
  line-by-line XML emitter into a two-stage builder: `_dxParse(text, isMd, ctx)` turns the plain-text/
  Markdown deliverable into normalised blocks (title, headings on a 1-3 scale, tables, key/value lines,
  bullets, numbered items, CLI blocks), `_dxRender()` writes them as WordprocessingML. Look-and-feel lives
  in `_DX` (palette) + `_dxStyles()`. Adds: title block (title/customer/date), running header, footer
  "Confidential -- prepared for <customer>" + Page X of Y (`titlePg`, first-page header blank), numbering
  part for real bullets, navy-header banded tables, shaded CodeBlock style, redundant Scope/Account/Date
  lines folded into the title block, ALL-CAPS -> title case, hard-wrap rejoin, float rounding, page break
  per ticket/system for the Change Control Tickets and CLI Runbook. .txt/.md paths untouched.
- **Customer name plumbing:** `downloadDeliverable()` sets `window.__dlScope`; `triggerFileDownload()`
  reads-and-clears it (one-shot) and passes `{customer}` to `_buildDocx`. Downloads that don't set it
  (e.g. the per-system export) fall back to the Account:/Scope: line in the text -- never a stale scope.
- **How it was verified:** captured the real text of all 15 deliverables for the demo customer
  "Harbourview Distribution" via Playwright (`/api/**` blocked, `aiq_mock_mode=true`, 152 systems
  confirmed), built each .docx from the new builder, all 15 pass the docx skill's `validate.py`, exported
  through desktop Word to PDF and inspected the pages; then a real click on the Security Brief download
  button (format modal -> Word) against the live dev server produced a valid, correctly-titled file with
  zero page errors. No Node on this machine -- JS was tested in a Playwright page, not Node.
- **Known source-data glitches spotted (not fixed, outside this change):** MSP report Service Level table
  row "Case MTTR (<=5d)   5  d" has a stray space in the value; the MSP per-customer dashboard truncates the
  customer name ("Harbourview Distri") and its last header "DRR" is cut off. Demo/real system names,
  `example.com` contacts, and -- importantly -- the MSP report and Security Brief name OTHER customers
  ("also affects N other customers ... Apex Global Solutions, ...") : not safe to hand to a customer
  as-is; needs a decision (redact vs. keep for internal MSP use). Account Handover / Sales Refresh / TAM
  Success Plan / QBR are internal TAM documents by nature.

**Still open / not done:** rear-panel program still has no layout for FAS8000, older FAS25xx/26xx, unnamed
StorageGRID models, or cloud platforms. LEGAL.md/ARIA_FIX_PLAN.md still not content-audited. The Portfolio
Dashboard's urgency-score weighting is hand-picked. Whether the packaged `.exe` serves correctly given
`do_GET()`'s unconditional `index_src.html` rewrite is still unconfirmed. The Word standard is only
verified against the demo customer's text; a real fleet may surface line shapes the parser has not seen
(unusual indentation, new section types) -- if a real document looks off, capture its text and add the
shape to `_dxParse`.

**Git:** branch `main`. v5.6.164 committed and pushed (app.js, dist bundle, version.json, CHANGELOG.md,
README.md, this note). Working tree also shows harvest data files modified by the running server
(`data/*.json`) and untracked docs images -- not part of this work, never commit those with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart -- app.js is
served fresh on every page load and needs neither. **HTML changes must land in both `index.html` and
`index_src.html`.** **Verify UI wiring with a real DOM event**, never a direct function call. **Any hand-rolled
OOXML (docx/xlsx) change must be validated by reproducing the file structure in Python and loading it with
`python-docx`/`openpyxl`** (installed via pip, not present by default) **before calling it verified.**
**Any screenshot of this app for documentation must block `/api/**` (or otherwise force demo mode) and verify
the resulting system count before saving** -- the app's default loaded state is the real fleet, not demo data.
