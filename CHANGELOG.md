# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.1.0] - 2026-07-10

### Added — NetApp Reference Library Enrichment Engine
- **EOA Platform Flagging** — Automatic detection of systems running End-of-Availability hardware. Complete EOA list from docs.netapp.com (AFF A200/A220/A300/A320/A700/A700s/C190/C800, ASA C250/C400/C800, FAS2600/FAS500f/FAS8200/FAS9000) plus EOA switches (BES-53248, Cisco 9336C-FX2, NVIDIA SN2100)
- **CVE/Security Advisory Database** — 7 tracked CVEs with version-range matching (CVE-2026-22050 ONTAP snapshot lock bypass, CVE-2026-22052 S3 NAS info disclosure, CVE-2026-20833 Kerberos AES enforcement, CVE-2026-22054 Config Advisor hard-coded creds, CVE-2025-26512 SnapCenter privilege escalation CVSS 9.9, CVE-2026-22051 StorageGRID metrics disclosure, CVE-2026-24051 Trident PATH hijacking)
- **ONTAP Version Highlights Database** — Per-version feature summaries (9.10.1 through 9.19.1) for upgrade justification in deliverables
- **MetroCluster ISL Requirements Database** — Distance limits (300 km FC Brocade, 700 km IP), packet loss/jitter thresholds, MTU 9216, feature-version matrix (9.9.1→9.18.1)
- **Firmware Baselines Database** — Recommended minimums for NSM100 (0220), IOM12 (0260), Cisco NX-OS (9.3(12)), Brocade FOS (9.2.1), Broadcom EFOS (3.8.0.2)
- **SnapCenter Version Chain** — Added SnapCenter to SOFTWARE_VERSION_DATABASES (4.5→6.2.1)
- **StorageGRID 12.1.0** — Added to version database

### Fixed — Support Cases (Critical)
- **Tab 4 support cases wiped to zero** — `filterActiveCases()` returns the same array reference, so `allSupportCases.length = 0` was destroying data before re-push. Fixed in all 3 call sites by calling `filterActiveCases()` as an in-place sort without the destructive length-reset pattern
- **GraphQL cases query returning HTTP 400** — Fixed enum syntax (`"FILER"` → `FILER`) and field names (`caseTitle` → `symptom`, `caseStatus` → `status`, etc.) in server.py
- **`isActiveCase: true` filter hiding all cases** — Removed restrictive filter; now fetches ALL cases and tags active/closed on the client side
- **Cases showing in overview but not in Action Planner** — Same root cause as the `filterActiveCases` wipe bug above

### Changed
- **Support Cases UI (Tab 4)** — Redesigned with summary bar (Active/Processing/Closed/Total counters), color-coded left borders (cyan=active, orange=processing, dim=closed), human-readable status labels (e.g. `WAIT_TSE` → "Open — Awaiting TSE")
- **KPI Card** — Support cases KPI now shows `active / total` (e.g. `3 / 28`)
- **Schema bumped to v13** — Forces cache regeneration with corrected cases data
- **Comments updated** — All `filterActiveCases` call sites updated to reflect in-place sort behavior

## [3.0.0] - 2026-07-10

### Added — TAM Account Intelligence Suite (Tabs 10–15)
- **Tab 10: Contracts & Lifecycle** — Contract status summary cards (Active/Expiring/Expired), lifecycle event table (EOA/EOS milestones sorted by urgency), and contract renewal pipeline filtered per-customer with tech refresh status and service tier breakdown
- **Tab 11: Sustainability & ESG** — Fleet-wide sustainability score with week-over-week trend, historical weekly score table, improvement factors, per-system carbon emissions (monthly), and per-customer average data reduction ratio (dedup + compression)
- **Tab 12: Recommendations** — Active IQ key recommendations grouped by category (VERSION, AUTO_SUPPORT, BEST_PRACTICES, CONFIG, SUPPORT_AND_ENTITLEMENTS) with rank scores and sub-categories
- **Tab 13: Account Intelligence** — Account personnel table (Sales Rep, CSM, SAM, ASP, Propensity per system), site inventory filtered per-customer, customer/site/system summary cards
- **Tab 14: Contract Compliance** — Contract and warranty status cards, service tier distribution, contract renewal pipeline with HW/SW service levels, EOA/EOS dates
- **Tab 15: Operational Health** — AutoSupport (ASUP) health verification (7-day recency check), Anti-Ransomware Protection (ARP) enablement audit, firmware currency analysis, last reboot timeline

