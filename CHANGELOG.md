# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [4.4.1] - 2026-08-10

### Fixed
- **Risk & Advisory Register severity counts** — `normRisk()` lowercases severity (`"high"`, `"medium"`) but the As-Built count summary compared against capitalized keys (`'High'`, `'Medium'`), so every risk miscounted as `Unknown` even though each table row showed the correct badge. Now matches case-insensitively.
- **Blank risk titles in As-Built Risk Register and Security Posture panels** — both rendered `r.title`, a field `normRisk()` never sets (only `description` exists), producing bare `[medium]`/`[high]` rows with no text. Now render `r.description`, which always has a value (falls back through several API field variants, then a generic message).

### Investigated
- **Monthly Capacity "Used (TB)" column showing all dashes** — traced live against the Active IQ API: this account's full systems GraphQL query errors (`Float cannot represent non numeric value: null`) and falls back to a reduced field set that drops `monthlyCapacity` entirely; the separately-queried cluster-level `monthlyCapacity` also returns `usedKiB: null` for every month while `rawMarketingKiB` is fully populated. Confirmed this is a genuine Active IQ data gap for this account (raw/marketing capacity has full monthly history, used capacity does not), not a bug. Added a per-month cluster-level merge fallback in `server.py` for accounts where the data does exist elsewhere in the response; when it's genuinely absent, the UI now says so explicitly instead of rendering a column of dashes.
- **Propensity score tooltips** — added explanatory tooltips clarifying that Active IQ's Propensity classification (CRITICAL/HIGH/MEDIUM/LOW) is NetApp's own proprietary churn/expansion model computed inside Active IQ; this tool only displays the value AIQ assigns and has no visibility into the underlying scoring logic.

---

## [4.4.0] - 2026-08-10

### Added
- **Intelligent sitemap-based product/integration auto-discovery (Scanner 8)** — `_scan_sitemap_discovery()` fetches `docs.netapp.com/sitemap.xml` (a real, sanctioned sitemap index — confirmed present in `robots.txt` and not disallowed) every scheduled enrichment cycle, diffs the ~262 top-level product/documentation sections against a persisted `data/discovered_products.json`, and automatically seeds `knowledge_base.json` with pages from any genuinely new section (bounded to 10 new sections per run, logged not silently dropped if the cap is hit). Verified end-to-end: NetApp's real, recent (August 2026) JetStream Software acquisition is discoverable this way with zero code changes, once NetApp's docs team publishes the pages under a new top-level section
- **13 new verified third-party integration seeds** — researched against NetApp's own documentation (every URL individually curl-verified live before inclusion): JetStream DR (VMware DR on Azure NetApp Files), Splunk (StorageGRID monitoring + SmartStore), Datadog (SNMP monitoring), Microsoft Sentinel/Splunk SOAR (Ransomware Resilience playbooks), ServiceNow (OnCommand Insight CMDB integration, 2 pages), IBM Db2 (SnapCenter plug-in, general + SAP-specific), Red Hat OpenShift (3 pages — solution architecture, VM DR via Trident Protect, container data protection), and Data Infrastructure Insights' ONTAP collector

### Fixed
- **`getSystemIntegrations()` fabricated an entire fake technology stack** — this function derived virtualization/database/backup-software claims (VMware vSphere, Oracle RAC, Commvault; OpenStack Cinder, NVIDIA AI BasePOD, Hadoop/Spark; Hyper-V, MS SQL, Veritas; etc.) from `parseInt(serialNumber) % 5` — a deterministic hash with **zero connection to any real telemetry** — and presented it in the "Enterprise Workload Alignments & 3rd-Party Integrations" panel and its "Active Workload Recommendations" as if detected from real Active IQ data, for every live customer system. Active IQ's GraphQL API has no field exposing this information (confirmed via extensive live schema introspection this session); the `sys.integrations` passthrough this function checked first is never actually populated anywhere in the codebase, so the fabricated branch fired for 100% of real systems. Now honestly returns "Not Reported by Active IQ" for all three categories, which correctly and automatically stops every downstream fabricated recommendation from firing too (the function's genuinely real MetroCluster-based recommendations, which don't depend on this data, are unaffected)
- Fixed a related grammar bug ("1 systems" instead of "1 system") in the same panel's aggregate counts, and added an honest notice message ("Not reported by Active IQ API for these systems — verify on-cluster via CLI") in place of the fabricated breakdown table when no real data exists

---

## [4.3.2] - 2026-08-10

### Fixed
- **Harvest crash on accounts with zero accessible systems** — tested the server against a second Active IQ account (different tenant, no watchlists configured, all 3 system-query tiers returned 0 systems). Discovered `_do_full_harvest()`'s contract-renewals fetch crashed with `'NoneType' object has no attribute 'get'`: `.get("systemContractRenewals", {})` only applies its default when the key is *missing* — GraphQL can return `{"data": {"systemContractRenewals": null}}` (key present, value `None`) for an account with no privilege/data in scope, and the chained `.get("systems")` call then crashes. Same bug pattern already fixed twice before in this codebase (NVD apiKey, risk-mutation enum values). Fixed here and found + fixed **5 more instances** of the identical pattern in `customers`, `sites`, `sustainabilityScore`, and both `osVersions` calls
- The harvest itself degrades gracefully otherwise: a 0-system result does not overwrite the existing cache, so the dashboard continues serving the last known-good data rather than going blank — confirmed this is intentional, working behavior, not a bug

### Documented (not a bug — confirmed via live introspection)
- The GraphQL `watchlists` query field referenced in two fallback code paths (`{ watchlists { id name } }`) **does not exist** in the current Active IQ GraphQL schema — verified via a fresh introspection query and a live test call that returned `GRAPHQL_VALIDATION_FAILED`. This fallback has therefore never worked for any account; REST-based watchlist discovery (`/v1/watchlists/list` etc.) is the only channel that has ever functioned, and even that returns `404`/`401` for several endpoint variants depending on account entitlements. Left the dead GraphQL fallback in place (harmless — already caught) with a comment explaining why, in case NetApp adds the field in a future API version

---

## [4.3.1] - 2026-08-10

### Improved
- **Operational Guidelines & Proceeding Steps (Action Planner, Section 8)** — a TAM had to read the full checklist top-to-bottom with no way to triage at a glance:
  - Added an at-a-glance urgency banner at the top ("⚠ N items require attention" / "✓ No blocking items"), color-coded by whether any critical risk is present
  - Priority Action Items now carry a P1-P4 badge and are sorted by urgency, instead of a flat unordered list
  - Plain "see Section 2" / "Section 3" / "Section 4" / "Section 6" text references replaced with clickable links that jump directly to that section via `switchPlanTab()`, verified live to actually navigate

---

## [4.3.0] - 2026-08-10

### Added
- **CISA KEV vs. acknowledged-risk cross-reference** — `riskInstances` query now requests `riskAcknowledgementInfo`; new `_check_acknowledged_risks_vs_kev()` flags every case where a TAM-acknowledged (accepted/deferred) risk's CVE has since appeared in CISA's Known Exploited Vulnerabilities catalog, meaning it's now under confirmed active exploitation rather than a theoretical rating. Surfaced as a dedicated alert block at the top of the Security Posture Executive Brief
- **Precise CPE-based NVD matching** — `_search_nvd_for_version()` now queries NVD's `virtualMatchString` (Common Platform Enumeration) using NetApp's real, verified NVD Dictionary product names (`clustered_data_ontap`, `storagegrid`, `e-series_santricity_os_controller` — confirmed via live introspection, not guessed) as the primary match, supplementing the existing keyword search rather than replacing it, deduplicated by CVE ID
- **NVD API key now used everywhere** — `scan_and_persist_advisories()`'s CVSS lookup and `_search_nvd_for_version()` previously ran unauthenticated (5 req/30s) even when a key was configured; both now read the key from `aiq_config.json` and pass it via the (correct, header-based) transport fixed in 4.2.2

### Fixed
- **Capacity enrichment gap: "Physical Used"/"Logical" permanently 0.00 TB** — the system-level API can populate `rawMarketingKiB`/`usablePerformanceTierKiB` while independently leaving `usedKiB` (and logical `usedKiB`) null. The existing cluster-level fallback was gated only on `_raw_kib == 0`, so this case — raw/usable present, used genuinely missing — fell through with a hardcoded 0 that no fallback logic ever touched. Added an independent per-field fallback to cluster-level capacity data for `usedKiB`/logical `usedKiB` specifically. Confirmed live on a real system: `clusterPhysicalUsedTB` went from a hardcoded `0` to a real recovered `0.003`
- **Confirmed not a bug**: a separate report of blank "System Identity & Hardware" fields (Model Revision, Marketing Type, Storage Config, Service Processor IP, Propensity, Next Best Action) for an older FAS8200 system was traced directly to the raw harvest data — Active IQ's own API returns empty strings/null for these fields for this system. The GraphQL query correctly requests them; this is a genuine upstream telemetry gap for older hardware, not a code defect, and the UI's `valOrDash()` already displays it honestly as "—" rather than fabricating a value

