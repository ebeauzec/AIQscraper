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

## Session handoff -- 2026-09-29 (Windows dev station, v5.6.177 -> v5.6.179)

Three separate threads this session; the second and third shipped.

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

**2. ASA (All-SAN Array) capacity bug, fixed (shipped, v5.6.179).** User: no capacity/reporting for any ASA
systems. The original SAZ-fallback hypothesis (narrow `isASAr2` gate at ~line 19267) turned out to be a dead
end once checked against the real fleet (`state.systems` in the live browser session, 2898 systems, 22 real
ASA nodes): `sazUsedKiB` is 0 for every real ASA system regardless of `isASAr2`, so broadening that gate
would have changed nothing. The real cause, confirmed live: Active IQ genuinely returns null for
usedKiB/utilizationPercentage/rawMarketingKiB at BOTH system and cluster level for some ASA clusters (seen on
ASA-A70/A90/A30 -- 2 of 22 real systems had physical/raw/usable all stuck at 0; most ASA-A800/A250 systems
report fine). That's not a mapping bug -- it's the same class of real API gap already handled for
StorageGRID/E-Series via the `_capacityUnavailable` flag (app.js ~19308), which swaps the normal efficiency
card for an honest "no capacity data" note instead of misleading "0.0 TB / N/A". Fix: extended
`_sgEseriesCapGap` (app.js ~19315) to include `isASA`, added an ASA `platformNote` branch (~19344), and gave
the UI card (`renderCSMTab()`, ~17241-17245) a third label/color case ("ASA Block SAN Array", cyan) alongside
the existing StorageGRID/E-Series ones. Verified via a real DOM event flow (`focusOnSystem(serial)` +
`switchTab('csm')`, not a direct function call) against three real systems: a zero-capacity ASA-A70 (now
shows the honest note), a healthy ASA-A800 (unaffected, still shows its real 1.3:1 ratio), and an
already-working StorageGRID system (unaffected, still purple "StorageGRID Object Node").

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

**Git:** branch `main`, v5.6.178 and v5.6.179 committed and pushed individually (exe rebuilt each time via
PyInstaller to `%LOCALAPPDATA%\Temp\aiqbuild178`/`aiqbuild179`, synced into `dist/NetApp_AIQ_Advisor/` +
`dist/app.js`). Working tree otherwise shows harvest data files modified by the running server
(`data/*.json`) and untracked docs images -- never commit those with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart -- app.js is
served fresh on every page load and needs neither. **HTML changes must land in both `index.html` and
`index_src.html`.** **Verify UI wiring with a real DOM event**, never a direct function call. **Any hand-rolled
OOXML (docx/xlsx) change must be validated by reproducing the file structure in Python and loading it with
`python-docx`/`openpyxl`** (installed via pip, not present by default) **before calling it verified.**
**Any screenshot of this app for documentation must block `/api/**` (or otherwise force demo mode) and verify
the resulting system count before saving** -- the app's default loaded state is the real fleet, not demo data.
