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

## Session handoff -- 2026-09-29 (Windows dev station, v5.6.164 -> v5.6.175)

The whole session was one goal: **ARIA's Word (.docx) deliverables must download customer-ready, with no
manual reformatting.** Started from 15 already-generated docs on the user's Desktop (restyled once with a
throwaway python-docx script into `Desktop\Customer-Ready`; user then said leave those and build it into ARIA).

- **Where it lives:** `app.js` Downloads section (~line 32800+): `_dxParse(text, isMd, ctx)` turns the
  plain-text/Markdown deliverable into normalised blocks; `_dxRender()` writes WordprocessingML;
  `_buildDocx()` adds title block, running header, "Confidential -- prepared for <customer>" footer with
  Page X of Y, numbering part (real bullets), hyperlink rels (rId100+). Look-and-feel: `_DX` palette +
  `_dxStyles()`. `.txt`/`.md` downloads are untouched. Customer name comes from `window.__dlScope`
  (set in `downloadDeliverable`, read-and-cleared in `triggerFileDownload`), else the Account/Scope line.
- **Cards** (`_dxCollectCard`, `_dxSpecialCard`, `_dxCardStart`, block type `fix`): corrective actions,
  CVE priority entries, ticket/runbook actions, QBR/MSP/Success Plan findings, Decisions (Why/When/Owner),
  roadmap actions, per-system upgrade plans, support cases, nested-bullet groups. Long titles split via
  `_dxSplitTitle` (tail -> Findings + Systems rows). Tables: text/pipe/segmented-rule columns, key/value
  runs, upgrade list, drift list. Also: URLs/bare NetApp domains/e-mails are hyperlinks (`_DX_LINK_RE`),
  raw HTML is stripped (`_dxStripHtml`, keeps `<svm>`-style placeholders).
- **Security Brief fixed releases (v5.6.169):** `_dfFixedReleases`/`_dfMinFixLines` read
  `NETAPP_SECURITY_BULLETIN_DB` (data/security_bulletins.json) -> "Fixed In" + per-system "Upgrade To"
  (same-branch fix, else lowest later fix; BMC firmware matched by model). Only 191 of 531 stored advisories
  carry release numbers; where none, the brief quotes the advisory text and offers Active IQ's recommended
  release *labelled as a recommendation*. NetApp's advisory pages are JS-rendered (WebFetch gets nothing),
  so real numbers need the harvester to capture the fixed-release tables. Never invent versions.
- **Generator fixes made along the way:** risk trend is a real table (`_dfTrendText`, md vs text), Success
  Plan status is a pipe table, RACI table spacing, MSP tables no longer truncate the customer name,
  Handover inventory no longer truncates platforms.
- **How to test (no Node here):** Playwright with `/api/**` blocked except `/api/bulletins`, and
  `localStorage aiq_mock_mode=true` (152 demo systems), capture text via `compileExtendedDeliverables`,
  build docx in-page with `_buildDocx`, validate with the docx skill's `validate.py`, export through desktop
  Word (COM) to PDF and look at pages. Real-click check: TAM/MSP tab -> download button -> `#dlFormatModal`
  Word. Beware: heredoc python that writes `\n` into JS gets corrupted -- use the Edit tool or a file.
  When the user's screenshot shows old output, first suspect a stale tab/exe (hard refresh / relaunch).

**Known/not done:** other customers are named in the MSP report and Security Brief ("also affects N other
customers ... Apex Global Solutions") -- not safe to send to a customer; needs a redact-vs-keep decision.
Account Handover / Sales Refresh / TAM Success Plan / QBR are internal TAM documents by nature. Demo/real
system names, `example.com` contacts appear as-is. Only demo-customer text was audited (rule-only rows,
markup, truncation, pipes all clean); a real fleet may show new line shapes -- capture the text and add the
shape to `_dxParse`. Rear-panel program gaps (FAS8000, older FAS25xx/26xx, unnamed StorageGRID, cloud) and
the unconfirmed packaged-exe `index_src.html` question still stand from earlier sessions.

**Git:** branch `main`, v5.6.164 through v5.6.175 all committed and pushed individually (exe rebuilt each
time, PyInstaller to `aiqbuild14`..`aiqbuild25` under `%LOCALAPPDATA%\Temp`). Working tree shows harvest data
files modified by the running server (`data/*.json`) and untracked docs images -- never commit those with
code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart -- app.js is
served fresh on every page load and needs neither. **HTML changes must land in both `index.html` and
`index_src.html`.** **Verify UI wiring with a real DOM event**, never a direct function call. **Any hand-rolled
OOXML (docx/xlsx) change must be validated by reproducing the file structure in Python and loading it with
`python-docx`/`openpyxl`** (installed via pip, not present by default) **before calling it verified.**
**Any screenshot of this app for documentation must block `/api/**` (or otherwise force demo mode) and verify
the resulting system count before saving** -- the app's default loaded state is the real fleet, not demo data.