### Known limitation (not fixed — documented)
- A handful of third-party IMT integration-doc seed URLs (Veritas support portal, Red Hat/OpenStack docs) now return `403` to all automated traffic — a site-wide bot wall, not a dead link. No URL substitution fixes this; working around it would mean deliberately defeating another company's access controls, which this project won't do. One genuinely dead Veeam URL was fixed since it was an ordinary broken link, not a bot wall

---

## [4.2.2] - 2026-08-10

### Fixed
- **NVD API key sent via the wrong transport** — `fetch_cve_nvd()` and `_scan_nvd_netapp()` both appended `apiKey` as a URL query string parameter (`&apiKey=...`); NVD API 2.0 only accepts it as an HTTP header and silently returns `404 Not Found` for the query-string form regardless of whether the key is valid. Every NVD-backed enrichment call was failing whenever `nvdApiKey` was configured in `aiq_config.json` — worse than having no key at all, since an unauthenticated call would at least have succeeded (just at the slower 5-req/30s rate limit instead of 50/30s). `_enrich_fetch()` now accepts an `extra_headers` parameter; confirmed live: NVD scan went from `HTTP Error 404: Not Found` to a successful query after the fix

---

## [4.2.1] - 2026-08-10

### Fixed
- **Fleet silently reported as fully upgraded** — `enrichSystemTelemetry()`'s upgrade-recommendation logic used `let upgrades = s.upgrades;` — the same stale-cache pattern already fixed for `contracts` in 4.2.0. A pre-existing cached `upgrades` object (e.g. from before real Active IQ recommendation data was available for that system) permanently skipped recomputation regardless of the system's actual current OS version. Confirmed live: a system running ONTAP 9.12.1 showed "Systems Up to Date" / "No upgrades required" in the Technical Audit tab. After the fix, 163 of 167 systems in the test fleet were correctly reclassified as needing an upgrade. Live-data systems now always recompute upgrade recommendations fresh; mock/non-live systems still respect their intentionally pre-set `upgrades` field

---

## [4.2.0] - 2026-08-10

### Added
- **Native CVE data (`Risk.cves`)** — `riskInstances` GraphQL query now requests `cves { id cvssScore description summary lastUpdated }`; exposed as `normRisk.cveDetails` in `app.js`. Advisory-URL synthesis and `computeCostOfInaction()`'s CVE count now use this authoritative per-risk data instead of relying solely on regex-matching risk description text
- **Active IQ write-back actions** — `acknowledgeRiskInAIQ()`, `mitigateRiskInAIQ()`, and `updateQualifiedVersionInAIQ()` call the real `riskAcknowledge`, `riskMitigation`, and `updateQualifiedVersion` GraphQL mutations, writing changes back to the customer's live Active IQ account. Every previous ARIA action was read-only; these are clearly labeled "⚠ Writes to Active IQ" in the UI (Technical Risks tab and OS Upgrades tab) and require an explicit confirmation/justification prompt before firing
- **Case MTTR SLA metric** — MSP Service Delivery Report now includes a "Case MTTR" row in its SLA Compliance Matrix, computed via a fixed `computeMTTR()` (see Fixed)
- **Enrichment scheduler staleness checks and split timers** — fast security scanners (CISA KEV, PSIRT, NVD, EPSS) now skip re-scanning when their target file is already fresher than the configured interval; the slow KB/doc crawl and reference-library harvest (previously blocking the fast scanners for 5+ minutes) now run on their own independent, much longer interval. Fast-group runtime measured at 8.5s, down from 325.8s
- **What's New dismiss checkbox** — release-notes modal now has an explicit "Don't show this again until the next update" checkbox instead of a single ambiguous button

### Fixed
- **What's New modal silently broken dismiss buttons** — a changelog entry containing literal `<script>/<style>/<noscript>` text, injected unescaped via `innerHTML`, switched the browser's HTML parser into script-data mode and silently swallowed the modal's own footer buttons as inert text. They were never real, clickable DOM elements. All changelog text is now HTML-escaped before rendering
- **`computeMTTR()` always returned `null`** — read a field name (`openedDate`) that is never actually set anywhere in the codebase; the real field is `createdDate`. Function was silently broken and unused; now fixed and wired into the MSP report
- **MEDDPICC Brief blank Economic Buyer / Champion sections** — `propCategory`, `nextBestAction`, `primContact`, `email`, `phone` were hardcoded to `'—'` despite the underlying data (`propensityCategory`, `nextBestAction`, `sys.contacts`) being available and used correctly elsewhere in the file
- **Security Brief CVE detection** — switched from `r.title.includes('cve')` string-matching to native `cveDetails`; removed hardcoded `daysSinceOldestCVE = 30` in favor of a real exposure window computed from actual CVE dates; fixed duplicate "7." section numbering (Security Roadmap vs. NIST CSF 2.0)
- **MSP Report fabricated columns** — "Backup" column always showed `'OK'` and "Cloud(TB)" always showed `'TBD'`/`'0.0'` regardless of real data; both removed. "Avail(TB)" derived from the always-zero `physicalAvailTB` field; now computed from `usableCapacityTB - physicalUsedTB`
- **Literal `\n` and stray-quote rendering bugs** — QBR Pack's prior-quarter-actions fallback text had an escaped `\\n` (literal backslash-n) instead of a real newline; Sales Refresh Proposal had a stray literal `"` character before "Service Level" in every contract-renewal line item. Both reached the actual downloaded TXT files
- **`domesticParent` vs `domesticParentName` inconsistency** — `compileCustomerSuccessPlanText` and `compileMSPServiceReport` read the non-canonical `domesticParent` (always undefined); standardized on `domesticParentName`
- **Fabricated numeric defaults presented as real telemetry** — a hardcoded "7.5/10" satisfaction score, "120 days" capacity runway, and "100 GB/day" growth rate would silently appear in place of missing data across the Site Logistics report, CSV export, and TAM Success Plan. Replaced with either a real computed value (case-health score) or explicit "No Data" indicators; fixed a CSV export bug where `null` would have literally rendered the string `"null"`
- **Three different health-grade formulas** — QBR Pack and Extended Deliverables each computed their own local health score/grade with different thresholds than the canonical `computeAccountHealthScore()`/`getHealthGrade()` used by the MEDDPICC Brief, meaning the same account could receive a different letter grade depending on which deliverable a TAM handed the customer. Unified on the canonical functions
- **Sustainability Report unsourced ESG figures** — power/CO2 "avoided" figures used unreferenced 0.5 kW/TB and 0.5 kg CO2/kWh conversion constants with no methodology disclosure; added an explicit estimate-methodology footnote. "Physical Footprint Avoided" was a duplicate restatement of the "Space Saved" figure; merged into one line. Systems with a genuine 0 sustainability score were previously indistinguishable from "no data" and silently excluded from optimization recommendations; now correctly included
- **As-Built TXT export missing sections** — the downloadable As-Built Configuration Document was missing Account & Success Team, Capacity Growth & Projections, and Risk & Advisory Register sections present in the in-app HTML view; added
- **Stale deliverable counts** — "Deliverables Suite (10)" tab label and "Download all 10 deliverables" comment both corrected to the actual count of 13

---

## [4.1.0] - 2026-08-06