### Added — UI Enhancements
- **Tooltips on all summary cards** — Hover tooltips with detailed explanations on every KPI card across the main dashboard, Executive Summary, and all TAM tabs (10–15)
- **Card subtitles** — Descriptive subtitle text below every numeric card for at-a-glance understanding
- **Fleet-wide disclaimer** on Sustainability tab clarifying that scores are fleet-wide, not per-customer

### Added — Data Pipeline
- **TAM GraphQL endpoints** — Sites, Sustainability Scores, OS Version Catalog, Renewals, and Recommendations harvested via `server.py`
- **Enrichment passthrough** for `siteName`, `siteId`, `siteCity`, `siteCountry`, `salesRepName`, `csmName`, `samName`, `aspName`, `propensityCategory`, `contractActive`, `warrantyEndDate`, `serviceTier`, `latestAsupDate`, `isARPEnabled`, and 20+ additional TAM fields
- **DOM injection rendering** for Tabs 13–15 using `createElement`/`appendChild` to bypass HTML template nesting issues

### Changed
- **Per-customer scoping** — Tabs 10, 13, and 14 now filter TAM data (sites, renewals, personnel) to the selected customer instead of showing fleet-wide data
- **Account Personnel promoted** to top of Tab 13 output (above Sites table)
- **Version unified** to 3.0.0 across README, CHANGELOG, HTML sidebar, and installer

### Fixed
- Tabs 13–15 rendering blank due to unclosed HTML tags in template string injection — resolved via DOM element injection
- Sites table showing all 50 fleet sites regardless of selected customer — now filtered by system siteName/siteId
- Renewals pipeline showing entire fleet in Tabs 10 and 14 — now filtered by hostname/serial

## [2.0.0] - 2026-07-10

### Added
*   **SQLite Persistent Database (`aiq_cache.db`)**: Replaced volatile browser-only localStorage with a server-side SQLite database. All system telemetry, enrichment data, risks, and metadata persist across browser sessions and machines. The browser localStorage is still used as a fast client-side cache, but the authoritative store is now the database.
*   **Python Server Backend (`server.py`)**: Full reverse-proxy and API gateway server that handles OAuth token exchange, GraphQL API harvesting, SQLite persistence, and serves the dashboard. Eliminates the need for CORS browser extensions.
*   **GraphQL API Integration**: Migrated from REST-only polling to NetApp's GraphQL API for richer data harvesting including cluster-level capacity, SnapMirror relationship counts, HA configuration status, and security advisory details.
*   **SnapMirror Relationship Mapping**: Server now maps `snapMirrorRelationships.totalCount` and `isHAConfigured` from each cluster to every system. Frontend `_buildSnapMirrorData()` function constructs meaningful relationship entries (async/sync split) for the UI.
*   **Fix-Grouped Deliverables (`_filterAndDeduplicateRisks`)**: All deliverable templates (Problem Statements, Advisory Email, QBR Summary, Solution Proposal, CLI Runbook) now group findings by their corrective fix (e.g. "Upgrade to ONTAP 9.16.1"). A single fix that addresses 8 CVEs shows as one prioritised action with all resolved findings listed beneath it.
*   **Chronological Capacity Charts**: Chart X-axis labels now show real calendar months (e.g. "Jan 2026", "Feb 2026") instead of generic "Month -6" labels.
*   **Actionable Remediation Text**: Security advisory recommendations now include specific upgrade version targets (e.g. "Upgrade to ONTAP 9.16.1") instead of generic "See Security Advisory" text.
*   **Alphabetical Customer Account Sorting**: Sidebar customer account groups are now sorted A-Z.

### Changed
*   **Deliverable Brevity**: All generated reports now filter to **Critical and High severity only**, excluding medium/low and best-practice category items. Duplicate advisories resolved by the same OS upgrade are consolidated into a single entry.
*   **Deliverable Format Overhaul**: All 5 text templates completely rewritten for executive presentation: concise headers, clean alignment, fix-first structure, no redundant boilerplate.

