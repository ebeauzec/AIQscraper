# CONTEXT.md — Active IQ Reporting Tool (ARIA)

> **Reconstructed**: 2026-07-28 from full codebase analysis + previous conversation artifacts.
> **Current Version**: 4.0.1 (per `version.json`, dated 2026-08-01)

---

## 1. What This Project Is

**ARIA** (*Active IQ Risk Intelligence Advisor*) is a standalone desktop application that connects to NetApp's Active IQ (AIQ) cloud platform, harvests system health and configuration data across a customer's entire storage fleet, and presents it in a rich interactive dashboard.

It is designed for **NetApp SEs, TAMs, SAMs, CSMs, and partners** who need to generate customer-facing reports (QBRs, security posture reviews, capacity plans, account handovers) without manual data gathering from the AIQ portal.

### Key Value Proposition
Active IQ's web portal is single-system-focused. ARIA provides **fleet-wide cross-customer views**: aggregated risk registers, fleet firmware audits, hop-by-hop upgrade path calculators, per-system CVE cross-referencing, capacity runway projections, and downloadable deliverables (CSP, QBR Pack, MSP Report, Handover Brief, CLI Runbook).

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────┐
│             Desktop Application                       │
│  ┌──────────────┐   ┌──────────────────────────────┐ │
│  │  server.py   │   │  index.html / index_src.html │ │
│  │  (HTTP proxy │   │  app.js (1.3MB logic)        │ │
│  │   + SQLite   │◄──►  styles.css                  │ │
│  │   + harvest) │   │  chart.js (Chart.js lib)     │ │
│  └──────┬───────┘   └──────────────────────────────┘ │
│         │                                             │
│  ┌──────▼───────┐   ┌──────────────┐                 │
│  │ aiq_cache.db │   │ asup_parser  │                 │
│  │ (SQLite)     │   │ (offline     │                 │
│  └──────────────┘   │  ASUP import)│                 │
│                     └──────────────┘                  │
│  ┌──────────────────────────────────────┐             │
│  │ launcher.py (pywebview native window)│             │
│  └──────────────────────────────────────┘             │
└──────────┬───────────────────────────────────────────┘
           │  HTTPS
┌──────────▼───────────────────────────────────────────┐
│        NetApp Active IQ Cloud Platform                │
│  ┌──────────────────┐  ┌───────────────────────────┐ │
│  │ GraphQL API      │  │ REST API                  │ │
│  │ gql.aiq.netapp   │  │ api.activeiq.netapp.com   │ │
│  └──────────────────┘  └───────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Technology Stack
- **Backend**: Python 3.8+ (`http.server` + custom handler), SQLite3, SSL context with enterprise CA auto-detection
- **Frontend**: Vanilla HTML5 / CSS3 / ES6 JavaScript SPA (zero framework dependencies)
- **Charting**: Chart.js (bundled as `chart.js`)
- **Desktop Wrapper**: pywebview (WebView2 on Windows, WKWebView on macOS)
- **Packaging**: PyInstaller (Windows `.exe`, macOS `.app`)
- **Installer**: Custom tkinter GUI installer (`Install_NetApp_AIQ_Advisor.py`)