### Fixed
- **CVE count inflation** — `computeCostOfInaction()` now counts unique CVE IDs via `Set` instead of summing raw `securityBulletins.length` across all systems. "180 unpatched CVEs" corrected to actual unique count (e.g. 2 for test fleet)
- **Security brief severity mismatch** — `compileSecurityBrief()` severity comparison now uses `.toLowerCase()` to match API-normalized values; previously compared uppercase literals against lowercase data, producing `Total Risks: 0` despite 18 findings
- **ARP denominator errors** — All ARP coverage displays and computations (COI scoring, security brief, MEDDPICC, feature adoption table `_fmtAdopt`) now use total fleet size as denominator instead of `arpKnownSys.length`; systems with unknown ARP status are conservatively treated as unprotected
- **HW firmware "undefined"** — `computeFleetFirmwareSummary()` per-system entries now include computed `score` (0-100) and `status` (`Current`/`Partial`/`Behind`) properties; eliminates "undefined (undefined%)" in implementation runbook
- **SVM count "0 (None)"** — Implementation runbook now uses `getSystemSvms(sys)` instead of nonexistent `sys.svms` property
- **Warranty expiring undefined** — `computeFleetWarrantyStatus()` now returns `expiring30`, `expiring90`, `active`, and `expired` fields; sales refresh proposal no longer shows "undefined" for warranty timeline
- **Sustainability score disagreement** — `compileSustainabilityReport()` reads correct efficiency fields (`logicalUsedTB`/`physicalUsedTB`/`spaceSavedTB`); `compileMEDDPICCBrief()` removes arbitrary `|| 50` fallback that inflated scores
- **Security brief TAM** — `compileSecurityBrief()` scans `csmName` from fleet data instead of unreliable `window.currentUser.name`
- **MEDDPICC personnel** — `compileMEDDPICCBrief()` reads `csmName`/`salesRepName` directly instead of `salesHealth.supportTam`/`salesHealth.accountManager` which had wrong mappings
- **Advisory email findings count** — Total findings label now uses per-severity sum instead of deduplication group count
- **Indistinguishable upgrade actions** — Group headings now append affected system names (e.g. "Upgrade to ONTAP 9.19.1 — resolves 4 findings (SYS_01, SYS_02)")
- **TAM QBR literal \n** — Risk descriptions sanitized via `_truncate(s, 300)` helper that strips raw `\n` and truncates at sentence boundaries
- **Account handover document count** — Total derived from sum of category counts instead of independent `ecosystemData.length`
- **Solution architecture system count** — Now counts distinct affected systems from risk data instead of using total fleet size
- **Platform string duplication** — Parenthetical model suffix skipped when `platform === model` or when `systemName` already contains the platform string
- **Site name concatenation** — City suffix suppressed when `siteName` already contains the city name (e.g. prevents "Johannesburg — Johannesburg, ZA")
- **Security brief CVE sort** — Severity sort map handles lowercase values from API normalization
- **Feature adoption NaN** — `_fmtAdopt()` helper now guards against `totalLen === 0` to prevent `NaN%` for customers with empty fleets

### Changed
- **ARP protection logic** — `computeCostOfInaction()` uses `isARPEnabled !== true` instead of `=== false` to correctly identify systems with `null`/`undefined` ARP status as unprotected

---

## [4.0.9] - 2026-08-05

### Fixed
- **E-Series / SANtricity platform detection** — numeric platform codes from Active IQ (e.g. `2824` for E2800, `2900` for E2900, `5700` for E5700, `4000` for E4000) were falling through to ONTAP enrichment instead of SANtricity. Fixed in 5 detection sites:
  - `_getVersionType()` — enrichment type router now detects numeric codes via `/^(28|29|57|40)\d{2}$/` regex and `santricityVersion` property
  - `enrichVersion()` — dispatch function now routes E-Series to `enrichSANtricity()` correctly; also reads `sys.santricityVersion` as version source
  - `getLatestSupportedVersion()` — returns "SANtricity OS 12.0" instead of "ONTAP 9.19.1" for E-Series systems
  - `calculateUpgradePath()` — uses SANtricity version matrix instead of ONTAP upgrade rules
  - Version Intel header — falls back to "SANtricity" label instead of hardcoded "ONTAP" when `santricityVersion` is present
- **Server-side upgrade path** — `fetch_upgrade_path_info()` in `server.py` now has a dedicated SANtricity branch that fetches the E-Series what's-new page and uses `11.x` / `12.x` version regex instead of ONTAP's `9.x.x` pattern
- **HTML parser script injection** — `_strip_html_tags()` now skips content inside `<script>`, `<style>`, `<noscript>`, and `<svg>` tags; `_parse_netapp_release_notes()` pre-strips these blocks with regex before extracting release notes, preventing raw JavaScript from appearing in Version Intel cards
- **E-Series model coverage gaps** — added detection for `ef300`, `e2800`, `e2900` string matches that were missing from several detection functions

### Changed
- **Reference harvester** — expanded SANtricity data collection in `tools/reference_harvester.py`
- **Knowledge base** — new E-Series and SANtricity KB entries added to `data/knowledge_base.json`

## [4.0.8] - 2026-08-04

### Added
- **Support Case Health Engine** (`computeSupportCaseHealth()`) — computes a real 0–10 health score from live Active IQ support case data, replacing the hardcoded CSAT `sentimentScore` that was always 0 (live) or 7.5 (fallback):
  - **Severity penalties**: P1 open cases deduct 3.0 pts each, P2 deduct 1.5, P3 deduct 0.5
  - **Volume penalties**: >3 open cases deduct 0.3 pts each beyond threshold
  - **Aging penalties**: cases open >30 days deduct 0.5 pts each; >90 days deduct 1.0 pts each
  - **Escalation penalties**: escalated cases deduct 1.0 pts each
  - **Resolution velocity bonuses**: fast mean-time-to-resolve on closed cases adds up to +1.5 pts
  - Fallback: systems with no case data score 10.0/10 ("Excellent")

### Changed
- **Account Health Score** — "CSAT" component (10% weight) now uses `computeSupportCaseHealth()` instead of static constants
- **Normalization pipeline** — `normalizeSystem()` auto-computes case health during data ingestion; propagates to all downstream consumers
- **TAM System Detail Card** — "Customer CSAT Sentiment" label → "Support Case Health" with computed score and health bar
- **Sales Health Summary** — "Average CSAT Sentiment" label → "Support Case Health"; default fallback score adjusted from 8.0 to 7.0
- **Per-system popups** — "CSAT Score:" → "Case Health:" throughout
- **CSV export** — column header "CSAT Sentiment" → "Case Health"
- **All 7 deliverable templates** — CSAT labels replaced with "Support Case Health" / "Case Health Score" in CSP, QBR, MSP, MEDDPICC, Handover, Security Brief, Sustainability reports
- **MEDDPICC Brief** — `avgCsat` computation now calls `computeSupportCaseHealth()` per system instead of using `sentimentScore || 7.5`
- **Health Score tooltip** — updated weight description to reflect 8 components with correct percentages

---

## [4.0.7] - 2026-08-04

### Added
- **Hardware Firmware Currency Scoring Engine** (`computeFleetFirmwareSummary()`) — fleet-wide composite firmware health scoring across 4 subsystems:
  - SP/BMC firmware currency (25% weight)
  - Motherboard BIOS firmware currency (25% weight)
  - DQP currency (20% weight)
  - Drive firmware currency (30% weight)
  - Per-system breakdown with status classification (Current ≥80% / At Risk ≥50% / Critical <50%)
  - Weighted composite score (0-100%) exposed via `_firmwareSummary` in deliverables return object
- **Hardware Firmware Currency UI Badge** — color-coded indicator in the KB Intelligence Summary Panel showing fleet-wide firmware health with inline SP/MB/DQP/Drive breakdown and CURRENT/AT RISK/CRITICAL status label
- **9 New IMT Vendor Entries** in `data/imt_interop.json` — full version compatibility matrices for:
  - Veritas NetBackup (v10.3–10.5)
  - Veritas Backup Exec (v21–24)
  - VMware vSphere/ESXi (v6.7 U3–8.0 U3)
  - Microsoft Hyper-V / Windows Server (2016–2025)
  - Red Hat Virtualization / oVirt (v4.3–4.4)
  - OpenStack Manila/Cinder NetApp Drivers (2023.2–2025.1 Epoxy)
  - Citrix Hypervisor / XenServer (v8.2–8.2 CU1)
  - Proxmox VE (v7.4–8.3)
  - Nutanix AHV (latest)
- **9 New Reference Harvester Scrapers** in `tools/reference_harvester.py` — automated version tracking for all new IMT vendors, matching the `harvest_imt_versions()` pattern with per-vendor URL and regex extraction
- **Firmware data injection into all 7 deliverable templates**:
  - `compileCustomerSuccessPlanText` — HW Firmware Currency in Operational Health Scorecard
  - `compileQBRPack` — HW Firmware Currency in health scorecard
  - `compileMSPServiceReport` — HW Firmware Currency in SLA section
  - `compileMEDDPICCBrief` — HW Firmware Gap as MEDDPICC risk/upsell metric
  - `compileAccountHandoverBrief` — HW Firmware Currency in posture section
  - `compileSecurityBrief` — HW Firmware Attack Surface (3-line breakdown: SP, MB, DQP, Drive)
  - `compileSustainabilityReport` — Hardware Firmware Health in efficiency section

### Changed
- **Account Health Score rebalanced** — added hardware firmware as 8th component (8% weight). New weights: ASUP 15% + ARP 12% + OS FW 12% + HW FW 8% + Contract 13% + Risk 20% + Efficiency 10% + CSAT 10% = 100%
- **Version bumped to 4.0.7** across `version.json`, `app.js` (`APP_VERSION`), `README.md` badge, `CONTEXT.md`, and CHANGELOG.md
- **README.md** updated: health score formula table reflects 8-component weighting, file tree includes `tools/reference_harvester.py` and new data files, component reference sizes updated

---

## [4.0.6] - 2026-08-04