### Fixed
*   **`ReferenceError: recommendedOSVersion`**: Fixed scope issue in enrichment stage where the recommended OS version variable was not accessible in the remediation text builder.
*   **Stale `secRisks.length` references**: Replaced broken references to a now-renamed variable throughout the deliverables function.

## [1.11.0] - 2026-07-09

### Fixed
*   **KB Links — Permanent Fix (`buildKBSearchURL`)**: Removed the broken `validateAndSanitizeKBLink()` sanitizer (which tried to guess internal NetApp portal redirect paths) and replaced it with a `buildKBSearchURL(description, category)` function. Instead of deep-linking to a specific KB article URL that may 404 due to NetApp's internal redirect system, the tool now opens a live KB search pre-populated with the risk description and category keywords. This always works, never 404s, and actually returns more relevant results. Works for any condition — including new ones discovered via the AIQ API that have never been seen before.

### Improved
*   **Universal System Normalization (`enrichSystemTelemetry`)**: Overhauled the enrichment function to be a true ingestion gateway called on every system from every source (API, import, localStorage, mock). Key changes:
    *   Accepts both camelCase and snake_case API field names (`serialNumber`/`serial_number`, `ontapVersion`/`ontap_version`, etc.)
    *   Normalizes risk `severity` to lowercase regardless of how the API delivers it (`HIGH` → `high`)
    *   Strips any incoming `kbLink` fields from risks — search URLs are generated at render time, not stored
    *   Normalizes `securityBulletins` and `supportCases` from API field name variants (`cveId`, `bulletinId`, `caseNumber`, `subject`, etc.)
    *   Detects CVO systems by name pattern in addition to model string
    *   Adds `switches: []` as a guaranteed field in the returned object to prevent renderer crashes
    *   Handles unknown/future platform models gracefully (treated as AFF-equivalent ONTAP)
*   **localStorage Enrichment on Load (Schema v9)**: Systems loaded from localStorage are now re-run through `enrichSystemTelemetry()` on every startup. This ensures any system stored from a previous API pull that was missing fields (e.g. `switches`, `autosupport`, `salesHealth`) automatically gets those fields populated without wiping user-edited data.

## [1.10.0] - 2026-07-09

### Added
*   **ITIL Safety Tiers (`OPERATING-PROTOCOL.md`)**: Automatically classifies all technical risk resolutions and CLI implementation commands into safety levels (*Non-Disruptive*, *Disruptive but Data-Safe*, and *Destructive or Irreversible*). Displayed dynamically inside the technical risk cards, details modals, and ITIL Change Tickets.
*   **Dynamic Telemetry Profiler (`enrichSystemTelemetry`)**: Configured a dynamic parsing wrapper that detects hardware platform families (AFF, ASA, FAS, StorageGRID, E-Series) and dynamically computes validated firmware upgrade targets, support contract lifecycles, and storage efficiency metrics.
*   **CLI Command & Compliance Corrections**: Fixed `vserver audit create` mandatory parameters (`-format json`) and added the `vserver audit enable` command. Integrated native ONTAP volume snapshot disablement command (`volume modify -snapshot-policy none`) for volumes managed by Veeam, Commvault, or Rubrik to prevent schedule collisions.

## [1.9.0] - 2026-07-09