### Data Sources
1. **AIQ GraphQL API** (`gql.aiq.netapp.com`) — Watchlists, system inventory, TAM info, cluster configs, switches, shelves, support cases
2. **AIQ REST API** (`api.activeiq.netapp.com`) — Token exchange, capacity, risks
3. **ASUP Files** — Offline AutoSupport bundle parsing (`.7z`, `.tgz`, `.zip`, `.xml`, `.gz`) for air-gapped environments
4. **Local Reference Library** — `data/firmware_baselines.json`, `data/security_bulletins.json`, plus embedded EOA platform lists, CVE database, upgrade caveats, MetroCluster ISL specs
5. **External Enrichment Sources** (v4.0.0 scanner architecture):
   - `docs.netapp.com` — ONTAP/StorageGRID/SANtricity release notes (known issues, fixed issues, what's new)
   - `security.netapp.com` — PSIRT advisory index and individual advisory detail pages
   - `services.nvd.nist.gov` — NVD CVE API v2 (CVSS scores, severity, descriptions, affected version ranges)
   - `mysupport.netapp.com` — Bugs Online public search
   - `kb.netapp.com` — JSON-LD category tree crawler: 64+ KB articles across 3 hierarchy levels (root → product → topic categories)
   - `docs.netapp.com/us-en/ontap/` — Index page crawler: 139+ doc links extracted from ONTAP, hardware, NAS, SAN, upgrade indexes
   - `docs.netapp.com` integration seeds — **75 verified doc URLs** covering VMware (6), Kubernetes/Astra (5), databases (6), cloud/hybrid (8), backup (5), security (8), monitoring (5), data protection (7), networking (5), upgrades (6), sustainability (4), and common operations (10)
   - `kb.netapp.com/on-prem/ontap/` — Fleet-specific KB sub-category crawling: Data Access, Data Protection, MetroCluster, SnapMirror, SnapLock, NAS, SAN (27+ articles)
   - `docs.netapp.com` security/remediation docs — direct links for antivirus, anti-ransomware, NAS audit, multi-admin verify, SnapLock, authentication
6. **Version Catalog Auto-Detection** (v3.8.0+) — Scrapes docs.netapp.com to discover newly released ONTAP, StorageGRID, and SANtricity versions; auto-updates the client-side `SOFTWARE_VERSION_DATABASES` on each page load
7. **Fleet-Aware Deliverable Mapper** (v4.0.0) — All 13 TAM deliverables receive fleet-relevant enrichment references. Articles scored by ONTAP version match (+30), platform family (+20), model match (+25), operational category (+10). Minimum score 5 required for inclusion.
8. **Enrichment Intelligence UI** (v4.0.0) — KB Intelligence Summary Panel (aggregate stats, fleet profile, per-category breakdown), enrichment badges on all 13 deliverable cards (★ N KB refs pills), and rich contextual intelligence engine (`getArticleContext`) generating CLI commands, effort estimates, and fleet-specific remediation steps per matched article.

---

## 3. File Inventory & Purpose

### Core Application Files

| File | Size | Purpose |
|------|------|---------|
| `server.py` | 275KB | Central HTTP proxy, SQLite cache, GraphQL harvester, enrichment engine (7 external sources), version catalog, ASUP handler, TLS auto-config, cluster name derivation, E-Series hardware synthesis |
| `app.js` | 1.36MB | All frontend logic: state management, API calls, tab rendering, enrichment display, remediation plan generator, reference library, dynamic version management, platform-aware upgrade paths (ONTAP + StorageGRID + E-Series), deliverable DR/capacity/adoption intelligence |
| `index.html` | 81KB | Production dashboard SPA (6 views, sidebar nav, search, modals) |
| `index_src.html` | 85KB | Development/source version of dashboard — includes ASUP import modal DOM + enhanced error handling |
| `styles.css` | 28KB | Complete dark-mode design system with CSS custom properties, responsive layouts, animations |
| `chart.js` | 208KB | Bundled Chart.js library |
| `launcher.py` | 7.8KB | Desktop launcher (pywebview native window + embedded CORS proxy + fallback browser) |
| `asup_parser.py` | 25KB | Offline ASUP bundle parser (ONTAP, StorageGRID, E-Series) with ARIA schema normalization |

### Configuration & Data Files

| File | Purpose |
|------|---------|
| `aiq_config.json` | Stores refresh token, watchlist IDs, TAM info |
| `version.json` | Source of truth for version number (currently 4.0.0) |
| `data/firmware_baselines.json` | Ground-truth firmware recommendations (ONTAP, SP/BMC, shelf, disk, StorageGRID, SANtricity) |
| `data/security_bulletins.json` | Local CVE/NTAP advisory database for offline security matching |
| `aiq_cache.db` | SQLite cache database (~22MB, stores all harvested data) |

### Build & Distribution

| File | Purpose |
|------|---------|
| `AIQscraper.spec` | PyInstaller build spec (Windows + macOS) |
| `build_windows.bat` | Automated Windows build script |
| `build_mac.sh` | Automated macOS build script |
| `bump_version.ps1` | PowerShell SemVer version management + git tagging |
| `Start-Dashboard.ps1` | PowerShell launcher (kills port 8080, starts server + browser) |
| `start_dashboard.bat` | Batch file launcher (same purpose) |
| `Install_NetApp_AIQ_Advisor.py` | GUI/CLI installer with shortcuts, registry entries, desktop icon |
| `dist/NetApp_AIQ_Advisor/` | Pre-built Windows executable (5.1MB) |

### Documentation & Legal

| File | Purpose |
|------|---------|
| `README.md` | Comprehensive user & developer manual (790+ lines) |
| `CHANGELOG.md` | Full release history (v1.0.0 through v4.0.1) |
| `LEGAL.md` | IP ownership declaration |
| `LICENSE` | Proprietary license (Eugene Beauzec, non-commercial free, commercial requires consent) |

### Development / Debug Tools (~30 files)

All `check_*.py`, `debug_*.py`, `diag_*.py`, `probe_*.py`, `test_*.py`, `validate_*.py`, `verify_*.py`, `trigger_*.py`, `dump_*.py`, `find_*.py`, `fix_*.py`, `inspect_*.py`, `analyze_*.py` files are **development-time utilities** for API exploration, schema introspection, data verification, and debugging. They are not used in production.

Also includes: `brace_report.txt` (JS syntax audit), `fix_guidelines.ps1` (one-off app.js patch), various `*_results.json` / `*_data.json` files (probe output artifacts).

---

## 4. Dashboard Views (6 Primary Navigation Areas)

### View 1: Overview Dashboard
- 4 KPI cards (Total Systems, Critical Risks, Active Warnings, Expiring Contracts)
- Chart.js graphs (Storage Savings/Efficiency, Capacity by System)
- Monitored Systems & Clusters table with sorting, CSV export, JSON import/export

### View 2: Technical Audit (TAM Module)
- Multi-select system filtering
- Controller Node Port & Link Topology visualization
- SANtricity E-Series Hardware Audit card
- SVM & Protocol Security Audit
- Active Predictive Risk Signatures table with slide-out remediation modal
- OS Upgrade Advisor with hop-by-hop upgrade path calculator
- Network Switch & Fabric Validation table
- Active Security & Technical Bulletins (CVE matching with CISA KEV integration)

### View 3: Support & Ops (SAM Module)
- Contract status cards (SupportEdge, warranty, EOA/EOS lifecycle)
- 3rd-Party Virtualization tracking
- AutoSupport status monitoring
- Logistics & Customer Sales Health
- Active Support Cases table
- Outstanding Field Actions (FA)

### View 4: Value & ROI (CSM Module)
- Storage Efficiency Savings metrics
- Cloud Tiering ROI (FabricPool)
- SnapMirror data protection coverage
- Capacity & Performance Forecasting with runway projections
- 15-Point TAM/MSP Remediation Readiness Checklist

### View 5: Action Planner
- Consolidated operational action plan generator
- Phased remediation plans (20+ risk categories)
- ITIL change management governance
- Downloadable deliverables: CSP, QBR Pack, MSP Report, Handover Brief, CLI Runbook
- PDF print/save capability

### View 6: Settings & Config
- API Authentication (refresh token, base URL, offline demo toggle)
- Watchlist Scope management
- Quick Actions (sync, diagnostics, update)
- System Serial Numbers configuration
- Custom Subgroups Manager
- Full System Metadata & Logistics Editor (per-system identity, contacts, sales data)
- GraphQL Query Console & Sandbox

---

## 5. What Is Complete (✅)

### Core Functionality
- AIQ authentication (OAuth refresh token → access token exchange)
- System discovery and inventory harvesting via GraphQL
- Risk/action harvesting
- Capacity data with per-aggregate trend charts and runway forecasting
- Firmware currency comparison against `data/firmware_baselines.json` (ONTAP, SP/BMC, disk, shelf)
- Security bulletin matching (77+ entries, 82+ CVEs, CISA KEV integration)
- MetroCluster health monitoring (config, partner status, mirror state)
- Support case tracking
- Switch & fabric validation
- Contract & lifecycle tracking
- Storage efficiency & ROI metrics

### Dashboard & UX
- All 6 navigation views fully rendered
- Dark-mode design system with professional aesthetic
- Responsive layout
- Loading states and skeleton screens
- Slide-out remediation modal with step-by-step CLI commands
- PDF export / print capability
- CSV/JSON export/import
- Live search with autocomplete
- Account filter tree

### Enrichment Engine
- `REFERENCE_LIBRARY_FIRMWARE_BASELINES` — per-module shelf/switch firmware recommendations
- `REFERENCE_LIBRARY_MC_REQUIREMENTS` — MetroCluster ISL specs
- `REFERENCE_LIBRARY_ONTAP_HIGHLIGHTS` — per-version upgrade motivation text (9.7 → 9.19.1)
- `REFERENCE_LIBRARY_UPGRADE_CAVEATS` — breaking changes per target version
- `NETAPP_SECURITY_BULLETIN_DB` — full CVE/NTAP advisory database
- `generateDynamicRemediationPlan()` — 20+ risk category remediation engine (~900 lines), now populates Options/Trade-Offs and Compliance fields for live API risks
- EOA platform flagging, Kerberos KB5073381 detection, E-Series model recognition (E2824, E5700, EF4000)
- `linkify()` function auto-linking CVE IDs, TR references, NTAP IDs, KB articles — anchor-tag-safe (no double-wrapping)
- Platform-aware upgrade path calculator: ONTAP (multi-hop), StorageGRID (11.x → 11.9), E-Series/SANtricity (version-range)
- Cluster identity derivation from hostname when API lookup returns empty
- Deliverable intelligence enrichment: DR coverage, capacity forecast, feature adoption sections injected into all 13 deliverables

### External Enrichment Pipeline (v3.8.0+)
- **7 external sources** per version: release notes, PSIRT advisories, NVD CVEs, Bugs Online, KB articles, upgrade paths, best practice guides
- **Persistent SQLite cache** (`enrich_cache` table) with 7-day TTL (24h for NVD)
- **Background thread** runs after every harvest — never blocks page loads
- **Rate-limited** (1 req/sec) — polite to public servers
- **Version Catalog Auto-Update** — scrapes docs.netapp.com for latest ONTAP, StorageGRID, SANtricity versions; client `SOFTWARE_VERSION_DATABASES` updated dynamically on page load via `/api/enrich/versions`
- **Version Intel UI** — expanded card showing KB articles with remediation steps, upgrade path advisor with direct/multi-hop badges, and best practice TR references

### Build & Distribution
- PyInstaller single-dir EXE (Windows, working — `dist/NetApp_AIQ_Advisor.exe`)
- Mac `.app` build script
- GUI/CLI installer with desktop shortcuts, Start Menu entry, registry integration
- Version bump automation with git tagging
- "What's New" startup modal (version-gated)

### ASUP Offline Import (v3.7.0)
- `asup_parser.py` — Full parser for `.7z`, `.tgz`, `.zip`, `.xml`, `.gz` bundles
- Supports ONTAP, StorageGRID, and E-Series bundle formats
- ARIA normalized schema output with full Reference Library enrichment
- Coverage report showing parsed vs. unavailable telemetry
- `index_src.html` contains full ASUP import modal with drag-and-drop upload

---

## 6. What Is Partially Done (🔶)

| Item | Current State | What's Missing |
|------|---------------|----------------|
| **SnapMirror/SnapVault status** | Relationship count harvested; lag time partially available | Full relationship detail integration (source, dest, state, lag time) |
| **Upgrade Planner** | ONTAP version shown, hop-by-hop display exists in TAM tab | Full upgrade path validation logic (multi-hop sequencing, IMT cross-check) |
| **Print CSS** | Works for most content | Charts clip on print; needs page-break optimization |
| **Large watchlist pagination** | Pagination implemented | UX rough for >500 systems |
| **Token refresh** | Retry logic exists | Occasional silent failures; needs retry queue |
| **PDF export long tables** | Works with manual page breaks | Auto page-break logic cuts off some long tables |
| ~~**v3.7.0 CHANGELOG entry**~~ | ✅ Done in v4.0.0 | All versions through 4.0.1 now documented |
| ~~**README version badge**~~ | ✅ Done | Badge shows 4.0.1 |
| **Data protection coverage %** | SnapMirror count exists | Volume-level protection ratio calculation missing |
| **`index.html` vs `index_src.html` sync** | `index_src.html` has ASUP modal; `index.html` does not | Need to decide which is canonical and sync |
| **Firmware Phase 2** | Phase 1 (Unverified badge) complete | Model-specific SP/BMC baseline research and `data/firmware_baselines.json` expansion |

---

## 7. What Is Not Started (❌)

| Item | Notes |
|------|-------|
| **Performance Analytics tab** | Needs ONTAP perf counters or AIQ performance data |
| **SLA Compliance tab** | Needs customer SLA definitions |
| **Configuration Drift tab** | Needs baseline config to compare against |
| **License compliance data** | Need to discover correct AIQ API field |
| **EOS/EOA dates** | May need external data source or scraping |
| **Auto-updater mechanism** | No self-update capability |
| **Code signing** | Needs certificate |
| **Customer logo in PDF exports** | Need logo upload feature |
| **WCAG accessibility** | Not started |
| **Keyboard navigation** | Not started |
| **Multi-tenant support** | Serve multiple customers simultaneously |
| **Scheduled report generation** | Cron-style automated reports |
| **Email delivery of PDF reports** | Needs SMTP integration |
| **ServiceNow / Jira integration** | Action tracking integration |
| **REST API for CI/CD** | Programmatic access |
| **Historical trend database** | Beyond single-point-in-time snapshots |
| **Ansible playbook generation** | From recommendations |
| **RBAC** | Role-based access control for shared deployments |
| **StorageGRID version audit** | In Firmware Currency panel |
| **SANtricity version audit** | In Firmware Currency panel |

---

## 8. Known Issues / Bugs

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| B1 | PDF export sometimes cuts off long tables | Medium | Workaround: manual page breaks |
| B3 | Token refresh occasionally fails silently | Medium | Partial fix; needs retry queue |
| B4 | Large watchlists (>500 systems) slow to load | Medium | Pagination added but UX rough |
| B5 | MetroCluster partner status sometimes stale | Low | Cache TTL issue |
| B6 | ASUP upload fails for files >50MB | Low | Need chunked upload |
| B8 | `build_mac.sh` line 22 has corrupted string | Low | Windows Store error text copy-paste artifact |
| B9 | `AIQscraper.spec` macOS bundle version hardcoded to `3.0.0` | Low | Should read from `version.json` |
| B10 | `aiq_config.json` has empty watchlistId/tamName/tamEmail fields | Low | Populated at runtime; may confuse new users |

---

## 9. Code Quality Observations

### Strengths
- Clean frontend design system with CSS custom properties
- Comprehensive enrichment engine with 20+ risk categories
- Resilient ASUP parser handling multiple archive/product formats
- Enterprise TLS inspection auto-detection (Zscaler, BlueCoat, etc.)
- Well-documented README with use cases and architecture diagrams

### Concerns Noted in Previous Review
- **`server.py` is monolithic** (193KB / ~3,900 lines) — should refactor into modules
- **`app.js` is massive** (1.1MB / ~20,000+ lines) — should consider modularization
- **No automated test suite** — only ad-hoc debug/probe scripts
- **~30 dev utility scripts** in project root — should move to `tools/` directory
- **`index.html` vs `index_src.html`** — unclear which is canonical source of truth
- **Auth tokens stored in plaintext** JSON — acceptable for desktop, but encryption recommended
- **Cookie-based auth is reverse-engineered** — may break with AIQ portal updates (note: code now uses refresh token flow, which is more stable)

---

## 10. Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 1.0.0 | 2026-07-06 | Initial release |
| 2.0.0 | 2026-07-10 | Python backend (`server.py`), SQLite DB, GraphQL integration |
| 3.0.0 | 2026-07-10 | TAM Account Intelligence Suite (Tabs 10–15) |
| 3.1.0 | 2026-07-10 | NetApp Reference Library enrichment engine |
| 3.2.0 | 2026-07-11 | Storage efficiency calculation fixes |
| 3.3.0 | 2026-07-11 | Security Intelligence Engine (77 entries, 82 CVEs, CISA KEV) |
| 3.3.1 | 2026-07-12 | Bug fixes, batched CVE enrichment, per-system risk grouping |
| 3.5.0 | 2026-07-19 | What's New modal, changelog integration |
| 3.6.0–3.6.3 | 2026-07-19 | Collapsible upgrade cards, expand-all fix, hop display fixes |
| 3.7.0 | 2026-07-20 | ASUP Offline Import |
| 3.8.0 | 2026-07-28 | Enhanced Enrichment Engine — 7 external sources, version catalog auto-update, KB articles + upgrade paths + best practices in Version Intel card |
| 3.8.2 | 2026-07-31 | Fix: ESeriesSystem GQL schema error broke efficiency harvest — removed invalid fragment, restored snapshot-excluded data reduction ratios, donut chart savings, and capacity fields |
| 4.0.0 | 2026-08-01 | Fleet-Aware Enrichment Engine rewrite — 268+ KB articles, JSON-LD crawlers, deliverable enrichment mapper, KB Intelligence panel, enrichment badges |
| 4.0.1 | 2026-08-01 | Deliverable DR/capacity/adoption intelligence, dynamic remediation fields, cluster name derivation, multi-platform upgrade paths, E-Series detection fixes |

---

## 11. Previous Conversation Artifacts

The previous agent conversation (ID: `73665ae2-...`) produced these planning/review documents (stored in its artifact directory):

| Document | Purpose |
|----------|---------|
| `action_plan_consolidated.md` | Sample generated consolidated action plan for a customer (AFF A400, EF600, E5700) |
| `activeiq_reporting_tool_outline.md` | Feature outline with role-based architecture (TAM/SAM/CSM) |
| `implementation_plan.md` | Firmware currency "false Current" badge fix plan (completed Phase 1) |
| `task.md` | Firmware ground-truth audit task checklist |
| `walkthrough.md` | Multi-session build walkthrough (v3.1.0 enrichment + remediation engine) |
| `project_review.md` | Architecture assessment, feature completeness, code quality metrics |
| `enrichment_plan.md` | Data enrichment roadmap (SnapMirror, licenses, contracts, upgrade paths) |
| `api_architecture_report.md` | AIQ REST + GraphQL API documentation |
| `activeiq_data_verification.md` | Data accuracy verification report (portal vs. tool comparison) |
| `metrocluster_report.md` | MetroCluster feature implementation report |
| `security_bulletin_db.md` | Security bulletin database design & implementation notes |

---

## 12. Logical Next Steps (Suggested Priority Order)

### Immediate Housekeeping
1. **Sync `index.html` with `index_src.html`** — the ASUP modal DOM from `index_src.html` should be in the production file
2. ~~**Add v3.7.0 entry to CHANGELOG.md**~~ — ✅ Done (all versions through 4.0.1 documented)
3. ~~**Update README.md version badge**~~ — ✅ Done (badge shows 4.0.1)
4. **Fix `AIQscraper.spec` macOS version** — hardcoded 3.0.0
5. **Fix `build_mac.sh` corrupted string** on line 22

### Feature Work
6. **Complete SnapMirror integration** — pull full relationship details (source, dest, state, lag), add data protection coverage % to Executive Summary
7. **Firmware Phase 2** — research model-specific SP/BMC baselines, expand `data/firmware_baselines.json`
8. **StorageGRID + SANtricity version audit** in Firmware Currency panel
9. **Upgrade Planner enhancement** — full upgrade path validation with multi-hop sequencing

### Code Quality
10. **Move ~30 dev scripts to `tools/` directory** — declutter project root
11. **Refactor `server.py`** into modules (`routes/`, `services/`, `cache/`)
12. **Add basic test suite** (pytest) for version comparison, ASUP parsing, enrichment logic
13. **Establish `index_src.html` as canonical** — generate `index.html` from it or consolidate

---

## 13. KPI Computation Functions (`app.js`)

Key metric calculations are implemented in `app.js` at the following locations:

- **`computeAccountHealthScore(targetSystems)`** — Line 11009. Computes the 0-100 Account Health Score using a weighted formula of 7 factors (ASUP, ARP, Firmware, Contracts, Risks, Data Reduction, CSAT).
- **`computeMTTR(allSupportCases)`** — Line 11060. Calculates the Mean Time to Resolve in days for all closed cases.
- **`computeFeatureAdoptionScore(sys)`** — Line 11088. Evaluates a 15-point best-practice checklist to return an adoption score (0-15) and percentage.
- **`computeCostOfInaction(targetSystems)`** — Line 11118. Computes the weighted Cost of Inaction urgency score based on risks, CVEs, capacity runway, and lifecycle status.

---

*This document was generated by analyzing all 89+ project files and 11 previous conversation artifacts. It serves as the single source of truth for project state recovery after context loss.*