### Added
- **Section 18 — Firmware Currency** — new Action Planner tab providing comprehensive per-system firmware auditing:
  - Per-system firmware cards showing ONTAP version, system firmware, motherboard firmware, DQP version
  - Shelf module firmware table with current vs. recommended baseline status
  - **Drive firmware aggregation table** with model, current FW, recommended FW, ✅/⚠️ status badge, vendor, and count columns
  - Fleet-wide firmware currency summary ribbon: current / behind / unknown drive counts across all systems
  - Semantic version comparison (`_fwMatch`) handles dot-delimited, patch-level (e.g., `9.16.1P11`), and alphanumeric firmware strings
- **Multi-source firmware harvester** (`tools/firmware_harvester.py`) — cascading fallback strategy to bypass Cloudflare/Akamai WAFs on docs.netapp.com:
  - Source 1: `endoflife.date` API for ONTAP and SANtricity lifecycle/version data
  - Source 2: PyPI package metadata for NetApp SDK versions
  - Source 3: GitHub release APIs for Trident, Harvest, and related tools
- **Server-side drive firmware auto-discovery** — `server.py` enhanced with fleet-driven DQP-based drive firmware recommendations:
  - Populates `recommendedDriveFirmwares` map keyed by drive hardware model name during harvest
  - Recommendations flow through to per-system objects for client-side rendering
- **DQP parser utility** (`tools/dqp_parser.py`) — parses Disk Qualification Package files for drive firmware extraction

### Fixed
- **Drive firmware Recommended/Status columns always showing `—`** — `enrichSystemTelemetry()` constructs a new object with an explicit field list; `recommendedDriveFirmwares` was missing from that return object and was silently dropped during system enrichment. One-line fix at the return statement.
- **Firmware probe endpoint** (`/api/firmware-probe`) added for live drive firmware debugging

### Changed
- **Version bumped to 4.0.6** across `version.json`, `app.js` (`APP_VERSION`), `README.md` badge, and CHANGELOG.md
- **README.md** updated: Section count 17→18, file tree includes `tools/firmware_harvester.py`, component reference sizes updated, drive firmware currency added to feature list
- **Firmware baselines expanded** with current ONTAP 9.19.1+ and SANtricity 12.00 versions in `data/firmware_baselines.json`

---

## [4.0.5] - 2026-08-02

### Removed
- **6 unreportable feature fields purged** — the following fields were always `null` from the Active IQ GraphQL API and have been completely removed from `normalizeSystem()`, `computeFeatureAdoptionScore()`, `_buildSecurityChecklist()`, `_renderFeatureAdoptionSection()`, and all remediation/hardening blocks:
  - `isAuditEnabled` — NAS audit logging state not exposed by API
  - `isSnapLockEnabled` — SnapLock compliance/enterprise mode not exposed by API
  - `isMAVEnabled` — Multi-Admin Verification state not exposed by API
  - `nvEncryptionEnabled` (+ `nveStatus`, `nveDisabled`) — NVE/NAE encryption state not exposed by API; was a heuristic guess
  - `isFlexPod` — FlexPod membership not exposed by API
  - `belongsToMixModelCluster` — mixed-model cluster membership not exposed by API
- **Encryption/Audit/MAV/SnapLock columns** removed from Feature Adoption HTML table (header, data rows, summary row, and missing-feature recommendations)
- **`nveDisabled` counter variable** and its counting logic removed from remediation blocks

### Fixed
- **ARP denominator inflation** — ARP coverage percentage now uses "known-system" count (systems where ARP status is actually reported) instead of total fleet size. Prevents systems that don't report ARP from being counted as "disabled". Applied across 6 deliverable templates: Account Health Score, CSM Report, Executive Briefing, QBR, MEDDPICC, Talking Points
- **False-negative feature flags** — Feature Adoption table now renders tri-state icons: ✅ enabled, ❌ disabled, — unknown/not reported. API `null` values no longer counted as disabled

### Changed
- **Feature Adoption scope narrowed to API-confirmed fields only**: ARP, FabricPool, MetroCluster, All Flash Optimized, HA Configured, SnapMirror, Operating Mode
- **Checklist item #11** updated from "Volume encryption (NVE/NAE) enabled" to "Anti-Ransomware Protection (ARP) active on all volumes"
- **Encryption Coverage metric renamed** to "ARP Coverage" with known-system denominator
- **Version bumped to 4.0.5** across `version.json`, `app.js` (`APP_VERSION`), `README.md` badge, and CHANGELOG.md

---

## [4.0.4] - 2026-08-02

### Added
- **Certified Reference Architecture Enrichment** — 31 new `reference_architecture` sources added to `VENDOR_GUIDELINE_SOURCES` covering:
  - **FlexPod CVDs** — Cisco Validated Designs (Design Zone, FlexPod Solutions Portal, FlexPod Documentation Center)
  - **NetApp Verified Architectures (NVA)** — workload-specific validated architecture library
  - **Technical Reports (TRs)** — TR-4569 (Security Hardening), TR-4067 (NFS), TR-4515 (AFF SAN), TR-4929 (FlexPod DC), TR-4616 (NFS Kerberos), TR-4571 (FlexPod Architecture), TR-4613 (NVMe/FC), TR-4733 (SM-BC), TR-4614 (SAP HANA Backup), TR-4668 (Oracle), TR-4590 (SQL Server)
  - **AI/ML Reference Architectures** — NVIDIA DGX SuperPOD + ONTAP, NetApp AI Solutions documentation
  - **Industry Solutions** — Healthcare (Epic, Cerner, Imaging), Financial Services (SEC 17a-4, SnapLock WORM)
  - **Automation & IaC** — Ansible Galaxy ONTAP Collection, Terraform ONTAP Provider, ONTAP Automation Toolkit
  - **BlueXP Services** — Ransomware Protection, Classification/Data Sense, Tiering, Disaster Recovery, Backup & Recovery
  - **Keystone STaaS** — subscription-based opex storage documentation
  - **Nutanix AHV** — Early Access iSCSI SAN integration (GA targeted Q3 2026)
- **REFERENCE_LIBRARY_INTEGRATIONS: referenceArchitectures catalog** — new app.js knowledge base section with 7 sub-categories:
  - `flexpod` — 6 key FlexPod CVD designs + 4 benefits (joint support, firmware matrices, deployment risk, lifecycle)
  - `nva` — 8 NetApp Verified Architectures (DGX SuperPOD, Oracle, SQL Server, SAP HANA, VDI, Splunk, OpenShift, Epic)
  - `technicalReports` — 8 key NetApp TRs with corrected titles (TR-4614→SAP HANA Backup, TR-4616→NFS Kerberos)
  - `partnerSolutions` — 14 certified alliance partners (Cisco, VMware, Veeam, Commvault, Microsoft, Red Hat, NVIDIA, SAP, Oracle, Ansible, Terraform, Rubrik, Cohesity, HYCU)
  - `bluexp` — 6 BlueXP SaaS services
  - `keystone` — 5 Keystone STaaS features
- **Comprehensive Fleet Signal Detection** — 14 previously unmapped signal keys now have detection logic:
  - **Backup vendors**: `rubrik`, `cohesity`, `hycu`, `veritas` (via risk text matching)
  - **Databases**: `oracle_db`, `mssql`, `sap_hana` (via risk text: Oracle/dNFS/ASM, SQL Server/MSSQL/Always On, SAP HANA)
  - **Security tools**: `crowdstrike`/Falcon, `paloalto`/Prisma/Cortex, `varonis`, `cyberark` (via risk text)
  - **Observability**: `splunk` (via risk text)
  - **Containers**: `kubernetes`/Trident/OpenShift (via risk text)
  - **AI/ML**: `ai_ml`/GPU/DGX/NVIDIA (via risk text)
  - **Hypervisors**: `proxmox`/PVE, `nutanix`/AHV (via host OS detection)
  - **FlexPod**: `flexpod` (via `isFlexPod` API property, platform text, and risk text)
- **Deliverable Template Updates** — Solution Proposals now include a dedicated "CERTIFIED REFERENCE ARCHITECTURES & VALIDATED DESIGNS" section; Customer Communications includes reference architecture document count badge

### Fixed
- **FlexPod signal initialization** — added `'flexpod': False` to `fleet_signals` init dict (was being set but never initialized)
- **TR number corrections** — TR-4614 correctly mapped to SAP HANA Backup & Recovery (not SAN Host Reporting), TR-4616 correctly mapped to NFS Kerberos (not general ONTAP encryption)

### Changed
- **Version bumped to 4.0.4** across `version.json`, `app.js` (APP_VERSION), `README.md` badge, and CHANGELOG.md
- **Total fleet signal keys expanded to 40** (39 original + flexpod), all with active detection logic

---

## [4.0.3] - 2026-08-01

