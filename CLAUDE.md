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

## Session handoff -- 2026-09-29 (Windows dev station, v5.6.177 -> v5.6.178)

Three separate threads this session; only the third shipped.

**1. Security scare, unresolved.** User installed ARIA fresh on a Mac (unzipped straight from a GitHub
download, no Google Drive involved) and it came up already connected to Active IQ with a refresh token,
account filters, and watchlist IDs visible in the GUI. Did exhaustive git forensics on `ebeauzec/ARIA`
(`git ls-files`, `git ls-tree -r HEAD`, `git log --all --diff-filter=A --name-only`, `git grep` for
secret-like patterns, direct inspection of every `data/*.json`) -- **the repo itself is clean, nothing
committed.** Leading theory: `localStorage` for `http://localhost:8080` is scoped by origin, not by which
files are served from it, so stale watchlists/credentials from a prior run on the same origin could look
"pre-connected" regardless of which code deployed there. Gave the user Brave cache-clearing steps to test.
**Not confirmed fixed or even correctly diagnosed -- follow up if it recurs.** Also flagged but not fixed:
`.gitignore` has `aiq_config.json$` -- gitignore is glob syntax, the trailing `$` is a literal character,
not an anchor, so that line doesn't actually match the file. Harmless today only because the file was never
`git add`ed; worth fixing for real given this thread was about credential hygiene.

**2. ASA (All-SAN Array) capacity/reporting bug, unresolved.** User reports no capacity/advanced reporting
for any ASA systems. Read through the ASA detection block in the big system-telemetry-enrichment function
(app.js ~18969-19025: `isASA` is a broad model-string check, `isASAr2` is narrow and depends on
`personality`/`isDisaggregated` API fields that may not always be populated -- a recurring theme with Active
IQ's sparse fields). Working hypothesis, **not yet confirmed against real ASA data or fixed**: the SAZ
capacity fallback at ~line 19267 (`if (isASAr2 && physTBfinal === 0 && (s.sazUsedKiB || 0) > 0) {...}`) is
gated on the narrow `isASAr2` when it should be gated on `isASA`, since real ASA systems may report
`sazUsedKiB` without `personality`/`isDisaggregated` being set. Next session: inspect real ASA system field
values against the live fleet before touching the code.

**3. Deliverable filenames standardized (shipped, v5.6.178).** User: downloaded filenames should be
`<Document Title> - <Customer> - <DD Month YYYY>` for every deliverable, uniformly. Added
`_dlFilename(title, scope, ext)` in `app.js` (right before `triggerFileDownload`, ~line 32780) and wired it
into every download call site: all ~16 types in `downloadDeliverable()` (~line 32791, each with its own
title string -- e.g. `'Executive Risk Assessment'`, `'TAM Quarterly Business Review Pack'`), the As-Built TXT
branch of `downloadPlanSection(19)` (~line 32281), and `downloadAsBuiltXlsx()`. `cleanScope`
(underscore-mangled name) is now unused in those spots -- left alone in `downloadPlanSection`'s other
section indices (1-18), which still use it. Since the filename `base` string also becomes the Word title
block via `_buildDocx()`, this fixed the in-document title to match the filename for free. Verified against
real production data (2898 systems, real customer "Liberty Group Ltd.") by monkey-patching `_dlBlob` to
capture names instead of triggering save dialogs -- confirmed correct output across txt/docx/md/csv/xlsx,
e.g. `"TAM Quarterly Business Review Pack - Customer Liberty Group Ltd. - 29 September 2026.docx"`.
`generateCVRPptx` (PPTX export, ~line 33021) was checked and confirmed to be dead code (no call sites) --
left untouched.

**Git:** branch `main`, v5.6.178 committed and pushed (exe rebuilt via PyInstaller to
`%LOCALAPPDATA%\Temp\aiqbuild178`, synced into `dist/NetApp_AIQ_Advisor/` + `dist/app.js`). Working tree
otherwise shows harvest data files modified by the running server (`data/*.json`) and untracked docs
images -- never commit those with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart -- app.js is
served fresh on every page load and needs neither. **HTML changes must land in both `index.html` and
`index_src.html`.** **Verify UI wiring with a real DOM event**, never a direct function call. **Any hand-rolled
OOXML (docx/xlsx) change must be validated by reproducing the file structure in Python and loading it with
`python-docx`/`openpyxl`** (installed via pip, not present by default) **before calling it verified.**
**Any screenshot of this app for documentation must block `/api/**` (or otherwise force demo mode) and verify
the resulting system count before saving** -- the app's default loaded state is the real fleet, not demo data.
