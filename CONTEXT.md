# CONTEXT.md — Active IQ Reporting Tool (ARIA)

> **Reconstructed**: 2026-07-28 from full codebase analysis + previous conversation artifacts.
> **Current Version**: 5.6.233 (per `version.json`, dated 2026-10-03)
> **Note**: Sections 1-4 were refreshed 2026-09-27. Sections 5-12 still describe the app as of v4.0.7
> (2026-08-04) and predate the dated addenda below plus everything through v5.6.221 -- treat them
> as a historical snapshot, not current state (items known to be out of date are struck through). For what's actually shipped since, read the addenda
> at the end of this file and `APP_CHANGELOG` in `app.js` (near line 32), not the tables in 5-8.

---

## 1. What This Project Is

**ARIA** (*Active IQ Risk Intelligence Advisor*) is a standalone desktop application that connects to NetApp's Active IQ (AIQ) cloud platform, harvests system health and configuration data across a customer's entire storage fleet, and presents it in a rich interactive dashboard.

It is designed for **NetApp SEs, TAMs, SAMs, CSMs, and partners** who need to generate customer-facing reports (QBRs, security posture reviews, capacity plans, account handovers) without manual data gathering from the AIQ portal.

### Key Value Proposition
Active IQ's web portal is single-system-focused. ARIA provides **fleet-wide cross-customer views**: aggregated risk registers, fleet firmware audits, hop-by-hop upgrade path calculators, per-system CVE cross-referencing, capacity runway projections, and downloadable deliverables (CSP, QBR Pack, MSP Report, Handover Brief, CLI Runbook).

For how ARIA actually compares to NetApp's own Digital Advisor product -- verified overlap, genuine structural
edges, one previously-claimed edge that turned out to be false, and prioritized next work -- see the
"Competitive positioning vs NetApp Digital Advisor" addendum near the end of this file.

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
4. **Local Reference Library** — `data/firmware_baselines.json`, `data/security_bulletins.json`, `data/imt_interop.json` (20+ vendors, expanded from ~11), `data/ecosystem.json`, `data/version_catalog.json`, `data/eoa_database.json`, plus embedded EOA platform lists, CVE database, upgrade caveats, MetroCluster ISL specs
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
7. **Fleet-Aware Deliverable Mapper** (v4.0.0, deliverable count later grew to 15 — see the "Deliverables" addendum below) — deliverables receive fleet-relevant enrichment references. Articles scored by ONTAP version match (+30), platform family (+20), model match (+25), operational category (+10). Minimum score 5 required for inclusion.
8. **Enrichment Intelligence UI** (v4.0.0) — KB Intelligence Summary Panel (aggregate stats, fleet profile, per-category breakdown), enrichment badges on deliverable cards (★ N KB refs pills), and rich contextual intelligence engine (`getArticleContext`) generating CLI commands, effort estimates, and fleet-specific remediation steps per matched article.