### Added
- **25-Point Categorized TAM/MSP Remediation Readiness Checklist** — expanded the previous 15-point flat checklist to 25 checks organized into a 2-column categorized layout:
  - **Left Column: Operations & Security** (15 checks across 4 categories):
    - *Software & Platform*: OS version currency, hardware EOA status, firmware & disk qualification currency
    - *Infrastructure Health*: storage efficiency ratio, aggregate capacity headroom ≥20%, HA pair configuration, network port health (link-down detection), QoS adaptive policy coverage
    - *Security & Compliance*: PSIRT CVE exposure, CISA KEV active exploitation alerts, NVE/NAE volume encryption, Anti-Ransomware Protection (ARP) status
    - *Support & Monitoring*: AutoSupport HTTPS reporting recency, S1/S2 critical case detection, outstanding Field Safety Alerts
  - **Right Column: Data Protection & Lifecycle** (10 checks across 3 categories):
    - *Data Protection*: SnapMirror replication configuration, FabricPool cold-data tiering, SVM/LIF inventory mapping, FlexClone sprawl detection (≤10 threshold)
    - *Risk & Remediation*: critical/high risk count, feature adoption score ≥60%, config drift detection (unassigned ports), MTTR posture (stale cases >90 days)
    - *Contracts & Lifecycle*: support contract expiry (>90 days), contract co-term alignment
- **Per-Column Pass/Fail Score Headers** — each column displays a dynamic "X/Y passed" score badge that updates with the check results.
- **Category Divider Labels** — visual category separators within each column for quick scanning during TAM/MSP reviews.

### Changed
- **Checklist UI layout** — replaced single-column scrollable list with a `grid-template-columns: 1fr 1fr` two-card layout. Each card has its own header with title and score badge. Both `index.html` and `index_src.html` updated.
- **Aggregate and single-system rendering paths synchronized** — both the multi-system aggregate view and single-system detail view now render the same 25-check categorized structure.
- **Reset/clear logic updated** — both view-switch clear points now also reset the right-column panel and score header elements to prevent stale data display.
- **Version bumped to 4.0.3** across `version.json`, `app.js` (`APP_VERSION`), `README.md` badge, and documentation.

---

## [4.0.2] - 2026-08-01

### Added
- **Platform-Specific Controller Rear-Panel Backplate** — new `_buildControllerBackplate()` function renders an accurate physical rear-panel visualization for each NetApp hardware family. Supports 8 distinct platform layouts:
  - **Next-Gen Modular (A70/A90/A1K/FAS70/FAS90/AFX)** — 11 I/O slot strip with labeled sections: HA/Cluster (Slots 1, 7), Data/FC I/O (Slots 2–6), System Management Module (Slot 8 — e0M, console, USB), and Storage/I/O (Slots 9–11), plus dual PSU.
  - **Mid-Range 10-Slot (A400/A900/FAS8300/8700/C400)** — onboard I/O section (e0M, e0a/b HA, e0c/d Cluster) plus 10 individually labeled PCIe expansion slots.
  - **A800/C800 NVMe (5-Slot)** — dedicated MGMT+BMC section with 5 PCIe slot strip.
  - **Entry 2U (A250/C250/FAS2820/A150)** — management/console section, onboard Ethernet (Cluster + Data), mezzanine FC/UTA2 slot, and SAS/NVMe shelf ports.
  - **E-Series (EF600/E5700)** — duplex controller canister with MGMT/SVC, baseboard/HIC host ports, and drive expansion SAS ports.
  - **Cloud Volumes ONTAP** — virtual appliance banner (AWS/Azure/GCP) with provider detection.
  - **StorageGRID Appliances** — object appliance node banner with SG-model auto-detection.
  - **Generic ONTAP Fallback** — auto-grouped MGMT, I/O, and PSU sections for unrecognized platforms.
  Each port block shows port name, type color-coding (blue=Cluster/HA, amber=Data, purple=Storage, yellow=FC, green=Mgmt), live status LED (green/red), and interactive hover integration with the cabling audit table via `hoverCablingPort()`/`unhoverCablingPort()`.
- **SVM & LIF Inventory Enrichment** — new `compileSvmLifInventoryText()` function generates per-SVM logical interface inventories for inclusion in TAM deliverables. Lists each SVM's LIFs with IP addresses, service policies, data protocols, home/current node and port, failover policy, and operational status.
- **Vserver Data Harvesting via GraphQL** — `server.py` now requests `vservers { id name type subType logicalInterfaces { ... } }` from the AIQ cluster endpoint and maps vserver data to individual systems via `serial_to_cluster_vservers`. Includes LIF failover configuration (home node/port, current node/port, failover policy).
- **Network Ports GraphQL Field** — added `networkPorts { totalCount networkPorts { port role link type broadcastDomain ipspaceName speedOperationalMbps macAddress maxTransmissionUnitBytes interfaceGroupOwner } }` to both full and medium system GQL queries for physical port metadata enrichment.
- **Harvest Merge-Back Guard** — when the Active IQ API returns 0 systems or 0 clusters due to transient timeouts, the harvester now preserves the previous harvest's data rather than overwriting with empty arrays. Logged as `[HARVEST] Merge-back: keeping N systems/clusters from previous harvest`.
- **Module-Level Vserver Cache** — `_vserverCache` moved to module scope (outside `state`) to survive `localStorage`-driven state replacements. Keyed by `serialNumber`, populated during `loadProductionData()` and `enrichSystemTelemetry()`.

### Fixed
- **Card content clipping** — changed `.card` CSS `overflow` from `hidden` to `visible`, preventing data tables and backplate visualizations from being cut off inside dashboard cards.
- **SVM data retrieval robustness** — `getSystemSvms()` now checks both `sys.vservers` and the module-level `_vserverCache`, with `localStorage` fallback, ensuring SVM/LIF data persists across page reloads.

### Changed
- **Version bumped to 4.0.2** across `version.json`, `app.js` (`APP_VERSION`), `README.md` badge, and documentation.
- **TAM Node Visual Layout refactored** — `renderNodeVisualLayout()` now renders the platform-specific backplate above the cabling audit table instead of the previous generic port grid. The layout is stacked full-width rather than side-by-side.
- **Deliverable text generators updated** — all 13 deliverable compile functions now include SVM/LIF inventory sections when vserver data is available.
- **Capacity GQL fields trimmed** — removed `usedWithoutSnapshotsKiB` and `usedWithoutSnapshotsClonesKiB` from capacity queries that were causing API errors on some clusters.

---

## [4.0.1] - 2026-08-01

### Added
- **Deliverable Intelligence Enrichment** — all 13 TAM deliverables now receive enriched content sections for DR & Replication coverage, capacity forecast & runway, and feature adoption analysis. Each deliverable's generated text includes fleet-specific metrics (SnapMirror relationship counts, RPO/RTO assessment, unprotected system identification, growth rate forecasting, and per-system 15-point best-practice adoption scores) drawn from live API data.
- **Dynamic Remediation Plan Fields** — risk detail modals for live API-sourced risks now populate the **Options & Trade-Offs** and **Compliance & Regulatory** sections from `generateDynamicRemediationPlan()` output, showing risk-specific alternatives, considerations, and regulatory context instead of empty/generic placeholders.

### Fixed
- **Cluster name "unknown" in table and chart** — when the Active IQ API's cluster-to-serial lookup returns no match, the server and client now derive the cluster name from the system hostname by stripping node suffixes (e.g. `A150-CLUSTER-01` → `A150-CLUSTER`). Fixes the Cluster column in the system table and the x-axis labels in the "Storage Capacity by System" chart both showing "unknown".
- **Platform-aware upgrade logic for all live systems** — ONTAP, StorageGRID (11.x → 11.9), and E-Series/SANtricity systems from the live API now receive correct upgrade path calculations. Previously, only ONTAP systems were evaluated; StorageGRID 11.x systems were incorrectly shown as "Up to Date" and E-Series models were unrecognized.
- **E-Series model detection expanded** — added recognition for E2824, E5700, and EF4000 models. SANtricity upgrade paths now use version-range matching (e.g. 11.70 → 11.80 series).
- **E-Series hardware synthesis** — live E-Series systems now receive a synthesized `eseriesHardware` object (controller model, drive count/type, management interface version) so the SANtricity Hardware Audit card renders properly instead of showing empty.
- **Feature adoption TypeError** — fixed `s.gaps.slice is not a function` crash by deriving feature gaps inline from boolean flags rather than expecting a pre-built array.
- **Capacity forecast wrapper** — added missing `computeFleetCapacityForecast()` function that delegates to `computeFleetCapacitySummary()` with mapped property names, fixing undefined-function errors in deliverable generation.
- **Linkify anchor tag breakage** — the `linkify()` function no longer matches NTAP/CVE patterns inside existing `<a>` tag `href` attributes, preventing double-wrapping that broke advisory links.
- **StorageGRID false "Up to Date"** — StorageGRID 11.x systems (e.g. 11.7, 11.8) are no longer incorrectly marked as current when 11.9 is the recommended target.

