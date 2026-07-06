# NetApp Active IQ Account Report Dashboard

[![Version](https://img.shields.io/badge/version-1.1.0-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A zero-dependency, browser-based report builder and dashboard tailored for NetApp Support Account Managers (SAM), Technical Account Managers (TAM), and Customer Success Managers (CSM).

This tool runs **entirely inside your browser** (as a static webpage) from this local folder. It does not require any backend server, Node.js/Python installations, or database engines. It connects directly to the Active IQ Digital Advisor APIs (`activeiq.netapp.com`) and persists credentials in your browser's private local storage.

---

## What the Tool Does

This dashboard consolidates telemetry data from the public Active IQ API to help account teams prepare customer reviews, identify system issues, and optimize installations.

*   **TAM Module (Technical Compliance)**: Lists active predictive risks (e.g., single-path storage failures, outdated shelf firmware) with official NetApp KB remediation links and target version upgrade recommendations. Includes interactive **Remediation Action Plans** displaying root cause, impact, step-by-step commands, and trade-off options.
*   **SAM Module (Support Operations)**: Tracks contract/warranty expiration thresholds (30/60/90 days), flags hardware End-of-Support (EOS/EOA) dates, and displays unresolved NetApp Field Actions (FA). Includes **3rd-Party Hypervisor Integration** compliance checks.
*   **CSM Module (ROI & Adoption)**: Showcases storage efficiencies (deduplication ratios, space saved), FabricPool cloud capacity tiering savings, SnapMirror active disaster recovery replication status, and a capability adoption scorecard.
*   **Unified Account Overview**: Search/filter by customer, cluster, system, or serial number. Aggregates data across the install base and supports one-click CSV report exports.

---

## Supported Platforms & Technologies

This reporting tool is aligned to retrieve and map telemetry across the complete NetApp product portfolio:
*   **ONTAP (FAS & AFF Systems)**: On-premises primary flash storage.
*   **Cloud Volumes ONTAP (CVO)**: Software-defined storage deployed in AWS, Azure, or GCP.
*   **StorageGRID**: Webscale S3/Swift object storage.
*   **MetroCluster IP/FC**: High-availability synchronous multi-site disaster recovery configurations.
*   **SnapMirror & SyncMirror**: Asynchronous and synchronous remote data replication paths.

### 3rd-Party Platform & Hypervisor Best Practices
The tool highlights compliance warnings against NetApp storage best practices for virtualization hosts and orchestrators:
*   **VMware vSphere / ESXi**:
    *   *Multipathing*: Verifies that Native Multipathing (NMP) Path Selection Policy (PSP) is configured to **Round Robin (VMW_PSP_RR)** instead of default Fixed/MRU, and that the IOPS limit is modified to `1` (via `esxcli storage nmp psp roundrobin device config set -I 1 -t iops`) to balance controller load and prevent latency warnings.
    *   *Integration Plugins*: Audits connectivity and credentials for **VASA Provider** and **ONTAP Tools for VMware (OTV)** for VVol and datastore provisioning.
*   **Kubernetes (Astra Trident)**:
    *   *Driver Versioning*: Flags outdated Astra Trident CSI drivers backing Kubernetes Persistent Volumes (PVs) that mismatch host API versions.
*   **Cloud Providers (AWS / Azure / GCP)**:
    *   *VPC Endpoints*: Tracks network latency timeouts between CVO nodes and backing S3/Blob storage, recommending private VPC endpoints to reduce cloud data routing costs.

---

## Indemnity & License Agreement

This tool is distributed under the **MIT License**. 

> [!IMPORTANT]
> **Operational Responsibility & Indemnity Disclaimer:**
> This is an unofficial utility script. Users are solely responsible for verifying the accuracy of the risks, field actions, contract states, and ONTAP upgrade targets in this dashboard before scheduling maintenance or making configuration changes to production clusters. The developers and contributors of this tool assume no liability for system downtime, data corruption, or service disruptions.
> 
> For full details, see the [LICENSE](LICENSE) file.

### Strict Read-Only Design
This dashboard is designed to be **strictly read-only** under all circumstances. It retrieves read-only telemetry data using HTTP `GET` requests. It contains no forms, endpoints, scripts, or interfaces that can execute mutating requests (`POST` for configuration, `PUT`, `PATCH`, or `DELETE`) against the Active IQ portal or any customer storage systems. The only `POST` call in the application is strictly for the initial authentication token swap.

---

## Instructions

### 1. Launch the Application
Simply double-click the **`index.html`** file in this directory to open the dashboard in your default web browser (Chrome, Edge, or Firefox).

### 2. Testing with Demo Data (Offline Mode)
To see how the dashboard functions immediately with CVO, StorageGRID, MetroCluster, SnapMirror, and VMware integration metrics:
1. Open the dashboard.
2. Click the **Settings & Config** tab in the sidebar.
3. Turn on the **Enable Offline Demo Mode (Mock Data)** toggle.
4. Go back to the **Overview Dashboard** to inspect system reports, charts, and metrics. Click on any system row, go to **TAM Technical Audit**, and click **Remediation Plan** on a risk to see the detailed action plan.

### 3. Setting Up Production API Credentials
To view your own live customer accounts and clusters:
1. Open your browser and log in to [activeiq.netapp.com](https://activeiq.netapp.com/) using your NetApp Support Site (NSS) credentials.
2. In the top navigation bar, click the **Quick Links** icon and select **API Services**.
3. Under the API Services tab, click **Generate Token**.
4. Copy the long **Refresh Token** shown on screen.
5. In your local dashboard application, navigate to the **Settings & Config** tab.
6. Disable **Offline Demo Mode**, paste the token into the **Refresh Token** input box, and click **Save Configuration**.

---

## Bypassing Browser CORS Checks

Because the page is loaded directly as a local file (`file:///.../index.html`), browser security rules (CORS) may block direct JavaScript `fetch` calls to the public Active IQ API domain. 

If you encounter connection errors when trying to connect to the live API, choose one of these options:

### Option A: Use a Developer Browser Extension (Easiest)
Install a standard, browser-approved developer extension that toggles CORS headers for local files:
* **Chrome**: Search the Chrome Web Store for **"CORS Unblock"** or **"Allow CORS"** and enable it.
* **Firefox/Edge**: Search their respective add-on stores for **"CORS Bypass"** or **"CORS Access Control"**.

### Option B: Launch Chrome with Web Security Disabled
Create a temporary browser instance that relaxes cross-origin limitations for local testing:
* **Windows (PowerShell/Run CMD)**:
  ```cmd
  chrome.exe --disable-web-security --user-data-dir="C:/temp_chrome_dev"
  ```
* **macOS (Terminal)**:
  ```bash
  open -n -a "Google Chrome" --args --user-data-dir="/tmp/temp_chrome_dev" --disable-web-security
  ```

### Option C: Serve via a Simple Local Web Server
If your security policies prevent browser modifications, serve the files from a local port rather than `file://`:
* If you have Python installed, open your command prompt/terminal in this folder and run:
  ```bash
  python -m http.server 8080
  ```
* Open your browser and navigate to `http://localhost:8080` to access the app with standard local origin permissions.

---

## Change History
See the [CHANGELOG.md](CHANGELOG.md) for version release details.