### Added
*   **Next-Gen Hardware & Software Platform Support**: Added native support for **AFF A1K** (flagship), **AFF A90**, **AFF A70**, **AFF C80** (capacity flash), **ASA A90**, **ASA A30** (all-flash SAN), **StorageGRID SG6160** object appliance, and **EF600 (E-Series NVMe)**.
*   **FAS/AFF vs. ASA Platform Differentiation**: Fully integrated ASA block SAN array features into capacity reporting widgets (Block SAN Storage Efficiency Ratios), FabricPool Cloud Tiering statuses (identifying N/A bypasses), and generated CLI Runbooks (including `esxcli storage nmp` symmetric multipathing checks and SCSI UNMAP space reclamation states).
*   **TAM Port Layout Upgrades**: Added dynamic mapping for **100 Gbps RoCE** cluster interconnects, **100 Gbps host ports**, **64 Gbps Fibre Channel SAN**, and **NS224 NVMe storage shelves** (via 100 Gbps NVMe links and NSM shelf module firmware upgrades).
*   **Self-Contained Local Code Updater**: Integrated an "Update Application" action button in the settings panel that triggers local `git pull` updates via the Python server proxy backend.
*   **Data Security, Sovereignty & AI Compliance**: Embedded dedicated disclaimers inside the Settings view and repository documentation detailing the 100% AI-free, self-contained, browser-local data sovereignty of the application.
*   **NSS Non-Technical Logistics Tickets**: Programmed a site logistics comparison visualizer tracking local session edits and auto-generating NSS non-technical support tickets with copy-pasteable change mappings.
*   **NetApp Fiscal Calendar Alignment**: Built quarter-to-fiscal date transformation logic (`convertToNetAppFiscal`) aligning all tech refresh windows with NetApp's fiscal cycle (May-April).

## [1.8.0] - 2026-07-07

### Added
*   **Active IQ API Polling & Sync Configs**: Built custom API gateway base URL inputs and auto-polling sync intervals (6h, 12h, 24h, 7d) in the Settings view.
*   **Watchlist-Only Sync Filter**: Added an option to filter and synchronize only systems belonging to active Active IQ Watchlists.
*   **Dynamic Synchronization Metrics**: Added a local sync dashboard tracking Last Poll Time, Next Scheduled Poll, and sync status with manual trigger options.
*   **Automated Background Sync Timer**: Programmed an asynchronous background sync checking interval to maintain telemetry freshness without blocking browser operation.
*   **Fixed Upgrade Path Down-grades**: Resolved target version generator anomalies to ensure target baselines are always higher than current baselines, and corrected `calculateUpgradePath` to return empty hops for up-to-date systems.
*   **Valid Support Article Links**: Replaced `/onprem/...` paths on `kb.netapp.com` (which returned 404s and triggered support portal redirects) with correct, working `/Advice_and_Troubleshooting/...` native URL routes.

## [1.7.0] - 2026-07-07

### Added
*   **Phased Customer Success & Posture Optimization (CSP)**: Integrated standard NetApp TAM/SAM/CSM and ITIL Change Control guidelines into a consolidated Success Plan deliverables module.
*   **Review-Ready Print Overrides**: Refactored `printActionPlan()` to output complete 9-section consolidated reports in a continuous flow, hiding navigation sidebars, and converting HTML textareas into static pre-wrapped text divs for clean PDF exports.
*   **Node-Level L1 Port Visualization**: Resolved L1 cabling maps to individual controllers with active slot indicators (Slot A - Top, Slot B - Bottom).
*   **E-Series & SANtricity Support**: Fully integrated support for block-level EF600 and E5700 hybrid systems. Added custom hardware audits tracking BBUs, DDP volume pools, and drive life grids.
*   **SVM & Protocol Audits**: Track Storage Virtual Machine (SVM) configurations, flagging SMBv1 ransomware vectors and insecure NFS exports with copy-paste CLI remediations.
*   **Reordered Watchlist Layout**: Moved watchlists above customer accounts in the sidebar.

## [1.6.0] - 2026-07-06

### Added
*   **Starred & Dynamic Filters**: Added ability to save/star current search queries. Starred queries are persisted to local storage and dynamically evaluated as custom filters in the sidebar.
*   **Multi-Query Search**: Support searching by multiple comma-separated systems, customers, clusters, or serial numbers.
*   **Action Plan Deliverables**: Added Section 8 (Executable Account Deliverables) to compiled plans, generating draft customer emails, os/refresh proposals, and internal operations dispatch tickets.
*   **Version Increments**: Fixed sidebar footer version displays to match version 1.6.0.

## [1.5.0] - 2026-07-06

### Added
*   **Active Technical Support Cases**: Added open support cases table to the Support & Ops tab, capturing Case ID, Subject Title, Severity levels, workflow Statuses, Created/Updated dates, and TAM action updates.
*   **Support Cases Planner Integration**: Injected support case list into compiled Action Plans (Section 4) with status tags and milestones.
*   **Support Cases Metadata Editor**: Added support cases JSON array editor under the Settings & Config tab to modify or add active support tickets.