### Changed
- **Version bumped to 4.0.1** across documentation.
- **app.js** — `enrichSystemTelemetry` cluster fallback now uses hostname with node suffix stripped (regex: `[-_](?:0[1-9]|node\d+|n\d+)$`) before defaulting to "unknown".
- **server.py** — cluster name extraction uses `re.sub()` on hostname as fallback when serial-to-cluster lookup returns empty.

---

## [4.0.0] - 2026-08-01

### Added
- **Fleet-Aware Enrichment Engine** — complete rewrite of the knowledge base scanner (§6a–6e). The enrichment system now discovers **268+ real articles** per scan from NetApp's public documentation, up from 0 in the previous release.
- **JSON-LD Category Tree Crawler** (§6a) — replaced the broken `kb.netapp.com` regex scraper (JS-rendered, returned 0 results) with a structured data crawler that extracts categories and sub-categories from JSON-LD `<script>` blocks. Discovers 64+ KB articles across 3 hierarchy levels.
- **docs.netapp.com Index Crawler** (§6b) — crawls the real ONTAP, hardware systems, NAS management, SAN management, and upgrade index pages, extracting 139+ doc links with auto-classification by URL path keywords.
- **Fleet KB Sub-Category Crawling** (§6e-iv) — crawls ONTAP-specific KB domains (Data Access, Data Protection, MetroCluster, SnapMirror, SnapLock, NAS, SAN) using JSON-LD extraction. Discovers 27+ fleet-relevant articles.
- **Deliverable Enrichment Mapper** — new `getFleetEnrichmentSections()` function maps scored fleet-relevant articles into all 13 TAM deliverables. Each deliverable receives contextually appropriate reference blocks:
  - Problem Statements → security/remediation guides, troubleshooting procedures
  - Customer Communications → summary of attached reference counts
  - Change Tickets → upgrade procedures, operational procedures
  - Solution Proposals → integration docs, cloud/hybrid references
  - Implementation Runbooks → upgrade, ops, troubleshooting, security, data protection
  - Sales Proposals → lifecycle/migration, cloud modernisation, ecosystem docs
  - Customer Success Plan → full KB by category
  - QBR Pack → KB coverage summary, top security & upgrade refs
  - MSP Report → ops procedures, troubleshooting, performance tuning
  - Account Handover Brief → complete reference library by category
  - MEDDPICC Brief → pain-mapped evidence (security, upgrades, known issues)
  - Security Brief → remediation/hardening + data protection refs
  - Sustainability Report → efficiency, cloud tiering, lifecycle/refresh docs
- **Fleet Relevance Scoring** — articles are scored 0–100+ based on ONTAP version match (+30), model match (+25), platform family match (+20), operational category (+10), and ops keywords (+5). Minimum score of 5 required for inclusion.
- **`GET /api/knowledge-base`** endpoint — serves KB articles with CISA KEV count and bulletin severity summary for client-side enrichment.
- **Client-side KB loader** — `loadEnrichmentKB()` fetches and caches KB data at startup; `getFleetRelevantArticles()` filters and scores articles by fleet context.
- **KB Intelligence Summary Panel** — new dashboard card above the deliverables section showing aggregate enrichment statistics (total articles, per-category breakdown: Risk, Customer, Security, TAM Ops, QBR/MSP, ESG), fleet profile context (system count, ONTAP versions, platform families, hardware models), with cyan-to-purple gradient design.
- **Enrichment Badges** — all 13 deliverable cards now display inline `★ N KB refs` badge pills showing the count of KB intelligence articles enriching each specific deliverable. Badges render conditionally (only when articles > 0) with tooltips describing what enrichment adds.
- **Rich Contextual Intelligence Engine** — new `getArticleContext()` function within `getFleetEnrichmentSections()` generates fleet-specific intelligence per article: CLI commands (`security anti-ransomware volume enable`, `metrocluster show`, etc.), effort estimates (e.g. "15 min/volume", "2 hours for full audit"), and fleet-aware remediation steps (e.g. "Enable ARP on 3 systems with ARP disabled").
- **Deliverable cards relabeled A–M** — 13 deliverables consistently numbered from A (Executive Risk Assessment) through M (Account Handover Brief) across all three categories (Risk & Remediation, Customer & Sales, TAM/MSP Operations).
- **75 Integration Seed URLs** — expanded `server.py` integration seeds from ~38 to 75 entries covering VMware (6), Kubernetes/Astra (5), Databases (6), Cloud/Hybrid (8), Backup (5), Security (8), Monitoring (5), Data Protection (7), Networking (5), Upgrades (6), Sustainability (4), and Common Operations (10).

### Fixed
- **Scanner §6a (KB search)** — `kb.netapp.com/?q=` search pages are JS-rendered; the HTML regex found 0 results. Replaced with JSON-LD structured data extraction.
- **Scanner §6b (docs URLs)** — some hardcoded `docs.netapp.com` sub-paths returned 404 (URL structure changed). Replaced with live index page crawling.
- **Scanner §6e-i (version docs)** — versioned URLs like `/ontap914/` all return 404 (ONTAP docs are not versioned by URL). Replaced with single `/ontap/` tree tagged with fleet version context.
- **Scanner §6e-ii (platform docs)** — incorrect hardware paths (`/a-series/` → `/aff-aseries/`, `/c-series/` → `/aff-cseries/`, `/asa/` → `/allsan-landing/`). Corrected to actual docs.netapp.com structure.
- **Scanner §6e-iv (KB troubleshooting)** — same broken regex scraper as §6a. Replaced with JSON-LD sub-category crawling.
- **Scanner §6e-v (remediation)** — same broken search. Replaced with direct security doc links and bulletin cross-referencing.
- **MindTouch API** — `@api/deki/site/search` returns 403 Forbidden. Abandoned in favour of JSON-LD extraction.

### Changed
- **Version unified to 4.0.0** across all files: `version.json`, `app.js` (`APP_VERSION`), `README.md` badge, `CONTEXT.md`, `index.html`, `index_src.html` footer, `launcher.py`, `Start-Dashboard.ps1`, `start_dashboard.bat`, `build/AIQscraper.spec`, `build/Install_NetApp_AIQ_Advisor.py`.
- **ARIA branding aligned** — `launcher.py`, `Start-Dashboard.ps1`, and `start_dashboard.bat` now use "ARIA — Active IQ Risk Intelligence Advisor" instead of legacy "NetApp Active IQ TAM Dashboard" / "NetApp Active IQ Advisor" names.
- **CHANGELOG.md** — added missing version header for the enrichment engine features that were previously listed between v3.8.2 and v3.7.0 without a release number.
- **`bump_version.ps1` limitation documented** — the script only updates `version.json`, `app.js`, and `CHANGELOG.md`, leaving HTML footers, installer scripts, and `CONTEXT.md` at stale versions.

---

## [3.8.2] - 2026-07-31

### Fixed
- **Efficiency metrics restored** — removed `... on ESeriesSystem` inline fragment from FULL and EFFICIENCY tier GQL queries. The ActiveIQ GraphQL schema does not support the `ESeriesSystem` type, causing a `GRAPHQL_VALIDATION_FAILED` error that silently degraded both query tiers. The harvest fell through to the MINIMAL tier, which contains no capacity or efficiency data — resulting in all data reduction ratios, savings, and donut chart segments showing as null/0.
- **Snapshot-excluded data reduction** — the dashboard now correctly surfaces `dataReductionRatio` (dedupe + compression only, excluding snapshots) from `ONTAPSystemEfficiency.ratio.dataReductionRatio`. Previously this field was always null due to the GQL schema failure above.
- **Snapshot-excluded capacity fields** — added `usedWithoutSnapshotsKiB` and `usedWithoutSnapshotsClonesKiB` to the GQL queries and harvest extraction. These populate `physicalUsedNoSnapsTB` and `logicalUsedNoSnapsTB` as fallback ratio sources when the primary API fields are null.

### Changed
- **Ratio fallback cascade** in `enrichSystemTelemetry()` now uses 3 snapshot-free sources before showing N/A: (1) `dataReductionRatioSys`, (2) `dedupSavedKiB + compactionSavedKiB`, (3) `logNoSnaps / physNoSnaps`. The old `logical/physical` fallback (which included snapshot inflation at 38:1+) has been removed.
- **README.md** — expanded Efficiency Calculation section with fallback cascade documentation and GQL schema notes.
- **version.json** — bumped to 3.8.2.

---

## [3.8.0] - 2026-07-28

