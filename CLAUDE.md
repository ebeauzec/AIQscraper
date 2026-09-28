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

## Session handoff -- 2026-09-28 (Windows dev station, v5.6.153 -> v5.6.161)

**v5.6.161, right after v5.6.160 shipped: the As-Built export's DATA had three more field-name bugs, found by the
user actually reading the Excel output row by row.** All three were "read a field that never existed, always
blank" -- the exact same class of bug, each one copied from the pre-existing As-Built TXT generator into the
new Excel export, so both were fixed together each time: (1) risk titles read `r.title` (real field is
`r.description` -- confirmed against the fallback chain already used correctly at `app.js` ~19183); (2)
contract dates read `sys.contracts.hwEndDate`/`swEndDate`, which never existed -- the real `contracts` object
(confirmed live: `{status, endDate, daysRemaining, supportLevel}`) only has one unified `endDate` plus a real
`supportLevel` that was never surfaced anywhere in this export; (3) firmware read `sys.firmware.systemVersion`/
`diskVersion`/`shelfVersion`, also nonexistent -- replaced with the real `sys.systemFirmware.currentVersion`,
`sys.motherboardFirmware.currentVersion`, and `_resolveShelfModules(sys)` (the shared helper the working
Firmware Currency section already uses), plus a new per-system drive-firmware current/behind/unknown count
since individual drive firmware has no single per-system value to collapse to. Verified live against one real
system's actual row data (not just "no exception thrown") for every fix this time.
**Pattern worth remembering**: the As-Built TXT generator (`downloadPlanSection(19)`, `app.js` ~32120) is old
enough that a meaningful fraction of its field references may be stale/wrong in ways nothing ever surfaced
before, because it was write-only (generated, downloaded, presumably rarely read cell-by-cell). Building the
Excel export against it just made the same latent bugs visible for the first time. If another field in that
export looks suspiciously always-blank, check it against a real system's actual JSON shape
(`state.systems.find(...)`) before assuming the harvest data itself is just sparse.

Continues the same multi-day stretch (v5.6.85 -> v5.6.153 -- rear-panel accuracy program, hardware-docs
harvester, Digital Advisor competitive-differentiation work, VMware Inventory section, trend redesign; see
git log / CHANGELOG.md for that range, don't re-derive). Everything below is pushed to `main`.

**v5.6.154 -> v5.6.155: sortable Capacity Breakdown table + Customer column.** `server.py`'s `do_GET()`
(~line 8294) rewrites `/` to `/index_src.html` in dev mode; `index.html` is only the compiled artifact the
packaged exe bundles. A fix landed in `index.html` alone is never actually live. Fixed for real in
`index_src.html`, kept `index.html` in sync. **Rule reinforced repeatedly this stretch: verify with a real
DOM event (`.click()`), never by calling the handler function directly** -- a direct call proves the logic
works, not that the page wires it up, and can't catch a missing `<thead>`/`<tbody>` split either (v5.6.157
hit exactly that on 4 new tables).

**v5.6.156/157: Portfolio Dashboard + cross-customer CVE exposure**, both leaning on the multi-tenant fusion
edge (`_merge_account_results()`, `server.py` ~1237). `computePortfolioExecutiveDashboard()` /
`_renderPortfolioExecutiveDashboard()`: new Action Planner section (tab/section index 22, Overview group),
ignores the scope selector entirely, gated on >=2 customers in `state.systems`. `_dfCveIndex()` extended with
a `customers` Set per CVE; `_dfPortfolioCveExposure()` surfaces "this CVE also affects N other customers" with
no minimum-size gate (even 1 other customer is actionable). v5.6.157 fixed a real bug found from a
screenshot: all 4 new tables sorted their own header row into the data because they lacked `<thead>`/`<tbody>`
(every other sortable table in the app already has this split).

**v5.6.158/159/160: As-Built Excel export, shipped broken twice, now genuinely fixed and verified.** Asked
"does it make sense to have the As-Built document downloadable as xlsx?", then "do it all." Built
`_buildXlsx()`/`_xlsxSheetXml()`/`_colLetter()` (`app.js`, right after `_buildDocx()`) -- a from-scratch
minimal XLSX writer (no library), 4 sheets (Systems/Shelves/SVMs & LIFs/Risks) from the same fields the
As-Built TXT export already uses. **Two real corruption bugs, in sequence, both only caught by user testing
in real Excel -- my own "verification" both times only proved the zip/XML was well-formed, never that Excel
would actually accept it:**
1. (v5.6.158 -> v5.6.159) Excel prompted to repair the file. Root cause: `xl/_rels/workbook.xml.rels` declared
   relationships for every worksheet but never for `styles.xml`, and `styles.xml`'s `cellXfs` had no matching
   `cellStyles` entry. Found and fixed by reproducing the exact file structure in a standalone Python script
   and validating with `openpyxl` (`pip install openpyxl` -- not present by default in this environment) until
   it loaded with zero warnings, THEN applying the identical fix to the real `_buildXlsx()`.
