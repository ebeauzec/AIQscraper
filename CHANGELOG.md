# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.8.0] - 2026-07-07

### Added
*   **Role-Aligned Sub-Tabs Redesign**: Redesigned Technical Audit (TAM), Support & Ops (SAM), and CSM Value & ROI (CSM) tab structures with role-aligned, task-based sub-tab navigations to segment dashboard components into logical, readable, and structured sub-panes.
*   **Context-Aware L1 Visualizers**: Enabled Cloud Volumes ONTAP (AWS/Azure/GCP) virtual network interface subnet maps and StorageGRID network band routing visual layouts, replacing physical cabling chassis representations.
*   **Platform Model Name Mapping**: Implemented precise model resolutions to display exact models (e.g. `AFF A400`, `StorageGRID SG6060`, `CVO (Azure)`, `EF600`) across L1 visuals.
*   **Loop Type Safety checks**: Integrated strict checks for custom system configuration JSON objects lacking optional keys like `risks` and `fieldActions` to prevent runtime exceptions.

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