### Added
- **Enhanced Enrichment Engine** — 7-source external intelligence pipeline that scrapes NetApp KB articles, upgrade path documentation, and best practice TR guides alongside the existing release notes, PSIRT advisories, NVD CVEs, and Bugs Online sources. All data persistently cached in SQLite (`enrich_cache`) with 7-day TTL and automatic refresh during each harvest cycle.
- **Version Catalog Auto-Detection** — scrapes docs.netapp.com release notes pages during enrichment to discover newly released ONTAP, StorageGRID, and SANtricity versions. The client-side `SOFTWARE_VERSION_DATABASES` is updated dynamically on each page load via the new `/api/enrich/versions` endpoint — upgrade path calculator and latest-version recommendations update automatically without code changes.
- **KB Articles & Remediation section** (teal) in Version Intel card — shows matching Knowledge Base articles from kb.netapp.com with inline remediation steps and direct links to full articles.
- **Upgrade Path Advisor section** (cyan) in Version Intel card — displays recommended upgrade target, direct vs. multi-hop badge, prerequisites, version-specific notes, and link to the official upgrade guide.
- **Best Practice Guides section** (indigo) in Version Intel card — lists relevant NetApp Technical Reports (TRs) for security hardening, performance tuning, and feature best practices with clickable links.

### Changed
- `SOFTWARE_VERSION_DATABASES` changed from `const` to `let` to allow dynamic updates from server-side version catalog scraping.
- `server.py` — added `fetch_kb_articles()`, `fetch_upgrade_path_info()`, `fetch_best_practice_guides()`, `fetch_latest_version_catalog()` fetcher functions; integrated into all three version enrichment pipelines (ONTAP, StorageGRID, SANtricity); added `/api/enrich/versions` endpoint; added catalog refresh to `_enrich_all_versions()` background thread.
- `app.js` — expanded `injectVersionEnrichment()` with 3 new UI sections; added version catalog sync to `syncFromServer()`; updated "no findings" check to include new data types.
- Updated `README.md` version badge and feature comparison table.
- Updated `CONTEXT.md` with new data sources, enrichment pipeline documentation, file sizes, and version history.

---

## [3.7.0] - 2026-07-20

### Added
- **ASUP Offline Import** — import AutoSupport bundles (`.7z`, `.tgz`, `.zip`, `.xml`, `.gz`) onsite when Active IQ is unreachable. Supported platforms: ONTAP, StorageGRID, and E-Series.
- **ARIA normalized schema** — parsed ASUP bundles are converted into the same internal schema used by live API data, enabling full Reference Library enrichment (CVE matching, EOA detection, upgrade path analysis, 15-point readiness) from bundle data alone.
- **Import Coverage Report** — post-import summary showing what was parseable vs. what requires live API access.
- **Association Panel** — link imported ASUP bundles to existing customers and sites, with optional notes.
- **Graceful degradation** — partial or truncated bundles are handled with best-effort parsing and clear coverage gaps.
- **SQLite persistence** — imported ASUP data is persisted in `aiq_cache.db` across sessions.
- **ASUP Import Modal** — full drag-and-drop UI with progress bar, match banner, and import history.

### Changed
- `asup_parser.py` — comprehensive bundle parser supporting `.7z` (via `py7zr` or system `7z`), `.tgz`, `.zip`, `.xml.gz`, and `.xml` formats.
- `server.py` — added `/api/asup/import`, `/api/asup/list`, `/api/asup/associate`, `/api/asup/delete` endpoints.
- `index_src.html` — added inline ASUP Import Modal DOM and enhanced error handling.

---


## [3.6.3] - 2026-07-19

### Fixed / Performance
- **Expand All UI lockup** — replaced the synchronous inline IIFE on the "Expand All" button with a named `_expandAllUpgradeCards` function. Detail bodies are now rendered in async batches of 5 using `setTimeout(0)` yields between each chunk, keeping the UI responsive even for large system lists. Collapse remains synchronous/instant.
- **Button state feedback** — button is disabled and shows "Rendering…" while the async pass runs, then flips to "⊖ Collapse All" when complete.

---

## [3.6.0] - 2026-07-19

### Added
- **What's New startup modal** — version-gated popup on first load after each release; shows changelog sections with per-category icons, hop details, "Got it" / Dismiss, "Don't show again" checkbox, and previous-release collapse accordion.
- **Collapsible OS upgrade cards** — Recommended OS Upgrades section now renders each system as a compact collapsed card (system name, urgency badge, version range, hop pills). Full procedure/pre-upgrade/considerations detail expands on click. Global Expand All / Collapse All toggle added.

### Fixed / Performance
- **TAM tab browser hang** — split render fingerprint into two stamps: _tamTableFP (triggers heavy table rebuild) and _tamVisFP (triggers visualizer/header only). Clicking between node tabs no longer re-renders risks/upgrades/switches/bulletins tables.
- **Inline onmouseover/onmouseout removed** from all risk rows and upgrade card headers — replaced with injected CSS classes (.tam-risk-sys-hdr:hover, .tam-risk-detail-row:hover, .tam-upgrade-hdr:hover). Eliminates continuous style recalculation on mouse movement.
- **Visualizer/SVM/E-Series renders guarded** — only fire when the active node serial or selection set changes, not on every keypress or auto-sync tick.

---

## [3.5.0] - 2026-07-19

### Added
- **APP_CHANGELOG constant** — versioned changelog data structure in pp.js for driving the What's New modal.
- **checkAndShowChangelog()** — version gate that fires 600ms after load; reads iq_seen_version from localStorage.
- **showWhatsNewModal()** — full-featured animated modal with previous-release accordion, "Got it" + "Don't show again" controls, ESC/backdrop dismissal, and window.showWhatsNew helper for manual re-open.

### Fixed
- NETAPP_SECURITY_BULLETIN_DB array syntax error (missing comma) causing SyntaxError: Unexpected token '{'.

---
## [3.3.1] - 2026-07-12

### Fixed — UI Rendering

#### Recommendation Cards — SHELF_FIRMWARE Mis-positioned
- **Root cause:** `linkify()` and `rescopeText()` inject HTML `<a>`/`<strong>` tags into recommendation text. The previous code applied `.substring(0, 500)` *after* those transforms, meaning a long advisory (e.g. SP_BMC) could be truncated mid-tag — e.g. cutting inside `<a href="https://...">`). The browser auto-closed the `<p>` element and left the dangling open `<a>` tag in scope, causing the **next card's `<div>` to be parsed as a child of the previous card** rather than a sibling. SHELF_FIRMWARE visually appeared inline inside the SP_BMC block.
- **Fix:** Truncation now applies to the **raw plain text** (`r.recommendation`) at 497 chars before any HTML transformation. `linkify()` and `rescopeText()` are then applied to the already-safe excerpt, guaranteeing no tag is ever cut mid-open.

#### Performance Optimisation — Risk Table & Bulletin Section
- **Risk table grouped by system:** Initial DOM now scales with number of systems (*N*) not total risks (*N × M*). Each system renders as a single collapsible summary row (severity pills: Critical / High / Med / Low counts). Click to expand per-risk drilldown. Systems sorted Critical-first, then alphabetically.
- **Expand All / Collapse All** button added to the risk table controls bar.
- **Bulletin severity tiers:** Critical + High advisories always rendered immediately. Medium / Low / Informational advisories collapsed behind a single click-to-expand row, reducing initial DOM and CVE fetch burst.
- **Batched CVE enrichment:** NVD API calls moved from a synchronous burst-of-N to a 5-per-100ms `setTimeout` queue. Primary (visible) rows enriched 80ms after paint; secondary (hidden) rows enriched lazily on first expansion, clearing the queue after one run.

### Added — Toggle Helper Functions
- **`toggleRiskGroup(groupId, headerRow)`** — per-system chevron drilldown with animated 90° rotation.
- **`toggleAllRiskGroups(btn)`** — expands/collapses all system groups in a single click.
- **`toggleBulletinSecondary(btn)`** — reveals collapsed Medium/Low/Info bulletin tier; fires deferred CVE enrichment queue on first open only.

---

## [3.6.2] - 2026-07-19

### Fixed
- Fix hop display logic: direct upgrades now correctly labelled as Direct (not Hop 1); multi-hop shows N-of-total counter and Final target badge; removed orphaned dead code

---
## [3.6.1] - 2026-07-19

### Fixed
- Fix upgrade card expand lockup — lazy-render hop detail HTML on first click only (data-loaded guard), add missing _toggleUpgradeCard and _renderUpgradeDetail functions

---
## [3.3.0] - 2026-07-11

### Added — Security Intelligence Engine (Major)

#### Multi-Source CVE Harvest
- **77 advisory entries covering 82 unique CVEs** ingested into `NETAPP_SECURITY_BULLETIN_DB` in `app.js` *(count at v3.3.0 release — the database grows with each Reference Library sync)*
- Sources scraped and cross-referenced:
  - `security.netapp.com` (NetApp PSIRT) — all NTAP-YYYYMMDD-XXXX advisories 2024–2026
  - **MITRE CVE** — NetApp ONTAP / StorageGRID / Trident keyword search
  - **NVD / NIST CVE API** — `keywordSearch=netapp+ontap` endpoint + web extraction
  - **CISA Known Exploited Vulnerabilities (KEV)** catalog — 2 NetApp-related entries confirmed at time of release *(KEV-flagged entries are re-evaluated on each sync)*
  - **GitHub Security Advisories** — Trident/Astra Trident Golang dependency CVEs
  - **NetApp KB** — operational bugs (CONTAP-xxxxxx IDs, upgrade-triggered instabilities)
  - **Tenable, SentinelOne, Eclypsium, CIRCL** — threat intelligence cross-reference