2. (v5.6.159 -> v5.6.160) File opened clean but the header row was invisible -- screenshotted as blank cells
   with working autofilter dropdowns, i.e. the text was there but unreadable. Root cause: white bold header
   text (`color rgb="FFFFFFFF"`) sitting on a fill that used a non-standard fill-index layout (custom solid
   fill at index 1, when real Excel-generated files always reserve index 0/1 for `none`/`gray125` and start
   custom fills at 2) -- whatever Excel did with that irregular layout, the practical effect was white-on-
   nothing. Fixed by conforming to the standard fills convention AND dropping the white color override
   entirely (header text now just bold, default/black), so visibility no longer depends on the fill
   rendering at all. Verified this time by extracting the REAL generated `styles.xml` from a live browser
   export (not just the Python mirror) and confirming the fix landed in the actual `_buildXlsx()` output.
   **Lesson for next time a hand-rolled OOXML writer (docx or xlsx) is touched: reproduce the exact part
   structure in Python and load it with `python-docx`/`openpyxl` before calling anything "verified" --
   well-formed XML and a valid zip are necessary but nowhere near sufficient for Excel/Word to accept it
   without complaint, and this cost two extra round-trips (found by the user, not by testing) before that
   discipline was actually followed.**

**Also v5.6.160: Deliverables Suite split into 3 tabs**, per explicit user request (then user specified the
exact 3 category names to use: "risk & remediation, Customer and Sales, and tam/msp" -- matching the suite's
own PRE-EXISTING internal category dividers exactly, so no new categorization judgment was needed, just
splitting the existing single section along its own existing seams). Section 9 (data-section-index 9) now
holds only cards A-C; two new sections 23 (D-I) and 24 (J-O) hold the rest; tab row now has 3 featured buttons
instead of 1. New `_DELIVERABLE_CATEGORIES` map (`app.js`, right before `downloadAllDeliverables()`) feeds
both the new per-tab `downloadDeliverableCategory()` buttons and `downloadAllDeliverables()` itself -- the
latter was found to be silently missing 2 of the 15 real deliverables (`VALUE_REPORT`/`CUSTOMER_REPORT`,
added after it was last touched), fixed as part of the same edit since both are now built from one shared list.

**Build/release housekeeping done this session:** seven versions shipped (`APP_VERSION`/`APP_CHANGELOG` in
`app.js`, `version.json`, `CHANGELOG.md`, bumped every time): 5.6.154 through 5.6.160. PyInstaller rebuilt to
a fresh temp dir every time (`aiqbuild5` through `aiqbuild11` under `%LOCALAPPDATA%\Temp` -- per standing rule
below, never `build/build_windows.bat`), exe + `_internal/base_library.zip` + `_internal/app.js` (+
`_internal/index.html` on the versions that touched it) + top-level `dist/app.js` copied into the committed
`dist/NetApp_AIQ_Advisor/` tree each time.

**Still open / not done:** rear-panel program still has no layout for FAS8000, older FAS25xx/26xx, unnamed
StorageGRID models, or cloud platforms. LEGAL.md/ARIA_FIX_PLAN.md still not content-audited. Only the
Capacity Breakdown by Node table (CSM tab) is sortable among `index.html`/`index_src.html`'s other `<th>`
elements. The Portfolio Dashboard's urgency-score weighting is hand-picked, not validated against real TAM
triage priorities. Whether the packaged `.exe` itself serves correctly given `do_GET()`'s unconditional
`index_src.html` rewrite (not bundled into the exe per `AIQscraper.spec`) is still unconfirmed, flagged three
sessions running now -- worth just checking directly next time, this has been noted long enough.

**Git:** branch `main`. v5.6.154 through v5.6.160 all committed and pushed individually. Working tree also
shows harvest data files modified by the running server (`data/*.json`) -- not part of this work, never
commit those with code changes.

**Standing rules:** rebuild and push the exe after every shipped change (PyInstaller to a temp dir, never
`build/build_windows.bat` -- destructive). Server.py changes need an actual server restart -- app.js is
served fresh on every page load and needs neither. **HTML changes must land in both `index.html` and
`index_src.html`.** **Verify UI wiring with a real DOM event**, never a direct function call. **No `node`
binary in this Bash environment** -- `new Function(text)` on the fetched file in a browser console substitutes
for `node -c`; a Python paren/brace/bracket-count sweep narrows down a bad line. **Any hand-rolled OOXML
(docx/xlsx) change must be validated by reproducing the file structure in Python and loading it with
`python-docx`/`openpyxl`** (installed via pip in this environment, not present by default) **before calling it
verified** -- a well-formed zip/XML is not sufficient evidence that real Excel/Word will accept it; this
stretch shipped the xlsx feature broken twice before that discipline was actually applied.