## [1.4.0] - 2026-07-06

### Added
*   **Site Logistics & Site Contacts**: Added delivery site addresses, gate access restrictions, courier transit alert banners, and primary site contacts (names, emails, phones, NSS IDs) to the Support & Ops tab.
*   **Sales Health Scorecards**: Added account sentiment scores (CSAT), sales AM/TAM representative tracks, target hardware refresh windows, and CSM upsell pipelines.
*   **Projections Line Charts**: Added historical and projected storage capacity growth line graphs and performance peak IOPS metrics to the CSM Value & ROI tab.
*   **Security & Technical Bulletins**: Added NetApp Security Advisories (NTAP-SA) tables mapping CVE vulnerabilities and mitigation guides to the Technical Audit tab.
*   **Custom Metadata & Bulletins Editors**: Added edit input forms and JSON textareas in the Settings tab to modify logistics, site contacts, CSAT sentiments, daily growth rates, and security advisories for each system.
*   **Sidebar Navigation Renaming**: Renamed "TAM Technical Audit" to "Technical Audit" and "SAM Support & Ops" to "Support & Ops" for concise terminology.

## [1.3.0] - 2026-07-06

### Added
*   **Collapsible Sidebar Filter Tree**: Added a dynamic Account Filters navigation panel in the sidebar, displaying Customer Accounts and Custom Subgroups.
*   **Subgroup Creator Form**: Added a subgroup management UI in the Settings tab to name new groups, check systems to assign to the group, and commit to `localStorage`.
*   **Subgroup Deletion Manager**: Added list panel to delete custom subgroups instantly.
*   **Global Filter States**: Intercepted system data pipelines to restrict dashboard KPIs, tables, and charts automatically when a sidebar group node is selected.

## [1.2.0] - 2026-07-06

### Added
*   **Account Action Planner**: Added a dedicated Action Planner module to compile detailed operational plans for individual systems, all systems under a specific customer, or the entire monitored portfolio.
*   **Executive Plan Exporter (Print/PDF)**: Added clean print configurations and a print trigger to export compiled action plans as distribution-ready documents or PDFs.
*   **JSON Import & Export**: Added buttons on the Overview and Settings tabs to export report configurations as local JSON files, or import external files to load dashboards dynamically.
*   **Documentation updates**: Added guidelines for Change Management, firmware upgrades, and virtualization host multipathing best practices.

## [1.1.0] - 2026-07-06

### Added
*   **Detailed Remediation Plans**: Added interactive modal action plans for every active risk, displaying detailed cause, impact, step-by-step resolution commands, and options/trade-offs.
*   **Expanded Platform Telemetry**: Added mock configurations representing Cloud Volumes ONTAP (CVO), StorageGRID, and MetroCluster IP nodes.
*   **SnapMirror Monitoring**: Added SnapMirror relationship card showing replication status, states, and lag times.
*   **3rd-Party Integrations**: Added hypervisor compliance tracking, checking VMware ESXi NMP Round Robin multipathing configurations and Astra Trident version updates.
*   **UI Enhancements**: Added active system selection dropdowns within TAM, SAM, and CSM tabs.

## [1.0.0] - 2026-07-06

### Added
*   **Unified Account Overview**: Renders a landing dashboard with core system counts, critical risk counters, warning notifications, and expiring contract lists.
*   **TAM Module (Technical Compliance)**: Lists active system risks, recommended resolutions, official NetApp KB references, and ONTAP target release advisors.
*   **SAM Module (Support Operations)**: Highlights warranty contract end dates, system hardware End-of-Support (EOS) lifecycles, and active Field Actions (FA).
*   **CSM Module (ROI & Adoption)**: Tracks capacity efficiency ratios, FabricPool cloud tiered capacity metrics, and a feature checklist.
*   **Interactive Analytics**: Integrated Chart.js to render storage savings and FabricPool cloud capacity charts.
*   **LocalStorage Cache**: Manages credentials, tokens, and demo modes client-side without a database.
*   **CSV Exporter**: Allows one-click downloads of account status reports.
*   **Indemnity & License**: Added MIT License with NetApp-specific operational disclaimer.