#### CISA KEV — Actively Exploited (confirmed at v3.3.0 release)
- **CVE-2024-54085** (CVSS 10.0) — AMI MegaRAC SPx BMC authentication bypass via HTTP header spoofing. Grants full unauthenticated BMC control on StorageGRID SG6160, SGF6112, SG110, SG1100. Added to CISA KEV June 25, 2025. PoC exists. Unaffected models: SG6060, SGF6024, SG100, SG1000.
- **CVE-2024-38475** (CVSS 9.1) — Apache HTTP Server mod_rewrite URL mapping flaw allowing source code disclosure and RCE. Added to CISA KEV 2024. Fixed in ONTAP 9.12.1P16 / 9.13.1P14 / 9.14.1P8 / 9.15.1P3 / 9.16.1.

#### New Critical CVEs (CVSS ≥ 9.0)
- **CVE-2024-43102** (CVSS 10.0) — FreeBSD UMTX Use-After-Free, kernel privilege escalation. All ONTAP 9. Advisory NTAP-20240916-0001.
- **CVE-2025-26512** (CVSS 9.9) — SnapCenter improper access control, low-priv user → remote admin on any SnapCenter plug-in host. Fix: SC 6.0.1P1 / 6.1P1.
- **CVE-2025-6965** (CVSS 9.8) — SQLite integer overflow in SnapCenter Server. Fix: SQLite 3.50.2+.
- **CVE-2025-15467** (CVSS 9.8) — OpenSSL stack buffer overflow in CMS AuthEnvelopedData. Affects ONTAP 9.18.1 only.
- **CVE-2026-27143** (CVSS 9.8) — Golang compiler integer overflow/underflow. Affects Trident / ONTAP tools. Fix: Go 1.25.9+.
- **CVE-2024-11236** (CVSS 9.8) — PHP ldap_escape buffer overflow on 32-bit. Fix: PHP 8.1.30+/8.2.24+.
- **CVE-2024-45337** (CVSS 9.1) — Golang x/crypto SSH auth bypass. Affects Trident.
- **CVE-2024-47685** (CVSS 9.1) — Linux kernel vulnerability. StorageGRID hotfix 11.9.0.7 required.
- **CVE-2025-4517** (CVSS 9.4) — Python tarfile path traversal. Affects all products bundling Python.

#### New High CVEs (CVSS 7.0–8.9) — 20+ entries including
- CVE-2026-27140 (CVSS 8.8) — Golang stdlib memory corruption, Trident/ONTAP tools
- CVE-2024-21989 (CVSS 8.1) — ONTAP Select Deploy read-only privilege escalation
- CVE-2024-38473 (CVSS 8.1) — Apache mod_proxy auth bypass (same advisory as CVE-2024-38475)
- CVE-2025-0411 (CVSS 7.0) — 7-Zip MoTW bypass in Active IQ Unified Manager
- CVE-2024-0760 (CVSS 7.5) — ISC BIND DNS flood DoS, ONTAP 9.14.1+ DNS LB configs
- CVE-2024-2511 (CVSS 7.5) — OpenSSL TLSv1.3 unbounded memory growth DoS
- CVE-2024-2398 (CVSS 7.5) — libcurl HTTP/2 server push memory leak
- CVE-2024-22025 (CVSS 7.5) — Node.js DoS, Active IQ Unified Manager / ONTAP tools
- CVE-2024-55549 (CVSS 7.8) — libxslt use-after-free, ONTAP / multiple products
- CVE-2026-24051 (CVSS 7.8) — Astra Trident PATH hijacking. Fix: Trident v26.02+

#### Enrichment Wiring
- **`getApplicableSecurityBulletins(ontapVersion, platformType)`** — version-aware DB matcher wired into `enrichSystemTelemetry()`. Performs ONTAP version string comparison (branch + patch-level) against all 77 DB entries
- **Three-way merge in `enrichSystemTelemetry()`** — API-provided bulletins, risk-extracted CVE IDs, and DB-matched advisories are merged and deduplicated by CVE ID using a `Set`. Result is sorted Critical → High → Medium → Low.
- **Enriched bulletin schema** — all bulletins now carry: `id`, `ntapId`, `cve`, `cvss`, `title`, `category`, `severity`, `status`, `mitigation`, `fixedIn`, `published`, `link`, `source` (`api` / `risk` / `db`)
- **`securityBulletins` now always populated for live systems** — previously only auto-generated when API returned zero bulletins; now additive so DB entries always appear alongside API data
- **Daily re-scrape cron** — scheduled at 08:00 to trigger reference library re-sync

### Fixed
- **Version String Comparison Bug (Critical)** — Replaced direct string comparisons (e.g. `s.osVersion >= s.swRecMin`) with the robust numeric `versionLt` helper in `app.js` across 5 filter lines. This resolves a bug where newer versions like 9.10+ were sorted alphabetically as smaller than 9.9.x baselines, miscalculating node firmware currency.
- **PyInstaller spec UnicodeEscape Error** — Converted `AIQscraper.spec` docstring to a raw string (`r"""..."""`) to fix a SyntaxError caused by backslashes inside path names (e.g., `\N`).

### Changed
- **SnapCenter version database** — Appended `"6.2.2"` to `SOFTWARE_VERSION_DATABASES.snapcenter` after synchronizing updates from the daily reference library scan.
- **CHANGELOG / README** — updated to reflect v3.3.0 security intelligence milestone.
- **Badge version** — bumped to 3.3.0.

---

## [3.2.0] - 2026-07-11


### Fixed — Storage Efficiency (Critical)
- **Efficiency ratio inflated by snapshot savings** — Server was referencing `_eff_ratio`, `_data_red`, `_dedup_kib`, `_compact_kib` without ever assigning them. All efficiency variables now correctly parsed from `ONTAPSystemEfficiency.ratio` and `.saved` GQL response objects
- **Switched from `efficiencyRatio` to `dataReductionRatio`** — Primary displayed ratio is now dedupe + compression only (no snapshot savings), matching how Active IQ presents data reduction. The snapshot-inclusive ratio is retained and shown as a secondary annotation ("incl. snapshots: X.X:1")
- **Space saved now uses `deDuplicationSavedKiB + compactionSavedKiB`** — Previously used `savedKiB` (total, including snapshot space). Now correctly shows data reduction savings only

### Fixed — Per-Node Capacity Breakdown (Critical)
- **Used TB and Utilisation showed 0.0 for all nodes** — The API reports capacity at cluster-aggregate level for cluster nodes; `clusterPhysicalUsedTB` was 0. Fallback chain now: `clusterPhysicalUsedTB` → `efficiency.physicalUsedTB` → last `historicalCapacityMonths` entry (same source the projection chart uses)
- **Utilisation % fallback** — Now uses `clusterCapacityUtilPct` (direct API value) first, then computes from raw/used, then from usable capacity
- **Raw TB shows N/A** where the API only reports cluster-aggregate (rather than showing 0.0 which was misleading)
- **Sort order fixed** — Per-node table now sorts by effective used TB descending

### Fixed — DOM Structure Bug
- **Strategic Capability Adoption Checklist not rendering** — Double `</div>` on one line in `index_src.html` broke DOM nesting; the checklist card was outside its tab container and not visible

### Changed — Documentation
- **README completely rewritten** — New structure leads with use cases, deliverables, and user guide. "Why this tool vs. Active IQ directly" section added with side-by-side comparison. Internal architecture moved to Section 10 as an addendum

---

## [3.1.0] - 2026-07-10


### Added — NetApp Reference Library Enrichment Engine
- **EOA Platform Flagging** — Automatic detection of systems running End-of-Availability hardware. Complete EOA list from docs.netapp.com (AFF A200/A220/A300/A320/A700/A700s/C190/C800, ASA C250/C400/C800, FAS2600/FAS500f/FAS8200/FAS9000) plus EOA switches (BES-53248, Cisco 9336C-FX2, NVIDIA SN2100)
- **CVE/Security Advisory Database** — initial 7 tracked CVEs with version-range matching added at v3.1.0 (CVE-2026-22050 ONTAP snapshot lock bypass, CVE-2026-22052 S3 NAS info disclosure, CVE-2026-20833 Kerberos AES enforcement, CVE-2026-22054 Config Advisor hard-coded creds, CVE-2025-26512 SnapCenter privilege escalation CVSS 9.9, CVE-2026-22051 StorageGRID metrics disclosure, CVE-2026-24051 Trident PATH hijacking). *The database has since grown significantly via subsequent Reference Library syncs.*
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