# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