9. **Platform-aware telemetry: StorageGRID, E-Series, ONTAP** (v5.6.203-5.6.205) — Harvested in `server.py` by small merge queries kept separate from the main system queries (Active IQ's field-count limit): `ESERIES_CAP_FIELDS` (StorageGRID topology/tenants/buckets/ILM, per-site capacity, power/heat, drive inventory + firmware, hardware limits, ONTAP upgrade history, E-Series NVSRAM, ARP/AI and timezone files) and `ONTAP_EXTRA2_FIELDS` (adapter/FC inventory, Cloud Insights hosts, talking points). Output fields `storagegridTopology` and `platformExtras`, carried through `enrichSystemTelemetry`. Analysis lives in `app.js`: `_dfStorageGridView` (grids + findings) and `_dfPlatformInsights` (power, drives, headroom, history, adapters). Surfaced in the Technical Audit StorageGRID card, Action Planner tabs 26 (StorageGRID) and 27 (Platform Insights), and the deliverables (TAM Success Plan, QBR, Exec Risk Assessment, Handover, MSP, Risk & Remediation, Security, Sustainability, Customer Report, Value, plus findings in the proposals and tracker import).
11. **StorageGRID in the risk engine** (v5.6.206-5.6.211) — Extras queries (`ESERIES_CAP_FIELDS`, `ONTAP_EXTRA2_FIELDS`) run through `_fetch_rows_all_scopes()` so restricted accounts (watchlist-scoped, no `unfiltered_system_access`) are harvested too; the systems query passes `includeStorageGridNodes: true`. The client merges duplicate systems from several accounts (fills empty fields) and resolves every StorageGRID system, node or admin, to its grid. Node counts come from the grid (`nodeTotal`: installed count, topology roster, fleet members), broken out by role and form factor (`_dfSgForm`: VMware = virtual, STORAGE_GRID_APPLIANCE / SG-series = physical, BARE_METAL). `_dfStorageGridView` raises findings (single-site, ILM, versioning/object lock, nodes not reporting to Active IQ, stale AutoSupport, single admin/gateway node, hardware end of support, models under NetApp end-of-availability notice CPC-00602, capacity, support term); `_SG_RECS` supplies a recommendation and steps for each, and `applyStorageGridRisks()` injects them into each grid's admin-node `risks` so they appear in Technical Risks, counts, deliverables and the tracker like any Active IQ risk. Per-node health (open risks, last AutoSupport) comes from the matched fleet system. ILM rules are shown "as reported by Active IQ": the API has no active-policy flag.
   - Browser cache schema is `aiq_systems_schema_v16`; `APP_VERSION` (app.js ~line 30) must match `version.json` and the top `APP_CHANGELOG` entry.
10. **Success Plans with real progress** (v5.6.205) — the harvest query and create/update mutations were previously invalid (`objectives` without sub-fields, non-existent `tamNotes`; the real field is `notes`). Plans now carry objectives -> milestones -> actions, and `_cspProgress` computes milestone/action completion for the Success Plans tab and deliverables.
   - Confirmed Active IQ API limits (do not re-investigate): no E-Series/StorageGRID port or WWPN fields, no parts-logistics hub status (only RMA parts), no per-relationship SnapMirror detail, no Mediator/AUSO state, ILM time periods are days.

---

## 3. File Inventory & Purpose

### Core Application Files

| File | Size | Purpose |
|------|------|---------|
| `server.py` | 572 KB / 10,245 lines | Central HTTP proxy, SQLite cache, GraphQL harvester, enrichment engine (9 scanners including the hardware-docs harvester), version catalog, ASUP handler, TLS auto-config, cluster name derivation, E-Series hardware synthesis |
| `app.js` | 2.30 MB / 38,337 lines | All frontend logic: state management, API calls, tab rendering, enrichment display, remediation plan generator, reference library, dynamic version management, platform-aware upgrade paths (ONTAP + StorageGRID + E-Series), deliverable DR/capacity/adoption intelligence, controller rear-panel SVG drawings |
| `index.html` | 125KB / 1,597 lines | Production dashboard SPA (8 nav views, sidebar nav, search, modals) |
| `index_src.html` | 129KB / 1,694 lines | Development/source version of dashboard — includes ASUP import modal DOM + enhanced error handling |
| `styles.css` | 31 KB / 1,396 lines | Complete dark-mode design system with CSS custom properties, responsive layouts, animations |
| `chart.js` | 208KB | Bundled Chart.js library |
| `hw_docs_harvester.py` | — | Fetches NetApp's official hardware/cabling documentation per platform, writes `data/platform_hardware.json` |
| `launcher.py` | 7.8KB | Desktop launcher (pywebview native window + embedded CORS proxy + fallback browser) |
| `asup_parser.py` | 25KB | Offline ASUP bundle parser (ONTAP, StorageGRID, E-Series) with ARIA schema normalization |
| `reference_harvester.py` | — | Dedicated reference harvester tool for harvesting and updating offline reference libraries, data catalogs, IMT interop (20+ vendors), and EOA databases |

### Configuration & Data Files

| File | Purpose |
|------|---------|
| `aiq_config.json` | Stores refresh token, watchlist IDs, TAM info |
| `version.json` | Source of truth for version number (currently 5.6.136) |
| `data/platform_hardware.json` | Harvested per-platform port/slot assignments from NetApp's official docs (feeds the rear-panel documentation panel) |
| `data/firmware_baselines.json` | Ground-truth firmware recommendations (ONTAP, SP/BMC, shelf, disk, StorageGRID, SANtricity) |
| `data/security_bulletins.json` | Local CVE/NTAP advisory database for offline security matching |
| `data/imt_interop.json` | Interoperability matrix database covering 20+ vendors (was ~11) |
| `data/version_catalog.json` | Scraped version catalog data for OS/software updates |
| `data/eoa_database.json` | End-of-Availability (EOA) & End-of-Support (EOS) hardware/software lifecycle database |
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
| `README.md` | Comprehensive user & developer manual (1,000+ lines) |
| `CHANGELOG.md` | Full release history (v1.0.0 through current) |
| `LEGAL.md` | IP ownership declaration |
| `LICENSE` | Proprietary license (Obi1 - FZCO, non-commercial free, commercial requires consent) |

### Development / Debug Tools (~30 files)

All `check_*.py`, `debug_*.py`, `diag_*.py`, `probe_*.py`, `test_*.py`, `validate_*.py`, `verify_*.py`, `trigger_*.py`, `dump_*.py`, `find_*.py`, `fix_*.py`, `inspect_*.py`, `analyze_*.py` files are **development-time utilities** for API exploration, schema introspection, data verification, and debugging. They are not used in production.

Also includes: `brace_report.txt` (JS syntax audit), `fix_guidelines.ps1` (one-off app.js patch), various `*_results.json` / `*_data.json` files (probe output artifacts).

---

## 4. Dashboard Views (8 Primary Navigation Areas — `index_src.html`'s sidebar, `data-tab` values shown)

### View 1: Overview (`overview`)
- 4 KPI cards (Total Systems, Critical Risks, Active Warnings, Expiring Contracts)
- Chart.js graphs (Storage Savings/Efficiency, Capacity by System)
- Monitored Systems & Clusters table with sorting, CSV export, JSON import/export

### View 2: Technical Audit (`tam`, TAM Module)
- Multi-select system filtering
- Controller Node Port & Link Topology visualization — SVG rear-panel scale drawings per platform family, numbered ports, LIF-to-port highlighting, FC-port inference from LIFs, hardware documentation panel (see the "Technical Audit rear panels" addendum below)
- SANtricity E-Series Hardware Audit card
- Node strip: one entry per real node, classified by true platform (E-Series controllers inside a StorageGRID node are listed as StorageGRID, duplicates collapse, unlisted grid records hidden behind a toggle); StorageGRID card; MetroCluster card follows the selected node; per-platform OS upgrade target
- SVM & Protocol Security Audit
- Active Predictive Risk Signatures table with slide-out remediation modal
- OS Upgrade Advisor with hop-by-hop upgrade path calculator (includes IOM6 shelf upgrade-target checks)
- Network Switch & Fabric Validation table
- Active Security & Technical Bulletins (CVE matching with CISA KEV integration)

### View 3: Support & Ops (`sam`, SAM Module)
- Contract status cards (SupportEdge, warranty, EOA/EOS lifecycle)
- 3rd-Party Virtualization tracking
- AutoSupport status monitoring
- Logistics & Customer Sales Health
- Active Support Cases table
- Outstanding Field Actions (FA)
- Capacity forecasting/growth projections, performance (IOPS/latency) trends

### View 4: Value & ROI (`csm`, CSM Module)
- Storage Efficiency Savings metrics
- SnapMirror data protection coverage (count-only; Active IQ does not expose destination/lag)
- Capacity & Performance Forecasting with runway projections
- Feature adoption scorecard (25-point categorized TAM/MSP checklist, 2-column: Operations & Security, Data Protection & Lifecycle) — FabricPool is not part of this score
- Historical trend vs. last week/month/quarter

### View 5: Action Planner (`plan`)
- Fifteen customer-ready deliverables (A-O), generated by `compileExtendedDeliverables()` — QBR pack, security brief, risk & remediation brief, sustainability report, customer health report, and more
- 27 tabs in five groups, including StorageGRID (26), Platform Insights (27), SAN & NAS Storage (25) and Firmware Currency (18); every tab has Download Word (`downloadPlanSectionWord`); dedicated Word reports for StorageGRID and Firmware Currency
- Phased remediation plans, recommended-plan table, upgrade sequence (`_dfActionPlan`/`_dfUpgradeWaves`)
- ITIL change management governance
- Downloads as `.txt`/`.md`/structured A4 `.docx`, per-download format prompt

### View 6: Risk & Recommendation Tracker (`tracker`)
- Persistent, cross-sync tracking of open risks, recommendations, and action items with status, owner, and due date — survives re-harvests instead of resetting on every refresh

### View 7: Success Plans (`success`)
- Real Active IQ Success Plans (read AND write): owner, lifecycle stage, status, objectives, milestones and actions with progress (`_cspProgress`)
- Plans ARIA submits carry the complete affected-system list (notes fallback when a field is too large); mutations use `notes:[{message}]` and `results{ id type success errors }`

### View 8: Settings & Config (`settings`)
- API Authentication (refresh token, base URL, offline demo toggle)
- Watchlist Scope management
- Enrichment sources / Quick Actions (sync, diagnostics, update)
- System Serial Numbers configuration
- Custom Subgroups Manager
- Full System Metadata & Logistics Editor (per-system identity, contacts, sales data, CSAT)
- GraphQL Query Console & Sandbox

---

## 5. What Is Complete (✅)

### Core Functionality
- AIQ authentication (OAuth refresh token → access token exchange)
- System discovery and inventory harvesting via GraphQL
- Risk/action harvesting
- Capacity data with per-aggregate trend charts and runway forecasting
- 8-component Account Health Score engine (including HW Firmware Currency at 8%, was 7 components)
- IMT interoperability engine covering 20+ vendors (expanded from ~11)
- Reference harvester tool (`reference_harvester.py`) and offline data catalogs (`data/imt_interop.json`, `data/version_catalog.json`, `data/eoa_database.json`)
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
- Deliverable intelligence enrichment: DR coverage, capacity forecast, feature adoption sections injected into all 15 deliverables
- Platform-specific controller rear-panel backplate visualization (8 hardware families)
- SVM/LIF inventory harvesting via GraphQL vserver endpoint
- Harvest merge-back guard preventing transient API failures from wiping cached data
- Module-level vserver cache for localStorage resilience

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
| ~~**v3.7.0 CHANGELOG entry**~~ | ✅ Done in v4.0.0 | All versions through 4.0.2 now documented |
| ~~**README version badge**~~ | ✅ Done | Badge shows 4.0.2 |
| **Data protection coverage %** | SnapMirror count exists | Volume-level protection ratio calculation missing |
| **`index.html` vs `index_src.html` sync** | `index_src.html` has ASUP modal; `index.html` does not | Need to decide which is canonical and sync |
| **Firmware Phase 2** | Phase 1 (Unverified badge) complete | Model-specific SP/BMC baseline research and `data/firmware_baselines.json` expansion |

---

## 7. What Is Not Started (❌)

| Item | Notes |
|------|-------|
| ~~**Performance Analytics tab**~~ | ✅ Shipped as Action Planner → Performance (tab 20) |
| **SLA Compliance tab** | Needs customer SLA definitions |
| **Configuration Drift tab** | Needs baseline config to compare against |
| **License compliance data** | Need to discover correct AIQ API field |
| ~~**EOS/EOA dates**~~ | ✅ Active IQ's own `hardwareModel.endOfAvailability/endOfSupport` plus the Reference Library |
| **Auto-updater mechanism** | No self-update capability |
| **Code signing** | Needs certificate |
| **Customer logo in PDF exports** | Need logo upload feature |
| **WCAG accessibility** | Not started |
| **Keyboard navigation** | Not started |
| ~~**Multi-tenant support**~~ | ✅ Multiple Active IQ accounts fused into one fleet, customer/watchlist/group scoping (see competitive addendum). Per-user RBAC is still not started |
| **Scheduled report generation** | Cron-style automated reports |
| **Email delivery of PDF reports** | Needs SMTP integration |
| **ServiceNow / Jira integration** | Action tracking integration |
| **REST API for CI/CD** | Programmatic access |
| ~~**Historical trend database**~~ | ✅ `system_snapshots` captured every sync; Risk Trend chart and 30/60/90-day deltas, scoped per customer, watchlist or group |
| **Ansible playbook generation** | From recommendations |
| **RBAC** | Role-based access control for shared deployments |
| ~~**StorageGRID version audit**~~ | ✅ Latest-supported version per node (SG models resolve to the StorageGRID release), mixed-version finding, Action Planner StorageGRID tab |
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
| 4.0.2 | 2026-08-01 | Platform-specific rear-panel backplate, SVM/LIF enrichment, vserver GraphQL harvesting, harvest merge-back guard, networkPorts field, card overflow fix |
| 4.0.7 | 2026-08-04 | 8-component Account Health Score (added HW Firmware Currency @ 8%), IMT interop expanded to 20+ vendors, reference harvester tool (`reference_harvester.py`), new data files (`imt_interop.json`, `ecosystem.json`, `version_catalog.json`, `eoa_database.json`) |

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
2. ~~**Add v3.7.0 entry to CHANGELOG.md**~~ — ✅ Done (all versions through 4.0.2 documented)
3. ~~**Update README.md version badge**~~ — ✅ Done (badge shows 4.0.2)
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

- **`computeSupportCaseHealth(sys)`** — Line ~11992. Computes a 0–10 support case health score from real case data (severity penalties, volume penalties, aging penalties, escalation penalties, resolution velocity bonuses). Replaces the legacy fake CSAT sentimentScore.
- **`computeAccountHealthScore(targetSystems)`** — Line ~12100. Computes the 0-100 Account Health Score using a weighted formula of 8 components (ASUP 15%, ARP 12%, OS FW 12%, HW FW 8%, Contracts 13%, Risks 20%, Data Reduction 10%, Case Health 10%).
- **`computeMTTR(allSupportCases)`** — Line 11060. Calculates the Mean Time to Resolve in days for all closed cases.
- **`computeFeatureAdoptionScore(sys)`** — Line 11088. Evaluates a 25-point best-practice checklist to return an adoption score (0-25) and percentage. Checks are categorized into Operations & Security (15) and Data Protection & Lifecycle (10).
- **`computeCostOfInaction(targetSystems)`** — Line 11118. Computes the weighted Cost of Inaction urgency score based on risks, CVEs, capacity runway, and lifecycle status.
- **`_buildControllerBackplate`** — Platform-specific rear-panel HTML builder
- **`compileSvmLifInventoryText`** — SVM/LIF inventory text generator for deliverables
- **`getSystemSvms`** — SVM data retrieval with multi-source fallback

---

*This document was generated by analyzing all 89+ project files and 11 previous conversation artifacts. It serves as the single source of truth for project state recovery after context loss.*


## Deliverables (v5.6.83 - v5.6.104)

- Fifteen deliverables (A-O) built by `compileExtendedDeliverables()` in `app.js`; shared fact helpers (`_dfContractFacts`, `_dfArpFacts`, `_dfCveIndex`, `_dfSustain`, `_dfRunwayText`, `_osKnown`/`_osIsCurrent`, `_dfCollapseFindings`, `_dfMetroClusters`) give every document the same numbers.
- Planning helpers (`_dfActionPlan`, `_dfUpgradeWaves`, `_dfRefreshPlan`, `_dfCapacityTrend`) drive the "Decisions needed" block, the recommended-plan table, upgrade sequence, refresh planning and capacity trend.
- Downloads: `triggerFileDownload()` writes `.txt`, `.md` or a structured A4-portrait `.docx` (built in-app by `_buildDocx`); `_askFormat()` prompts per download.
- FabricPool is not part of the feature-adoption score or any scorecard; SnapMirror is a count only; MetroCluster pairs are inferred.
- `tools/audit_deliverables.py` is the regression check for all of the above.


## Technical Audit rear panels and hardware documentation (v5.6.105 - v5.6.134)

- `_buildControllerBackplate()` in `app.js` draws the selected controller's rear panel as an SVG scale drawing (`_LAY` layouts per family: fas8200, mid7 (FAS8300/8700, A400/C400), a800, chassis8u (A700/A900/FAS9000/9500), a700s, a320, a250, fas2800, a220 (A220/C190/A150/FAS2720/2750), fas50, a20 (A20-A50/C30/C60), gen11 (A1K/A70/A90/FAS70/90), afx/afx2k, plus E-Series canisters and StorageGRID appliances). One `_ZOOM` for all. Reported ports (Active IQ `networkPorts`, Ethernet only) are placed by name; FC ports come from LIFs (`_bpAddLifPorts`, inferred); breakout lanes are grouped (`_pGroup`); unreported connectors are dashed.
- Selection state is one function (`_bpRefresh`) over {hovered port, pinned port, hovered LIF row, pinned LIF row}; nothing else toggles highlight classes. LIF -> ports via `bpLifPorts` (ifgroup members from `interfaceGroupOwner`).
- StorageGRID: network roles per connector (`_SGR`), internal compute<->storage interconnect diagram (`_sgTopo`), compute controller drawn above storage.
- `hw_docs_harvester.py` -> `data/platform_hardware.json` (scanner 9 in `EnrichmentScheduler._do_kb_scan`); the app shows it in the collapsible documentation panel (`_bpFillDocs`). Source is the NetAppDocs `ontap-systems` AsciiDoc on GitHub (same text as docs.netapp.com/us-en/ontap-systems/<platform>/). `tools/verify_rear_panels.py` is the regression check that every documented port has a place on its drawing.
- Rule that cost time: read each platform's install/cabling TEXT, not only the diagrams (slot roles and port names are in the text; the FAS50 and AFX 2K were wrong until the text was read).


## Demo data fixes, Action Planner regroup, shelf firmware currency (v5.6.135 - v5.6.138)

- Demo/mock data: `_demoPortBucket()`/`_DEMO_PORT_TEMPLATES`/`_demoSynthPorts()` match a curated profile's `networkPorts` to the SAME rear-panel layout bucket as the system's platform label, instead of a loose class regex that could hand a fictional system a completely different chassis's ports. The `vservers`/LIF remap in `_demoHydrateSystem` retargets any data LIF sitting on a port the node's own `networkPorts` calls non-DATA, operating on the real nested shape (`v.logicalInterfaces[].serviceConfiguration.dataProtocols` / `.failoverConfiguration.{homePort,currentPort}`), and now also gives every demo LIF's `worldWidePortName` a per-system-unique tail (was cloned verbatim from the curated profile, so every demo system sharing a profile had byte-for-byte identical WWPNs).
- Action Planner's 19-section tab row is five bordered, labeled groups (Overview / Risk & Security / Operations & Health / Account & Commercial / ★ Customer Deliverables), each with a one-line description, instead of one flat button list. Section numbers/links/print output unchanged.
- Shelf module firmware currency is live: Active IQ's GraphQL schema has no per-shelf "currently installed" field (confirmed via live introspection — `Shelf`, `ShelfModuleHardwareModel`, `Bays` all lack one); the field that has it, `shelvesSummary { firmware { currentVersion recommendedVersion } } }`, is fetched as its own harvest pass in `server.py` (`SHELVES_SUMMARY_FIELDS`) — adding it inline to the main systems query hit Active IQ's GraphQL query-complexity ("maximum height") limit and silently degraded the whole harvest to a thinner tier. `_resolveShelfModules(sys)` in `app.js` is the shared resolver (Active IQ's own reported values preferred over the local reference-library baseline); `computeFleetFirmwareSummary()`'s composite score is now SP 20% / MB 20% / DQP 15% / Shelf 15% / Drive 30% (was SP 25/MB 25/DQP 20/Drive 30), and every deliverable that quotes "HW Firmware Currency" shows the Shelf% component. Two previously-dead shelf-firmware code paths (As-Built Document's shelf table, Action Plan's shelf-drift detector) were keyed on `sh.moduleType`/`sh.firmwareVersion` — neither a real `Shelf` field — and fixed against the same shared resolver.
- Cluster node pairs are sorted adjacent (by cluster name, then system name) in the Firmware Currency system list and the Recommended OS Upgrades list, instead of raw harvest-fetch order which could interleave unrelated clusters' nodes.


## Critical: silent data loss after every sync, and switch reporting audit (v5.6.139 - v5.6.141)

- **The headline finding**: `loadConfig()` in `app.js` (reads auth tokens/settings from localStorage) also unconditionally re-hydrates `state.systems` from localStorage as an undocumented side effect, every time it's called -- not just at the one genuine boot-time call. `loadProductionData()` calls `updateStatusIndicators()` at its own end purely to refresh the connection-status dot; that called `loadConfig()` just for the token; that silently reloaded the whole system list from localStorage, overwriting the correct, freshly-harvested in-memory data with whatever `saveSystems()` had just written to localStorage moments earlier in the SAME sync. That localStorage write is quota-limited (69.6MB full dataset on one real fleet vs ~5-10MB localStorage), so `saveSystems()`'s fallback strips `switches`, `vservers`, `risks`, `supportCases`, `fieldActions`, `securityBulletins`, `hypervisors`, `projections`, `logistics`, `contacts`, `salesHealth`, `autosupport`, `lifecycleEvents` before writing. Net effect: every harvest correctly populated all of these fields, then silently wiped them seconds later on the SAME page load -- confirmed live, switches went 295 systems -> 0 within one load. Fixed with a `restoreSystemsFromCache` parameter on `loadConfig()` (default true for the one genuine boot caller; `updateStatusIndicators()`/`runAPIDiagnostics()` now pass `false`). This is very likely the real explanation behind most "flaky/thin data" reports across the app generally, not just switches -- found while investigating a user report specifically about switches, but the bug itself is field-agnostic.
- Switch reporting audit that led to finding the above: Active IQ's own `cluster.switches` field can report the SAME physical switch twice under two different device-name suffixes from two discovery paths (MAC-suffixed vs serial-suffixed, different IP, differently-phrased firmware string) -- 14 such pairs in one account's harvest; deduped in `server.py` by normalized device name (`_sw_norm()`), keeping whichever duplicate Active IQ actually monitors. Server-side model inference now also checks the firmware STRING (not just the device hostname), and recognizes Huawei/HP/Aruba/Ubiquiti in addition to Cisco/Brocade/NVIDIA/Broadcom (`OTHER`/blank dropped from 50 to 22 genuinely unidentifiable stragglers). Added two real Active IQ switch fields that were never queried: `network` (a reliable CLUSTER_NETWORK/MANAGEMENT_NETWORK/STORAGE_NETWORK/OTHER enum) and `supportContract` (start/end date -- real switch EOS/warranty tracking, shown as a color-coded badge). A switch seen only via local port connectivity now gets an explicit "Unknown" row instead of silent absence; one reported by both sources merges into a single row carrying both CSHM data and local port-cabling detail.


## Watchlist auto-discovery: the real REST endpoint (v5.6.142)

- Watchlist auto-discovery in `server.py` (`_early_watchlists`, the "14. Try fetching watchlists" block, and the `/api/watchlists` handler) tried five different guessed REST path/response-shape combinations for years of iteration and never once found a working one -- every candidate returned 404 ("Unsupported endpoint") or, on two paths that do genuinely exist, 401. The real, documented endpoint (found via NetApp's internal API catalog, `aiq.netapp.com/catalog/internal/api-reference/activeiq-public/watchlist-v2`, user-supplied) is `GET /v2/watchlist/list`, authenticated with a header literally named `authorizationToken` carrying the raw access token -- **no `Bearer ` prefix, and not the standard `Authorization` header name** every other REST/GraphQL call in this file uses. That header mismatch, not the path, is what produced the 401s on paths that do exist (e.g. `/v2/watchlist/action`, which is actually a *create*-watchlist endpoint per its own docs, not a list). Response is `{"results": {"watchlist": [{"watchlist_id", "watchlist_name", "wl_level", "wl_category", "created_date", ...}]}}` -- snake_case, nested one level deeper than any of the guessed shapes checked for. All three call sites now use this endpoint/header/shape; confirmed live against a real account with previously-undiscoverable watchlists (its own `watchlistId` config field was always blank, relying entirely on this broken auto-discovery) -- now correctly finds all 4 of its real watchlists. A follow-up sweep for other similarly-broken REST endpoints (asked explicitly) found none -- every other direct REST call is the confirmed-working token exchange; everything else goes through GraphQL, a different technique (schema introspection, not path-guessing).


## ONTAP Select: no physical rear panel (v5.6.143)

- `renderNodeVisualLayout()`'s `isCloud` detection (`app.js`, feeds `_buildControllerBackplate`) only matched the platform string or `platformType` containing "cloud" -- catching Cloud Volumes ONTAP but not ONTAP Select, which reports `platformType: "ONTAP-SELECT"` and a `platform`/`model` string that's a VM *size* ("M300", "FDvM300"), not a chassis name. ONTAP Select fell through to the physical-chassis SVG engine, found no layout bucket for "M300", and rendered a blank panel captioned "physical layout for this model is not built in" -- true but misleading, since it's a VM with no chassis at all, the same situation Cloud Volumes ONTAP already has a dedicated "Virtual Appliance, no physical rear panel" card for. `isCloud` now also matches `ONTAP-SELECT`; the card's provider-label logic (previously defaulted to "GCP" for anything that wasn't AWS/Azure -- would have been wrong for Select) now checks for an actual cloud-provider name and falls back to "ONTAP Select (Software-Defined)" / "the VM's hypervisor (VMware/KVM)" instead of guessing a cloud provider that doesn't exist.


## Astra Data Store: same blank rear panel as ONTAP Select (v5.6.144)

- Asked explicitly to check for other virtualized platform types beyond ONTAP Select. Enumerated all 7 distinct `platformType` values in a real fleet: ASTRA (1 system), Cloud Volumes ONTAP (12), E-SERIES (214), HCI (15), ONTAP (888, all 33 models confirmed real physical chassis names), ONTAP-SELECT (644, fixed in v5.6.143), STORAGEGRID (514). Two needed investigation: ASTRA (has a real `ontapVersion` reported despite the unusual model name, suggesting ONTAP-based) and HCI (real rack hardware model names like H410S-2/H410C, suspected NOT virtualized).
- **ASTRA confirmed virtualized and fixed**: it's NetApp Astra Data Store, Kubernetes-native ONTAP -- no physical chassis, same "no rear panel exists" case as ONTAP Select, and it hit the identical blank "not built in" panel for the identical reason (`isCloud` didn't match `platformType === "ASTRA"`). `isCloud` now also matches `ASTRA`; the Virtual Appliance card gets Astra-specific copy ("Astra Data Store (Kubernetes-Native)" / "vNICs provisioned by the Kubernetes cluster network (CNI)") rather than reusing the VM-hypervisor or cloud-provider wording written for the other two cases. Verified live against the one real Astra system in the fleet (rendered correctly after the fix; an earlier live-verification attempt appeared to show an E-Series panel instead, which turned out to be a navigation artifact -- the "Google Inc." customer scope has ~19 other nodes and the node-tabs UI defaulted to a different one, not a rendering bug in the Astra fix itself).
- **HCI confirmed real hardware, correctly out of scope**: `platformType: "HCI"`, models H410S-2 (storage node)/H410C (compute node) are genuine physical rack-mounted chassis, not virtualized -- explicitly NOT given the Virtual Appliance treatment. It still has no rear-panel chassis layout built (so it also shows the blank "not built in" panel today), but that's a *different* bug class -- missing physical layout for real hardware, the same kind of gap FAS50/AFX2K had in earlier sessions -- not something this fix addresses. Flagged here as a known gap, not yet fixed.
- Also worth noting for future work: `_platformFamily()` (`app.js` ~line 17691) only returns `'storagegrid'` / `'eseries'` / `'ontap'` -- both ASTRA and HCI fall into the `'ontap'` catch-all for any code path keyed off that function (upgrade-path logic, CLI generation, etc.), not just the rear-panel renderer. Not investigated or changed this pass.


## E-Series systems silently misclassified as ONTAP (v5.6.145)

- User-reported blank rear panel (model "560", `platformType: "E-SERIES"`) led to a deeper bug than a missing chassis layout. `_platformFamily()` (`app.js` ~17707) -- the function that decides ONTAP vs. E-Series vs. StorageGRID for feature scoring (ARP/SnapMirror/FabricPool/HA), CLI command generation, change-verification steps, and the rear-panel renderer -- never checked Active IQ's own authoritative `platformType` field at all. It only guessed family from the `platform`/`model` string, on the documented theory (see the function's own comment) that real E-Series systems report a bare number never the words "e-series"/"santricity". That guess had a gap of its own: the numeric-model regex required exactly 4 digits starting with `28`/`29`/`40`/`57` (`/^(28|29|40|57)\d{2}$/`), so an older E-Series canister reporting a 3-digit model ("560", an EF560/E5600-family board) fell through every check and was silently treated as ONTAP everywhere in the app -- which is why its rear panel showed the ONTAP fallback caption ("ports are grouped by e0x/eNx slot naming") instead of any E-Series message.
- Fixed by adding `platformType` into the same detection test as one more authoritative signal (kept the existing platform/model guessing too, as a fallback for any data that doesn't carry `platformType`). While auditing the blast radius, found a second, larger instance of the identical class of bug: `_isPlatformStorageGRID()`'s substring list (`sg57`/`sg60`/`sg61`/`sg10`/`sg516`/`sg6`/`sg1`) was missing `sg58` -- so 12 real StorageGRID SG5800-family appliances ("SG5860") were also silently misclassified as ONTAP. Added.
- Verified live against the real fleet: before the fix, 13 of 215 E-Series-platformType systems (1x "560", 12x "SG5860") misclassified as `'ontap'`; after, 0. The "560" system's rear panel now correctly shows the E-Series "unrecognised model: physical layout not drawn" message (honest -- no invented diagram) instead of the wrong ONTAP-specific one.


## Same classification bug, three more places (v5.6.146)

- Asked explicitly to check for other misclassified systems beyond the "560" case. The v5.6.145 fix only touched `_platformFamily()` itself -- found the exact same E-Series/StorageGRID platform/model guessing independently reimplemented in three more functions, none of which checked `platformType` either: `enrichSystemTelemetry()` (`app.js` ~18022 -- the core per-system enrichment pass that drives `isONTAPBased`, support-level labels, and capacity multipliers for every system, live or mock) and two near-identical copies inside the TAM-tab node-visualizer code that toggle the E-Series Hardware Audit card on/off when switching between nodes. Same root cause every time: hand-rolled string/regex guessing copy-pasted independently rather than calling the shared `_platformFamily()` helper.
- Fixed all three: `enrichSystemTelemetry()` now checks `_genericFamily` (its own already-computed `platformType` value) first; the two node-visualizer copies now check `_platformFamily(activeSys) === 'eseries'` first. All three keep the old guessing as a fallback for any system whose data doesn't carry `platformType`.
- Verified live across the full real fleet (2,450 systems, all 7 platformType values): 0 misclassify via `_platformFamily()`. Also checked the reverse direction -- confirmed no real ONTAP system's platform/model string collides with the E-Series numeric-guess patterns, so broadening the check to trust `platformType` introduced no new false positives.
- **Found but explicitly not fixed** (flagged for a future decision, bigger than a classification patch): NetApp HCI storage nodes (`platformType: "HCI"`, models "H410S-2"/"SolidFire", 9 real systems) run Element OS (SolidFire), not ONTAP, but `_platformFamily()` only has three buckets (`storagegrid`/`eseries`/`ontap`) -- no Element OS bucket exists, so these fall into `'ontap'` and get scored on ONTAP-only features (ARP/SnapMirror/FabricPool/HA) that don't apply to them. Active IQ compounds this by reusing the `ontapVersion` field to carry Element OS version strings for these nodes (e.g. `"12.3.2.3"`, a format real ONTAP never produces) -- context-mismatched field reuse, the same pattern flagged elsewhere in this project's memory. The 6 HCI *compute* nodes ("H410C") are correctly ONTAP-based (they report a real ONTAP Select version, 9.12.1) and are unaffected. A real fix needs a fourth family bucket plus an audit of every ONTAP-specific feature check for whether it should exclude that bucket too.


## HCI classification fixed: 4th family, 'element' (v5.6.147)

- Asked to go ahead and fix the HCI gap flagged in v5.6.146. Added a 4th `_platformFamily()` bucket, `'element'`, detected via NetApp's own node-naming convention rather than guessing from version strings: storage nodes are named `H<model>S` (e.g. "H410S-2") or literally "SolidFire"; compute nodes are `H<model>C` (e.g. "H410C") and are deliberately left matching `'ontap'`, since they run a genuine ONTAP Select instance on top of the HCI hypervisor layer (confirmed live: they report a real ONTAP version, 9.12.1, not an Element OS version).
- The reason this was a small change despite touching classification used everywhere: an audit of every `_platformFamily(s) === ...` call site (grep across the whole file, ~90 matches) found nearly all of them already filter explicitly on `=== 'ontap'` for ARP/SnapMirror/FabricPool/HA/MetroCluster/ASA-r2/dedupe-compression scoring, CLI generation, and report text -- none check `!== 'eseries' && !== 'storagegrid'` as an inverse test. That meant the new `'element'` bucket was automatically excluded from all of those the moment it existed, with zero changes needed at those call sites. Only genuinely three-way branches needed explicit updates: `_nonOntapVerifyLines()`/`_nonOntapRollbackLines()` (were emitting StorageGRID Grid-Manager guidance for Element OS nodes -- now emit SolidFire-specific guidance: cluster/node health, iSCSI path counts), `enrichSystemTelemetry()`'s `isONTAPBased` flag (now also excludes `'element'`, so the enriched `ontapVersion` field correctly comes back `null` instead of the bogus Element OS version string), the NETAPP_SECURITY_BULLETIN_DB auto-match (excluded `'element'` for the same false-CVE-match risk E-Series' SANtricity version numbers already had), and a few cosmetic family-label maps (`famLabel`, the customer-report "Estate:" line, the renewals demo-data `platformType` field, the upgrade-plan family label).
- Verified live against the real fleet: 9 of 15 HCI systems (all storage nodes: 7x "H410S-2", 2x "SolidFire") now classify as `'element'`; the 6 "H410C" compute nodes stay `'ontap'`; 0 false positives against the other 2,435 systems in the fleet. `enrichSystemTelemetry(storageNode).ontapVersion` now correctly returns `null`.
- Deliberately NOT touched: the rear-panel renderer. HCI storage nodes still show the physical-chassis "unrecognised model" fallback there (real rack hardware with no layout drawn, same gap FAS50/AFX2K had) -- that's a different bug class from this classification fix and wasn't part of what was asked.


## Sync poll timeout too short + watchlist sidebar ordering (v5.6.148)

- User saw a "Sync failed: Sync timed out after 6 minutes" alert telling them to check the launcher (`app.js`, `loadProductionData()`'s background-sync poll loop, ~33787). Checked `/api/sync-status` live while it was up: `isSyncing: true`, well past the 6-minute mark -- the server was harvesting correctly the whole time; the client poll just gave up watching and threw a scared, misleading failure ("make sure the app is running" when it plainly was).
- Root cause traced back to this session's own earlier fix: watchlist auto-discovery (v5.6.142) now correctly finds a real account's full watchlist set -- confirmed live in `aiq_config.json`, both accounts' `watchlistId` fields are now blank (relying entirely on auto-discovery) and the top-level `watchlistIds` cache holds 20 real IDs, versus the old broken discovery that silently found 0. Each watchlist is its own paginated GraphQL query with its own TAM->Efficiency->Minimal tier-fallback retries, so 20 real watchlists across 2 accounts is genuinely more work than the 6-minute timeout was ever tested against (it predates the watchlist fix entirely).
- Fixed two ways: raised `POLL_TIMEOUT` to 20 minutes, and -- more importantly -- changed what a timeout actually does. The harvest runs server-side, independent of the browser tab, so a client poll timing out was never really a sync failure, only this page giving up watching. On timeout it now falls back to loading whatever's currently cached (a prior completed sync) instead of throwing, and shows "still refreshing in background — reload in a few minutes for the latest" in the status bar rather than an alarming failure alert.
- Also fixed in the same pass, a related user request: the sidebar's "Active IQ Watchlists" list rendered in whatever order the harvest/auto-discovery returned watchlists (API/pagination order) -- barely noticeable with a couple of watchlists, much more so now that a real account's full 20-watchlist list is visible for the first time. Sorted alphabetically by name (`locale-aware`, numeric-aware compare) in the sidebar render function (`app.js` ~32024).


## Two more silent data caps found in the harvester (v5.6.149)

- User noticed a node's rear panel showed no LIFs. Traced it: the system had 0 vservers reported -> the cluster's own SVM/capacity/HA data was entirely missing -> `server.py`'s `clusters()` GraphQL query (~2062) takes NO watchlist argument at all, unlike `systems()` which is explicitly queried per watchlist -- it only sees whatever default privilege scope the token has. Once watchlist auto-discovery started finding a real account's full set (v5.6.142), the unscoped call kept returning a real but badly incomplete count (109 clusters for 2900+ systems -- ~27 systems per cluster, implausible for real ONTAP HA pairs), because it can't see clusters only reachable via the newly-discovered watchlists. The account already had a "retry scoped to each watchlist" fallback for exactly this kind of gap, but it only ever fired when the unscoped call returned exactly 0 clusters -- never for a non-zero-but-incomplete result, so it never recovered here. Fixed: now always runs when any watchlists are known, merging by cluster id instead of only replacing an empty list.
- Verified live against the real fleet: NetApp account's cluster count went from 43 to 313; ONTAP systems with SVM/LIF data went from 196/1393 (14%) to 890/1393 (64%); several watchlists that were completely empty (Vodacom Tanzania, IEC ONTAP, Mauritius Commercial Bank) are now fully populated.
- Asked explicitly to check for any other silent caps in the same file. Found one more, already close to being hit live: the loop that resolves each watchlist's system membership for the sidebar (`watchlists_out`, ~3870) was hard-capped at the first 20 watchlists. With a real account now auto-discovering 23, the last 3 (Barclays Bank PLC, AXA, Orange Business Services -- 97/148/116 systems) silently never got resolved. The risk-instances and cases loops elsewhere in the same function already iterate every configured watchlist with no such cap, so there was no real reason this one should differ. Cap removed; verified live all 23 now resolve.
- Also investigated on request: shelf and motherboard firmware showing unknown for an unusually large number of systems. Verified directly against the live API with standalone probe scripts (not just reading the harvest code) that this is real, accurate data, not a bug -- it isolates to one specific customer (Google: 0/30 systems with motherboard firmware, 0/5 with shelf firmware, all clean empty GraphQL responses with no errors), while a same-day newly-discovered watchlist for a different customer (STC) reports perfectly (30/30). Consistent with that one customer running restricted AutoSupport telemetry -- an upstream data-completeness fact, not a harvest scoping gap. Nothing changed for this.
- Systematic sweep of the rest of `server.py` for the same class of bug (a hard cap or exception silently discarding partial results): systems, risk instances, cases, E-Series capacity merge, and shelf-firmware-summary merge all already iterate every configured watchlist with no cap. The only remaining numeric limits are generous per-watchlist pagination safety bounds (50 pages x 100/page = 5,000 systems per single watchlist) -- not a realistic ceiling for any real TAM/MSP watchlist, just a sane infinite-loop guard.


## Demo mode had zero shelf firmware representation (v5.6.150)

- Following the shelf-firmware investigation above, a screenshot of the Firmware Currency section's Shelf FW tile showing "0/42 unknown" turned out to be from demo/mock mode, not live data. Checked: no curated `MOCK_SYSTEMS` profile ever carried the `shelvesSummary` field `_resolveShelfModules()` (`app.js` ~24950) actually reads for firmware currency -- some curated profiles DO have a rich, hand-authored `shelves` array with real module names (e.g. a FAS9000 profile with 13 real `DS224-12`/`IOM12` shelves), but none of them ever paired it with the separate `shelvesSummary` entry the comparison logic needs, so every demo system showed unknown regardless of how detailed its shelf hardware otherwise was.
- Added `_demoSynthShelves()`/`_demoShelfSummaryForModule()`/`_demoPickShelfModule()` (`app.js` ~8014), synthesizing shelf module + firmware currency from the same `REFERENCE_LIBRARY_FIRMWARE_BASELINES` table the real feature compares against, so demo mode exercises the identical current/behind/unknown logic. Module choice follows the real NSM100/NSM100B (NVMe, current-gen AFF/C-Series/ASA r2) vs IOM12/IOM12B/IOM12G (SAS, classic-gen) split; ~65/25/10 current/behind/unknown mix, seeded per-system like the existing `_demoSynthPorts` networkPorts fallback. Wired into `_demoHydrateSystem`: when a curated profile already has real shelf hardware, the firmware entry is derived FROM that hardware's own module name (so the two fields can't disagree); when neither exists, both are synthesized together.
- First pass wrongly gave Cloud Volumes ONTAP demo systems fake physical shelf hardware (caught by testing, not by inspection) -- these are virtualized with no physical shelves at all, the same reasoning behind the real "Virtual Appliance, no physical rear panel" card CVO/ONTAP Select/Astra already get elsewhere. Added an explicit exclusion (`/cloud|ontap[\s-]?select|astra/i` on the platform string) before synthesizing anything.
- Verified live in demo mode: 108/108 physical ONTAP systems now have shelf firmware data (was 0/108), with a realistic 55/40/13 current/behind/unknown split across 417 total shelves; 0 virtualized systems incorrectly got shelf data.


## Competitive positioning vs NetApp Digital Advisor (2026-09-28)

Asked to compare ARIA against NetApp's own product -- Active IQ Digital Advisor, recently renamed "Digital
Advisor" and folded into BlueXP. Researched live (not from training-data memory) via NetApp's own docs/
community pages, then cross-checked every claim against ARIA's actual code, not assumption. Recorded here so
a future session doesn't have to redo the research, and so deliverable copy doesn't oversell a claim already
found to be false.

**What Digital Advisor actually does** (sourced 2026-09-28): watchlists (up to 100, 15,000 systems each,
cross-customer within one login's access); Upgrade Advisor (step-by-step GUI+CLI plans, ANDU-aware, now
handles mixed-patch-level clusters and EOL-with-grace-period targets, PDF/Excel export); Security Report
(unified ONTAP security posture across clusters/SVMs/volumes); sustainability score (power/carbon/heat,
now on E-Series/StorageGRID too); VMware inventory (vCenter/ESXi/VMs) for interop checks; tiered feature
depth per platform (e.g. ClusterViewer is ONTAP/CVO-only -- the same "not every platform gets equal
treatment" pattern this session spent hours untangling in ARIA's own `_platformFamily()`).
Sources: [Digital Advisor features](https://docs.netapp.com/us-en/active-iq/concept_understand_activeiq_features.html),
[What's new](https://docs.netapp.com/us-en/active-iq/reference_new_activeiq.html),
[Upgrade Advisor](https://docs.netapp.com/us-en/active-iq/upgrade_advisor_overview.html),
[Watchlists](https://community.netapp.com/t5/Active-IQ-and-AutoSupport-Docs-and-Resources/Active-IQ-now-has-unified-Digital-Advisor-and-Discovery-Dashboard-watchlists/ta-p/165773),
[Sustainability/StorageGRID](https://community.netapp.com/t5/Tech-ONTAP-Blogs/The-GRID-is-coming-into-view-in-Active-IQ/ba-p/165454).

**Overlap is wider than ARIA's own code comments claim credit for.** Checked each area against the actual
codebase: watchlist-scoped fleet views, upgrade planning with CLI steps, firmware currency (SP/MB/DQP/Shelf/
Drive composite), security/CVE posture (Security Posture Brief), sustainability score, VMware inventory
(`vcenters`, harvested and surfaced), and tiered multi-vendor coverage (E-Series/StorageGRID/HCI) are all
real parity, not ARIA-only. Before claiming any of these as a differentiator in a pitch or deliverable copy,
assume parity, not an edge, unless a specific depth difference is verified (see below).

**One claim corrected**: sustainability was wrongly listed as an ARIA strength in the first pass of this
analysis. Checked `computeHonestSustainabilityScore()` (`app.js` ~24528) -- it's a pass-through of Active
IQ's own `sustainabilityScorePercentage` field, not an independent carbon/power model. This is parity at
best (possibly sub-parity vs Digital Advisor's own native UI polish around the same number), not an edge.
Don't repeat this claim.

**Genuine structural edges** (verified, not assumed):
1. **Multi-tenant fusion.** Digital Advisor's watchlists span customers within *one* login's access.
   `_sync_all_accounts()` (`server.py` ~4049) harvests *separate* Active IQ accounts and
   `_merge_account_results()` (`server.py` ~1237) merges them -- not just concatenation: systems are
   deduped by serial and `tamRecommendations` cards are deduped by content (found live: overlapping accounts
   produced literal duplicate "ACTIVE_SUPPORT_CONTRACTS" cards before this fix). This is a partner/MSP shape
   Digital Advisor's single-tenant model has no equivalent for. **Built out concretely in v5.6.156/157** (see
   that addendum below): a dedicated **Portfolio Dashboard** Action Planner section (ignores the scope
   selector, rolls up every managed customer at once -- urgency-ranked accounts, fleet-wide 30/60/90-day
   trend, CVEs and refresh windows shared by 2+ customers) and **cross-customer CVE exposure** (a CVE found
   in one customer's scope shows which other managed customers are also exposed, in the Security Advisories
   tab and two deliverables) are both direct, now-shipped manifestations of this edge -- not just the
   underlying capability, but features a TAM/MSP can actually open and use.
2. **Physical rear-panel diagrams.** Digital Advisor shows telemetry, not a chassis. ARIA's rear-panel
   program (the majority of this session's earlier work) draws the actual physical layout -- real port
   roles, cabling legend, LIF-to-physical-port mapping. Nothing in Active IQ's own UI does this. Hardest to
   replicate, highest-value edge.
3. **Offline/dark-site path.** Digital Advisor is SaaS-only -- a customer that won't send AutoSupport to
   NetApp's cloud cannot use it at all. `asup_parser` (see architecture diagram, section 2) ingests raw ASUP
   bundles locally, no cloud dependency. Real structural gap in Digital Advisor that ARIA already closes, but
   currently reads as an internal fallback rather than a marketed capability.
4. **TAM-authored, branded deliverables.** Digital Advisor exports fixed-format PDF/Excel. ARIA generates 15
   narrative, editable deliverables (QBR pack, handover brief, as-built doc, CLI runbook) as structured
   `.docx`/`.md`/`.txt` in the TAM's own voice.
5. **CISA KEV-first CVE triage.** `_check_acknowledged_risks_vs_kev` cross-references NetApp's own advisory
   data against the CISA Known Exploited Vulnerabilities catalog -- "is this being actively exploited right
   now" is a different, often more actionable signal than CVSS severity alone, and unlikely to be a vendor's
   own dashboard's lead sort key.

**Concrete next work -- all four items done as of v5.6.151, see that version's addendum below for the
verified results:**
1. ~~Wire up `runIMTInteropCheck()`~~ -- **done**. `_buildDetectedSignals()` (`app.js` ~13439) added, only
   setting the two signals honestly derivable from real harvested fields (`vmware` from `vcenters`,
   `cisco_san`/`brocade_fc`/`broadcom_eth` from `switches[].vendor`). Wired into `compileCustomerReport()`'s
   Upgrade Sequence section as an "Interop Compatibility Warnings" subsection.
2. ~~Promote CISA KEV to the primary sort key~~ -- **done**. `_dfCveIndex()` now tracks KEV status per CVE;
   the CVE Remediation Priority Matrix sorts KEV-confirmed findings ahead of CVSS severity.
3. ~~Extend shelf firmware drift detection to SP/BMC and motherboard~~ -- **done**. New ACTION 2.6
   (Motherboard) and drift details added to ACTION 2.5 (SP/BMC) in `compileCustomerSuccessPlanText()`.
4. ~~Audit `_dfUpgradeWaves` against Digital Advisor's two newest upgrade rules~~ -- **done, confirmed
   parity, no code change needed** (see v5.6.151 addendum for why).


## Closed all four items from the Digital Advisor follow-up list (v5.6.151)

- **Interop compatibility warnings.** `_buildDetectedSignals(systems)` (`app.js` ~13439, right before
  `runIMTInteropCheck()`) builds the `{signalKey: true}` map the engine needs -- deliberately narrow: only
  `vmware` (from `vcenters.length > 0`, a real harvested field) and `cisco_san`/`brocade_fc`/`broadcom_eth`
  (from `switches[].vendor`, confirmed real by the earlier switch-reporting audit) are ever set. Every other
  signal in `IMT_INTEROP_MATRIX` (kubernetes, snapcenter, veeam, commvault, rubrik, cohesity, hycu, kvm_linux,
  hyperv, oracle_db, mssql, sap_hana, splunk, varonis) stays unset on purpose -- `getSystemIntegrations()`'s
  own comment documents that Active IQ's GraphQL API has no field exposing any of these, and a prior bug
  fabricated a fake vendor stack from a hash of the serial number. Since `runIMTInteropCheck()` skips an
  integration's checks entirely (including its CVE advisory) when its signal isn't set, leaving them unset is
  safe, not just conservative -- it can't produce a false positive for something Active IQ never reported.
  Wired into `compileCustomerReport()` right after the "## 10. Upgrade Sequence" table as an "Interop
  Compatibility Warnings" subsection, rendered only when a real finding exists. Verified live in demo mode:
  9 real findings across VMware/OTV, VMware vSphere (ESXi), Cisco NX-OS, and Cisco MDS for a 2,077-system
  fleet with real `vcenters` and `switches` data -- e.g. "ONTAP 9.5 is below minimum ONTAP 9.12.1 required for
  ONTAP Tools for VMware vSphere (OTV) 10.3".
- **CISA KEV as primary CVE sort key.** `_dfCveIndex()` (`app.js` ~18133) now tracks a `kev` flag per CVE ID,
  sourced from `securityBulletins[].cisaKEV`/`cisaKev`/`tags` (the same real field the existing "No CISA KEV
  Active Exploitation Alerts" health-score component already reads) and `risks[].knownExploited`. The CVE
  Remediation Priority Matrix (`app.js` ~24457) now sorts KEV-confirmed CVEs ahead of everything else,
  severity as the tiebreaker; KEV-flagged entries are labeled inline
  ("[CISA KEV -- confirmed active exploitation]"). Demo mode never populates either source field (same
  limitation the pre-existing KEV health-score component already has, not something this change introduced),
  so this can only be verified against real harvested data, not demo mode.
- **SP/BMC and motherboard firmware drift.** Same pattern as the existing `switchDrift`/`shelfDrift` in
  `compileCustomerSuccessPlanText()` (`app.js` ~22562): `spDrift` reads `sys.systemFirmware` (array or object,
  `currentVersion`/`recommendedVersion`), `mbDrift` reads `sys.motherboardFirmware` (object, same shape). Risk
  Posture Summary gained matching drift-count lines; ACTION 2.5 (SP/BMC, already existed as generic CLI
  commands with no per-system list) now shows real drift; new ACTION 2.6 (Motherboard) added, since no action
  item existed for it at all before. Verified live in demo mode: 29 systems with SP/BMC drift, motherboard
  drift lines rendering real current/target version pairs (e.g. "netapp-aff-01: current=18.9, target=18.17").
- **Upgrade-rule audit result.** Read `calculateUpgradePath()` (`app.js` ~13144) and `_dfUpgradeWaves()`
  (`app.js` ~25272) end to end rather than testing behaviorally. `calculateUpgradePath()` strips the
  `P`-number before comparing `currentBase`/`targetBase` (`cleanCurrent.split("P")[0]`), so two versions that
  only differ by patch level are treated as needing zero hops -- mixed patch levels across a cluster's nodes
  can never trigger spurious multi-hop blocking. `_dfUpgradeWaves()` has no code path that treats a cluster
  with multiple distinct `ontapVersion` values among its nodes as an error condition -- it collects them into
  a `Set`, lists them in the "Running" column, and proceeds to recommend one common target regardless. Both
  match Digital Advisor's stated behavior (don't block on mixed patch levels within a major release) without
  any change needed. No equivalent of Digital Advisor's explicit "9-month EOL grace period" rule was found or
  added -- ARIA already treats past-end-of-limited-support as an urgency signal (`_unsupported()`'s
  `pastLimited` check) rather than a hard block, which has the same practical effect, but this wasn't verified
  against a specific 9-month boundary since Active IQ doesn't expose one to check against.


## Full deliverable-suite expansion, all 15 deliverables reviewed (v5.6.152)

Asked to review every deliverable (A-O) and expand differentiation across the whole suite, then build
everything found. Two more dormant/underused backend capabilities found and closed, on top of the four from
v5.6.151.

- **`/api/history/trend` was a second complete dead engine.** `_get_fleet_trend()` (`server.py` ~1057)
  aggregates `system_snapshots` (already captured on every harvest, one dated row per system per day) into a
  daily critical/high-risk and open-critical-case series, fleet-wide or per customer -- with zero call sites
  anywhere in `app.js`. Added `_dfTrendData()` (`app.js` ~18155, right before `_dfCveIndex()`): client-side
  cached (`_trendCache`/`_trendInFlight` Maps), fetched on first use per scope, returns `undefined` (not yet
  loaded, render nothing) rather than blocking or fabricating -- the section simply appears on the next
  re-render once cached, the same degrade-honestly pattern used for `state.imt_interop`.
  **Two corrections, same day, after the first version shipped**: (1) user asked "how does ARIA know when I
  had my last meeting with a customer?" -- the original heading ("Since Last Sync"/"Since Last Check-In"/
  "Since Last Review") implied ARIA tracks actual TAM-customer engagements. It doesn't -- there is no
  calendar, CRM, or meeting-log integration anywhere in this tool, only harvest-sync history. (2) User then
  asked to replace the single ambiguous window with explicit 30/60/90-day deltas. Rather than just rename
  the heading, replaced the whole design: `_dfTrendWindows(customerName)` fetches the widest (90-day) series
  once, then computes 30/60/90-day critical/high/open-case deltas from within that same series by finding
  the earliest entry on/after each window's cutoff date -- no extra fetches. Each window is flagged `partial:
  true` when the actual tracked history is shorter than the window asks for (e.g. only 12 days of snapshots
  exist for a "60 day" window), so a short-history fleet gets an honest delta over the real span instead of a
  number implying a full window it doesn't have. `_dfTrendText()` renders all three windows as one table,
  each row explicitly labeled by calendar days ("30 days" / "60 days *" / "90 days *"), with a footnote when
  any window is partial. Verified live: synthetic 4-point series correctly produced 30-day (exact match, not
  partial), 60-day (partial, real span ~44 days), and 90-day (partial, real span ~89 days) deltas.
  Wired into `compileExtendedDeliverables()` (variable renamed `_riskTrendText`, was `_sinceLastSyncText`):
  appends to QBR Pack, Risk & Remediation Brief, Security Brief, and Customer Advisory emails, and a
  differently-headed customer-safe version ("Fleet Health, Risk Trend (30/60/90 Days)" / "Progress, Risk
  Trend (30/60/90 Days)") to the Customer Health & Lifecycle Report and Customer Value Report -- deliberately
  NOT the raw IMT/interop technical detail added below, since those two are explicitly customer-facing/
  sanitized documents. Same fix applied to `README.md`'s Digital Advisor comparison table (row was titled
  "What changed since I last engaged this customer" -- renamed to "Historical risk/case trend", now describes
  the 30/60/90-day design with an explicit "not a meeting or CRM log" note).
- **Separately, same day**: user asked whether ARIA works while their own machine is offline (distinct from
  the dark-site/ASUP-import capability, which is about the *customer's* storage system not phoning home to
  NetApp). Answer, confirmed against the architecture: yes, once at least one sync has completed. `server.py`
  runs entirely locally (SQLite + local JSON reference files); the dashboard, all 21 Action Planner sections,
  and every deliverable (including the new trend/VMware/portfolio features) are pure local computation over
  already-harvested `state.systems` with no network calls except to `server.py`'s own `localhost` endpoints.
  Only two things need connectivity: pulling *fresh* data from Active IQ, and the enrichment engine
  discovering *new* KB articles it hasn't cached yet. Not yet added to the README as an explicit FAQ --
  offered, not requested this session.
- **The IMT interop pipeline was already built for 9+ deliverables -- just never fed anything but vSphere.**
  Found, while wiring in the trend section, that `compileExtendedDeliverables()` already had a precise,
  deliberately-scoped `imtFindings` array (`app.js` ~25877) matching vCenter's *actual reported version*
  against `_getImtInterop().vmware_vsphere`'s version-keyed compat table -- built after a documented prior
  bug where a cruder substring-search fabricated Proxmox/Hyper-V/Cisco/Brocade estates a customer might not
  have. That array already fed `problemStatements`, `customerComms`, `solutionProposals`,
  `implementationPlans`, `changeTickets`, `salesProposals`, `customerSuccessPlan`, `qbrPack`, `mspReport`,
  `handoverBrief`, `riskRemediationBrief`, `securityBrief`, `sustainabilityReport`, and a UI badge on the
  Deliverables tab -- but nothing populated it beyond vSphere, since `runIMTInteropCheck()` (wired up in
  v5.6.151) was a completely separate, parallel implementation nobody had connected to it. One line
  (`imtFindings.push(...runIMTInteropCheck(...).filter(f => f.integrationKey !== 'vmware_vsphere'))`) merges
  the two: keeps the precise version-matched vSphere check as-is (strictly better where Active IQ reports an
  actual version), adds the broader-but-still-honest OTV/Cisco/Brocade/Broadcom findings for everything else.
  Retroactively enriched every deliverable in that list with switch/OTV coverage in one change. Verified
  live: a real fleet slice produced 9 findings spanning `vmware_otv`, `cisco_nxos`, `cisco_mds`,
  `broadcom_efos`, and `host_utilities_esxi`, all flowing correctly into `qbrPack` and the rest.
- **Multi-account portfolio analytics, the genuine structural edge.** Two new functions (`app.js`, right
  after `_dfRefreshPlan()`) read `state.systems` directly (the full, already-deduped multi-account fleet)
  rather than the scope-filtered `targetSystems` a deliverable is generated for -- a comparison a
  single-tenant dashboard structurally cannot produce. Both gate on having enough of a wider portfolio to
  compare against and return `null`/`[]` otherwise, never fabricating a benchmark from a handful of unrelated
  systems: `_dfPortfolioBenchmark()` (needs >=20 other systems) computes ASUP/ARP/contract-coverage rates
  across every OTHER customer in the fleet, now a "Portfolio Benchmark" section in the MSP Service Delivery
  Report right after its existing SLA Compliance Matrix. `_dfPortfolioEosOverlap()` finds hardware models
  approaching EOS in this scope that are ALSO approaching EOS for other managed customers in the same window,
  now a "Portfolio Refresh Overlap" section in Sales Refresh & Renewal Proposals. Verified live against the
  real fleet: MSP Report showed "vs. 13 other managed customers [138 systems]" with real ASUP/ARP/contract
  percentages; Sales Proposals found a genuine 5-customer AFF-A300 EOS overlap.
- **Deliverable roster confirmed complete** (A-O plus the As-Built Configuration Document, cross-checked
  against the actual Action Planner UI labels, not assumed): A Executive Risk Assessment, B ITIL Change
  Control Tickets, C CLI Runbooks & Upgrade Plans, D Customer Advisory & QBR Comms, E Technical Solution
  Proposals, F Sales Refresh & Renewal Proposals, G Risk & Remediation Brief, H Security Posture Brief, I
  Sustainability & ESG Report, J TAM Success & Posture Plan, K TAM QBR Pack, L MSP Service Delivery Report, M
  Account Handover Brief, N Customer Value Report, O Customer Health & Lifecycle Report. As-Built Document
  untouched this pass -- already ARIA's strongest edge (rear-panel diagrams), no gap found there. Sustainability
  (I) deliberately left alone -- still a pass-through of Active IQ's own score, not something to fake a
  differentiator on top of.

## Portfolio Dashboard, cross-customer CVE exposure, and a run of real-world bugfixes (v5.6.153 - v5.6.162)

Continues directly from the addendum above. Full detail in `git log`/`CHANGELOG.md` for this range; summarized
here so the differentiator claims and the deliverable/section inventory above stay accurate without re-deriving.

**Two more differentiators actually shipped, both leaning on the multi-tenant fusion edge (see edge #1 above,
now updated to point here):**
- **Portfolio Dashboard** (`computePortfolioExecutiveDashboard()`/`_renderPortfolioExecutiveDashboard()`,
  `app.js`, new Action Planner section, Overview group). Reads `state.systems` directly and ignores the scope
  selector -- the point is seeing every managed customer at once, which a single-tenant view structurally
  cannot do. KPI tiles, fleet-wide 30/60/90-day risk trend (`_dfTrendWindows(null)` -- `_get_fleet_trend()`
  server-side already treats a null customer as fleet-wide), an urgency-ranked "Accounts Needing Attention"
  table, a "Shared CVE Exposure" table (CVEs hitting 2+ customers), a "Shared Refresh Opportunities" table
  (hardware models nearing EOS for 2+ customers). Gated on >=2 customers in the fleet. Verified live against
  a real 78-customer, 2,898-system fleet: 385 critical risks, 109 systems within a year of EOS, a real CVE
  affecting 74 of 78 customers, FAS8200 shared by 16 customers.
- **Cross-customer CVE exposure** (`_dfCveIndex()` extended with a `customers` Set per CVE;
  `_dfPortfolioCveExposure()`/`_dfPortfolioCveExposureText()`). Unlike the portfolio benchmark above, needs no
  minimum-size gate -- even one other exposed customer is directly actionable. New "Portfolio Exposure" table
  in the Security Advisories Action Planner section, plus text in the Security Posture Brief and MSP Report.

**As-Built Excel export -- shipped, then two real corruption bugs, then two real data bugs, all found by the
user actually opening the file, not by any verification I ran beforehand.** `_buildXlsx()`/`_xlsxSheetXml()`/
`_colLetter()` (`app.js`, next to `_buildDocx()`): a from-scratch minimal XLSX writer (no library), same
hand-rolled-OOXML-in-a-zip approach as the existing docx writer. Not a differentiator (Digital Advisor's own
Upgrade Advisor already exports Excel) -- closes a parity gap, scoped to the As-Built document only since
it's the one deliverable whose data is genuinely tabular.
- Bug 1 (repair prompt): `xl/_rels/workbook.xml.rels` never declared a relationship to `styles.xml`.
- Bug 2 (invisible headers): white header text sitting on a fill using a non-standard index layout that
  didn't render -- fixed by conforming to the standard fills convention (0=none/1=gray125/2=custom) and
  dropping the white color override entirely so visibility never depends on the fill rendering.
- Bug 3/4 (blank data): risk titles read `r.title` (real field: `r.description`); contract dates read
  `sys.contracts.hwEndDate`/`swEndDate`, which never existed (the real `contracts` object only has one
  unified `endDate` plus a real `supportLevel` never surfaced before); firmware read `sys.firmware.*`, also
  nonexistent (real fields: `sys.systemFirmware`/`motherboardFirmware`/`_resolveShelfModules()`). All four
  were copied from the pre-existing As-Built TXT generator, which had carried the same bugs, undetected, for
  an unknown number of prior sessions -- it was write-only (generated and downloaded, never read cell-by-cell
  until the Excel export made the same fields visible in a grid).
  **Lesson recorded in `CLAUDE.md`, worth repeating here**: after the repair-prompt bug, verification switched
  to reproducing the exact file structure in Python and loading it with `openpyxl` (installed via pip, not
  present by default in this dev environment) before calling anything "verified" -- a well-formed zip/XML is
  necessary but nowhere near sufficient for Excel to accept it without complaint.

**TAM Success & Posture Optimization Plan made genuinely executable (v5.6.162).** Asked to make it a real
plan committable/executed against (the kind uploaded into Digital Advisor's own Success Plans), not a
document requiring re-derivation. Three fixes in `compileCustomerSuccessPlanText()`: removed a "+N more"
truncation on risk-group system lists (every affected system now named in full); ACTION 3.2 (Capacity) now
names the actual systems approaching their threshold (reusing `computeFleetCapacityForecast()`'s real
per-system `atRisk` data) instead of a generic templated command; ACTION 4.3 (ARP) now names the actual
systems with ARP confirmed disabled instead of only a percentage. **Real, checked limit**: the request's own
example asked for actual volume names -- Active IQ's GraphQL schema this tool queries never returns
individual volume objects, only per-system/per-cluster counts, so no per-volume identifier exists anywhere in
the harvest. System name is the deepest real identifier available; nothing was fabricated to go deeper.
Separately confirmed live that the *other*, pre-existing "Success Plans" feature (`SUCCESS_PLAN_TEMPLATES`,
the one with real Active IQ write-back via Adopt) already names every affected system individually from an
earlier session's fix -- not the same bug, did not need the same fix.

**Also this range**: sortable Capacity Breakdown by Node table + Customer column (CSM tab) -- shipped once
against `index.html` (the compiled artifact the packaged exe bundles, never what `server.py` serves at `/` in
dev mode) and reported as still broken, fixed for real in `index_src.html`; then the four new Portfolio
Dashboard/Portfolio Exposure tables sorted their own header row into the results because they lacked the
`<thead>`/`<tbody>` split every other sortable table already has, also caught from a screenshot. The
Deliverables Suite (was one "Deliverables Suite (13)" tab, actually 15 documents) split into three tabs along
its own pre-existing internal category dividers -- Risk & Remediation (A-C), Customer & Sales (D-I), TAM/MSP
(J-O) -- each with its own scoped Download All; found and fixed `downloadAllDeliverables()` silently missing
2 of the 15 real deliverables in the process.
**Recurring lesson across this whole range, worth internalizing rather than re-learning per bug**: verify UI
wiring with a real DOM event (`.click()`), never a direct function call -- a direct call proves the logic
works, not that the page actually wires it up, and cannot catch a missing `<thead>` either.


## StorageGRID, Platform Insights, Word exports and restricted-account scoping (v5.6.203 - v5.6.221)

Summary of this range; full detail in `CHANGELOG.md`. Written so a new session can pick up without re-deriving. Items 9-11 in section 2 cover the same ground in shorter form; this addendum is the authoritative, more recent version.

**StorageGRID awareness (v5.6.203-218).** Live introspection showed Active IQ exposes, per grid, `gridSites{nodes}`
(role, appliance model, RAID, drives, OS version), `tenants{buckets}` (versioning, S3 Object Lock, CloudMirror) and
`ILMDetails{rules}` (placements, storage pools, ingest behaviour, periods in days). The old "ILM not reported" claims
were wrong. Harvested into `storagegridTopology`; analysed by `_dfStorageGridView`; shown in the Technical Audit card and
the Action Planner StorageGRID tab (nodes, site capacity, ILM rules, findings, tenants/buckets, in that order); reported in
the TAM plan, QBR, Exec Risk, Handover, MSP, Risk & Remediation, Security Brief, Customer Report; findings enter the risk
engine via `applyStorageGridRisks`. Node totals come from the grid (roster / installed count), not from Active IQ system
records, because non-admin nodes often send no AutoSupport; unlisted records are flagged. Form factor: VMWARE = virtual,
STORAGE_GRID_APPLIANCE / SG-model = physical appliance, BARE_METAL. ILM rules are labelled "as reported by Active IQ"
(no active-policy flag exists). Appliance EOA notice CPC-00602 (SG100/SG1000/SG5712/SG5760/SG6060) is flagged without dates.
The node strip classifies nodes by true platform and collapses duplicates; the MetroCluster card follows the selected node.

**Platform Insights (v5.6.204-205).** Power/heat, drive inventory, upgrade history, hardware expansion limits, NVSRAM,
file currency, FC adapters, Cloud Insights, talking points. Harvest `platformExtras`; analysis `_dfPlatformInsights`;
Action Planner tab 27.

**Success Plans (v5.6.205, 209-210, 217).** The harvest query was invalid and silently loaded nothing; fixed with real
milestone/action progress. Create/update mutations fixed (`notes:[{message}]`, `results{ id type success errors }`),
verified only with bogus-NAGP/invalid-enum probes, never written live. Submitted plans always carry the full affected-system
list, split across notes if Active IQ rejects a very large field.

**Word exports (v5.6.218-221).** Every Action Planner view has Download Word (`downloadPlanSectionWord`,
`_domToMarkdown`); StorageGRID and Firmware Currency have dedicated reports; risk/advisory views use their purpose-built
export. Layout verified from generated Markdown, not by rendering Word.

**Restricted-account scoping (v5.6.208, 221) -- the most important lesson of the range.** An account without
`unfiltered_system_access` fails unscoped queries ("At least one mandatory argument is required"). Code that ignored the
error produced silent zeros/"Unknown". Fixed in the extras merges, shelf summary, risks, cases, customers, recommendations,
sites, sustainability, health score and renewals. Any new top-level query must go through the scoped fallback and be checked
against the restricted account, not only the privileged one.

**Genuine Active IQ limits (do not re-investigate):** no controller/port/WWPN on E-Series and StorageGRID; VMware nodes
have no model/drive/version/health; no per-model StorageGRID EOS dates; no ILM active-policy flag; no depot/hub logistics;
E-Series actual power is 0; no SP/BMC/BIOS/DQP for StorageGRID/E-Series.

**Pitfalls.** New harvested fields must be added to `enrichSystemTelemetry`'s explicit return; stay under the field-count
limit by using separate merged queries; client dedupe must merge not first-wins; bump the systems cache schema (v16) when
shape changes; write JS edit scripts with the Write tool, not heredocs (escape mangling); judge exports visually, not by word counts.

**Cluster switches (v5.6.231).** The `ClusterNetworkSwitch` type is small (see PLATFORM_COVERAGE.md). Active IQ reports a switch per cluster, so raw data repeats a shared switch per node; `_dfSwitchInventory` de-duplicates by serial (else normalised name). Only CSHM-monitored switches have model/firmware/RCF/contract; discovered-only switches carry a name and a firmware-description string; connectivity-only switches (from the ONTAP port side) have just a name. SNMP version is now harvested (`snmpVersion`; most switches are SNMPv2c). Do not re-investigate: no switch ports/ISL/health fields exist, and switch support-contract dates came back empty. Switches are not yet in the deliverables.

**Paging and Word leftovers (v5.6.232).** `systemContractRenewals` pages with `after` (it returns `cursor` and `totalCount`); `sites` and `customers` return a `cursor` but no total, so they page until a page is shorter than the page size. Any new list query should be checked for a cursor before assuming one page is enough. StorageGRID capacity growth is not derivable (null QoQ/YoY, empty monthly series for every grid): do not re-investigate.

**Harvest completeness audit (v5.6.232).** Rules learned the hard way: (1) never assume one page is the whole list: check for a cursor / `totalCount`; (2) a nested connection's `pageSize` default is small and sometimes honoured (LUNs: 50 -> up to 32,252 per system) and sometimes ignored (volumes): compare `totalCount` with the length read; (3) `systems`, `cases`, `systemContractRenewals` and several others default to `productTypes: [FILER, SWApp]`: pass all six (FILER, SWApp, NON_FILER, UNKNOWN, SWITCH, AIDE_DCN) to see everything; the non-controller records go to `otherProductSystems`; (4) no slices (`[:N]`) on harvested lists. A 100,000-item nested page is fast; many small follow-up passes are not (a first attempt with 1,000-item pages took 45 minutes instead of 12).

**Concurrency and duplicates (v5.6.233).** The SQLite cache is shared by every process that runs from this folder (a dev server, the packaged exe, a second window): a harvest save holds the write lock for a while, so writers must wait (`busy_timeout`) and the save must build its rows before locking. Two configured accounts can both see a system; the server keeps one copy per account (keyed by account + serial), so list fields such as renewals, sites and other-record systems must be de-duplicated when loaded (`_dedupeBy`). After committing, verify the staged file list (`git diff --cached --stat`) and `git status`: the v5.6.232 commit once left out `version.json` and every doc.

**LUN / volume units and thin provisioning (v5.6.234).** Two different unit conventions in one query: `luns.capacity.usableKiB` is actually BYTES (the harvest divides it by 1,024 to store KiB: round values such as 4.000 TB and 32.000 TB confirm it), but `storageVolumes.volumes.capacity.sizeKB`/`availableKB` and `logical.usedSnapshotsKiB` are already KiB (an earlier version divided them by 1,024 as well, making volume sizes 1,024x too small; the test that exposed it is `logicalUsedTB / volume size` per system: median 458 before the fix, 0.45 after). Cached data from before the fix is corrected on read by `_lvVolumeKiB` (marker `volumeSizeUnitsFixed`). Presentation rules: provisioned size is never used capacity, LUN and volume sizes overlap, 'volumes' not 'NAS volumes', overcommit is a finding only with 80%+ physical use. When a figure looks implausible, compare it against an independent one (logical used, physical used, usable) before trusting an earlier unit conclusion.
