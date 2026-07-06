// Active IQ Web Client - Core Application Logic
//
// NOTE ON READ-ONLY DESIGN SAFETY:
// This tool is designed to be strictly READ-ONLY. Under no circumstances should
// this application perform mutating actions (POST, PUT, PATCH, DELETE) against 
// any Active IQ data configurations, customer assets, or cluster parameters.
// The single POST request made in this app is strictly for token authentication
// exchange (refreshing NSS tokens) and does not perform any data modifications.
//

const API_BASE = "https://api.activeiq.netapp.com/v1";

// 1. Mock Data Definitions (Aligned with ONTAP, StorageGRID, CVO, MetroCluster, SnapMirror, Hypervisors)
const MOCK_SYSTEMS = [
  {
    serialNumber: "622001234567",
    systemName: "netapp-aff-01",
    clusterName: "NY-AFF-CLUSTER",
    customerName: "Global Bank Corp",
    ontapVersion: "9.12.1P4",
    platform: "AFF A400 (On-Prem)",
    status: "warning",
    risks: [
      {
        id: 101,
        severity: "high",
        category: "Hardware",
        description: "Single Controller Path Failure detected on SAS loop 1.",
        recommendation: "Inspect SAS cable connections on shelf 2, port 1B. Refer to KB1089201.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/Single_controller_path_errors",
        remediationPlan: {
          cause: "Signal degradation or physical disconnection on controller SAS port 1b connected to Shelf 2 Module B.",
          impact: "Loss of SAS path redundancy. A secondary failure on SAS port 1a will cause a complete shelf outage, leading to Data Unavailable (DU) status for all aggregates on Shelf 2.",
          steps: [
            "1. SSH into the NY-AFF-CLUSTER-01 node controller CLI.",
            "2. Run: 'storage show path' to view disk path map and confirm the offline controller port.",
            "3. Locate Shelf 2 at the rack. Verify the status LED on the SAS connector at port 1B (Module B).",
            "4. Gently reseat the SAS cable. If the LED remains amber or off, replace the SAS cable (Part: 112-00234) under active warranty.",
            "5. Run: 'storage show path -fields disk-count,path-link-status' to confirm all disk drives report dual-path status."
          ],
          options: [
            "Option A (Online): Reseat/replace SAS cable online (non-disruptive). ONTAP multipathing protects data availability via the active path.",
            "Option B (Schedule Maintenance): If IOM shelf controller module replacement is required, schedule a maintenance window. Although hot-swappable, doing it off-peak minimizes IO latency risks."
          ],
          thirdParty: "No direct hypervisor impacts. However, VMware ESXi storage paths might generate temporary ScsiDeviceIO path failure alerts which can be ignored during hot-swap."
        }
      },
      {
        id: 102,
        severity: "medium",
        category: "Software",
        description: "Disk Shelf IOM12 firmware is outdated (current: 0240, target: 0260).",
        recommendation: "Schedule a non-disruptive shelf firmware upgrade using ONTAP System Manager.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/Disk_Shelves_and_Storage_Storage_Media/How_to_update_shelf_firmware",
        remediationPlan: {
          cause: "Older firmware baseline (v0240) lacks optimization for SAS signal margins under heavy loads.",
          impact: "Increased risk of soft SAS path resets and packet retries under high transactional workloads.",
          steps: [
            "1. Download the IOM12 firmware bundle (version 0260) from the NetApp Support Site.",
            "2. Upload the bundle to the ONTAP cluster. Run CLI command: 'storage firmware download -node * -package iom12_0260.web'.",
            "3. Monitor progress: 'storage firmware show -package iom12'. The update installs background/non-disruptively, updating one module (A or B) at a time."
          ],
          options: [
            "Option A: Automated update via NetApp Active IQ Unified Manager (AIQUM) or System Manager GUI.",
            "Option B: Manual CLI update. Requires downloading and staging files locally on cluster web servers."
          ],
          thirdParty: "Ensure vSphere Host storage queue depths are configured correctly to absorb transient IO delays (less than 2 seconds) during module reboots."
        }
      }
    ],
    upgrades: {
      targetVersion: "9.13.1P8",
      urgency: "Recommended",
      benefits: "Provides critical patches for MetroCluster IP stability and snapmirror engine multi-stream optimizations."
    },
    contracts: {
      status: "warning",
      endDate: "2026-08-01",
      daysRemaining: 26,
      supportLevel: "SupportEdge Premium 4hr"
    },
    lifecycle: {
      eoaDate: "2025-06-30",
      eosDate: "2030-06-30",
      isNearEos: false
    },
    fieldActions: [
      {
        id: "FA-2026-04",
        title: "SAS Cable Signal Degradation alert on specific serial range",
        actionRequired: "Replace affected SAS cable (Part: 112-00234) during next maintenance window."
      }
    ],
    efficiency: {
      ratio: "4.2:1",
      logicalUsedTB: 120.5,
      physicalUsedTB: 28.7,
      spaceSavedTB: 91.8,
      fabricPoolTieredTB: 12.4
    },
    snapmirror: {
      enabled: true,
      relationships: [
        {
          destination: "netapp-cvo-aws (CVO)",
          type: "XDP (Asynchronous)",
          schedule: "hourly",
          status: "Mirrored",
          state: "Snapmirrored",
          lagTime: "42 mins",
          healthy: true
        }
      ]
    },
    hypervisors: [
      {
        type: "VMware vSphere",
        version: "ESXi 8.0 Update 2",
        plugin: "VASA Provider 10.1 (Active)",
        multipathing: "VMW_PSP_RR (Round Robin)",
        health: "Normal"
      }
    ]
  },
  {
    serialNumber: "622002223333",
    systemName: "netapp-cvo-aws",
    clusterName: "AWS-CVO-CLUSTER",
    customerName: "Global Bank Corp",
    ontapVersion: "9.14.1P3",
    platform: "Cloud Volumes ONTAP (AWS)",
    status: "warning",
    risks: [
      {
        id: 201,
        severity: "high",
        category: "Integration",
        description: "Kubernetes Astra Trident driver (v23.04) is outdated and unsupported.",
        recommendation: "Upgrade Astra Trident driver to v24.02 for full ONTAP 9.14 API support.",
        kbLink: "https://docs.netapp.com/us-en/trident/trident-get-started/requirements.html",
        remediationPlan: {
          cause: "Kubernetes cluster upgraded to v1.28 while Astra Trident version remains at v23.04. API deprecations break storage provisioning.",
          impact: "Inability to dynamically provision new Persistent Volumes (PV) for container workloads. Existing PVs remain mounted but configuration edits fail.",
          steps: [
            "1. Backup active Trident state: 'tridentctl get backend -n trident'.",
            "2. Download the Trident installer bundle v24.02.",
            "3. Run the installer upgrade command: 'tridentctl upgrade -n trident --to-image netapp/trident:24.02.0'.",
            "4. Verify Pod status: 'kubectl get pods -n trident' and verify all pods are running version 24.02.0."
          ],
          options: [
            "Option A (Helm Upgrade - Recommended): Use Helm package manager: 'helm upgrade trident netapp-trident/trident-operator --version 24.02.0'.",
            "Option B (Operator Upgrade): Apply the updated Trident Operator manifests manually."
          ],
          thirdParty: "Compatible with Kubernetes v1.26 through v1.29. Ensure downstream apps are prepared for dynamic PV mounts."
        }
      },
      {
        id: 202,
        severity: "medium",
        category: "Cloud",
        description: "Atheros AWS S3 capacity tiering bucket reports connection timeouts.",
        recommendation: "Verify VPC endpoint routing for AWS S3. Refer to NetApp Cloud Manager guide.",
        kbLink: "https://kb.netapp.com/Cloud/Cloud_Volumes_ONTAP/FabricPool_S3_connection_troubleshooting",
        remediationPlan: {
          cause: "Security Group policy changes in the AWS VPC restricted outbound HTTPS access on Port 443 to S3 IP ranges.",
          impact: "FabricPool tiering stops. Cold data remains on EBS root volumes, causing storage capacity overflow on premium cloud volumes.",
          steps: [
            "1. Log in to the AWS Management Console.",
            "2. Navigate to VPC -> Security Groups. Select CVO Node Security Group.",
            "3. Verify Outbound Rules. Ensure outbound HTTPS (Port 443) to S3 Gateway Endpoint is allowed.",
            "4. From ONTAP CLI, run: 'storage aggregate object-store profile show' to verify object-store endpoint connectivity."
          ],
          options: [
            "Option A: Implement AWS VPC Endpoint (Gateway) for S3. This routes traffic internally inside AWS and bypasses external gateway constraints.",
            "Option B: Open NAT Gateway outbound routing if VPC endpoints are not desired in the subnet."
          ],
          thirdParty: "Affects CVO nodes running inside AWS subnets. No physical hypervisor dependencies."
        }
      }
    ],
    upgrades: {
      targetVersion: "9.14.1P5",
      urgency: "Recommended",
      benefits: "Fixes AWS EBS block allocation bugs and optimizes cloud tiering latency performance."
    },
    contracts: {
      status: "normal",
      endDate: "2027-12-15",
      daysRemaining: 527,
      supportLevel: "Cloud Volumes Premium BYOL"
    },
    lifecycle: {
      eoaDate: "2027-12-31",
      eosDate: "2032-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "3.5:1",
      logicalUsedTB: 250.0,
      physicalUsedTB: 71.4,
      spaceSavedTB: 178.6,
      fabricPoolTieredTB: 48.0
    },
    snapmirror: {
      enabled: true,
      relationships: [
        {
          destination: "NY-AFF-CLUSTER (On-Prem)",
          type: "XDP (Asynchronous)",
          schedule: "daily",
          status: "Mirrored",
          state: "Snapmirrored",
          lagTime: "12 hours",
          healthy: true
        }
      ]
    },
    hypervisors: [
      {
        type: "Kubernetes (EKS)",
        version: "v1.28",
        plugin: "Astra Trident 23.04 (Outdated)",
        multipathing: "AWS EBS Multipath NVMe",
        health: "Warning"
      }
    ]
  },
  {
    serialNumber: "622003334444",
    systemName: "netapp-grid-01",
    clusterName: "SGRID-SG6060",
    customerName: "Global Bank Corp",
    ontapVersion: "11.8.0",
    platform: "StorageGRID Webscale (Object)",
    status: "critical",
    risks: [
      {
        id: 301,
        severity: "critical",
        category: "Security",
        description: "Management Interface SSL Certificate expires in 12 days.",
        recommendation: "Renew SSL certificate in StorageGRID Grid Manager. Refer to admin guidelines.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/StorageGRID/How_to_renew_StorageGRID_SSL_certificates",
        remediationPlan: {
          cause: "The user-installed custom certificate authority cert for StorageGRID Management Console (port 9443) is expiring.",
          impact: "Complete loss of S3/Swift client connections using TLS. API calls from backup programs, applications, and dashboards fail due to untrusted certificates.",
          steps: [
            "1. Generate a new Certificate Signing Request (CSR) in Grid Manager: Configuration -> Security -> Certificates.",
            "2. Obtain signing approval from your enterprise CA.",
            "3. Navigate to StorageGRID Grid Manager. Upload the new signed certificate (.PEM format) and private key.",
            "4. Verify client connection using curl: 'curl -v https://<storagegrid-endpoint>:9443/' and confirm the new expiry date."
          ],
          options: [
            "Option A: Upload custom CA certificate. Recommended for enterprise compliance.",
            "Option B: Regenerate default StorageGRID Self-Signed Certificate. Quick resolution but generates browser warnings."
          ],
          thirdParty: "Affects external S3 clients (Veeam, Commvault, Astra Control, AWS SDKs) making HTTPS S3 connections."
        }
      },
      {
        id: 302,
        severity: "high",
        category: "Hardware",
        description: "Grid storage node SG6060 Fan Module 2 reports RPM below critical threshold.",
        recommendation: "Replace Fan Module assembly (Part: 112-00445) immediately.",
        kbLink: "https://docs.netapp.com/us-en/storagegrid-appliances/sg6000/replacing-fan-in-sg6000-cn.html",
        remediationPlan: {
          cause: "Physical bearing failure in Fan Module 2 of the compute controller chassis.",
          impact: "Chassis temperature increases. If chassis temp exceeds 45°C, controller CPU throttles speed by 50%, degrading grid write speeds.",
          steps: [
            "1. Locate the SG6000 compute controller in the server rack. Check rear blue Identify LED.",
            "2. Access Grid Manager console. Verify which fan module reported failure (Fan 2).",
            "3. Pull fan module out of the slot (hot-swappable).",
            "4. Insert new fan assembly module (Part: 112-00445). Confirm Green status LED is lit.",
            "5. Verify RPM status reports normal in Grid Manager status tree."
          ],
          options: [
            "Option A: Hot-Swap replacement. Highly recommended as the chassis can run safely on remaining fans for up to 24 hours.",
            "Option B: Shut down node for replacement. Unnecessary precaution that causes node outage and grid data redistribution."
          ],
          thirdParty: "No hypervisor impact. Controlled inside the physical SG6000 hardware chassis."
        }
      }
    ],
    upgrades: {
      targetVersion: "11.8.2",
      urgency: "Recommended",
      benefits: "Patches security issues and introduces S3 Object Lock configuration wizard interfaces."
    },
    contracts: {
      status: "normal",
      endDate: "2028-01-10",
      daysRemaining: 553,
      supportLevel: "SupportEdge Premium 4hr"
    },
    lifecycle: {
      eoaDate: "2026-12-31",
      eosDate: "2031-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "1.0:1",
      logicalUsedTB: 850.0,
      physicalUsedTB: 850.0,
      spaceSavedTB: 0.0,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [
      {
        type: "Bare Metal Appliance",
        version: "SG6060 firmware v3.4",
        plugin: "None",
        multipathing: "100G LACP Bonding",
        health: "Critical"
      }
    ]
  },
  {
    serialNumber: "622004445555",
    systemName: "netapp-mc-ip",
    clusterName: "NY-NJ-METROCLUSTER",
    customerName: "Global Bank Corp",
    ontapVersion: "9.12.1P10",
    platform: "FAS9000 MetroCluster IP",
    status: "warning",
    risks: [
      {
        id: 401,
        severity: "high",
        category: "MetroCluster",
        description: "MetroCluster IP Inter-Switch Link (ISL) packet loss on port e5a exceeds 2%.",
        recommendation: "Inspect fiber patch cables and SFP+ optical transceivers on Switch A1.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Protection_and_Security/MetroCluster/MetroCluster_IP_ISL_link_troubleshooting",
        remediationPlan: {
          cause: "Optical transceiver (SFP) in Cisco Nexus 3132 MetroCluster switch port e5a is reporting high CRC error rates due to dust contamination.",
          impact: "SyncMirror replication lag between Site A and Site B. Under high write loads, write operations might stall to maintain syncreplication parity.",
          steps: [
            "1. SSH to Cisco Switch A1. Run: 'show interface ethernet 1/5 counters errors'.",
            "2. Note the high FCS/CRC error count.",
            "3. Put port in admin shutdown: 'interface ethernet 1/5' -> 'shutdown'. (ONTAP will failover replication traffic to path B).",
            "4. Disconnect optical fiber cable, clean connector using a fiber optic cleaning pen, and replace SFP transceiver.",
            "5. Re-enable port: 'no shutdown'. Verify errors do not increment."
          ],
          options: [
            "Option A: Clean fiber and replace SFP (non-disruptive, recommended).",
            "Option B: Replace optical patch cord. Only if SFP swap does not resolve error rates."
          ],
          thirdParty: "No hypervisor impact. Managed entirely by the back-end MetroCluster IP fabric switch layers."
        }
      }
    ],
    upgrades: {
      targetVersion: "9.13.1P8",
      urgency: "Recommended",
      benefits: "Provides automated switchover enhancements for MetroCluster configuration."
    },
    contracts: {
      status: "normal",
      endDate: "2027-04-30",
      daysRemaining: 298,
      supportLevel: "SupportEdge Premium 2hr"
    },
    lifecycle: {
      eoaDate: "2025-12-31",
      eosDate: "2030-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "3.8:1",
      logicalUsedTB: 540.0,
      physicalUsedTB: 142.1,
      spaceSavedTB: 397.9,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: true,
      relationships: [
        {
          destination: "NJ-METROCLUSTER (Site B)",
          type: "SyncMirror (Synchronous)",
          schedule: "Immediate",
          status: "In-Sync",
          state: "Snapmirrored",
          lagTime: "0 sec",
          healthy: true
        }
      ]
    },
    hypervisors: [
      {
        type: "VMware vSphere (Stretch)",
        version: "ESXi 8.0",
        plugin: "ONTAP Tools v10.0",
        multipathing: "ALUA Multipath configured",
        health: "Normal"
      }
    ]
  },
  {
    serialNumber: "622005557777",
    systemName: "netapp-fas-vmware",
    clusterName: "HQ-ESXI-CLUSTER",
    customerName: "Global Bank Corp",
    ontapVersion: "9.13.1P5",
    platform: "AFF A800 (VMware Integrations)",
    status: "warning",
    risks: [
      {
        id: 501,
        severity: "high",
        category: "Hypervisor Integration",
        description: "VMware ESXi Host multipathing policy is configured to default 'Most Recently Used' (Fixed) instead of Round Robin.",
        recommendation: "Change ESXi Host Native Multipathing (NMP) Path Selection Policy (PSP) to VMW_PSP_RR.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/ESXi_multipathing_best_practices_for_ONTAP",
        remediationPlan: {
          cause: "Newly added ESXi hosts did not have the NetApp Host Utilities script executed, leaving default storage path settings active.",
          impact: "Unbalanced storage path utilization. If the active FC/iSCSI path fails, path failover times exceed 30 seconds, causing ESXi datastore disconnect warnings (PDL - Permanent Device Loss) and VM freeze/crash events.",
          steps: [
            "1. Log in to VMware vCenter Server using vSphere Client.",
            "2. Select affected ESXi host -> Configure -> Storage -> Storage Devices.",
            "3. Select NetApp LUN -> Properties -> Edit Multipathing Policy.",
            "4. Change Path Selection Policy from 'Fixed' to 'Round Robin (VMW_PSP_RR)' and set the IO operation limit to 1.",
            "5. Alternatively, run CLI script on ESXi shell: 'esxcli storage nmp device set -d <naa_id> -P VMW_PSP_RR' and 'esxcli storage nmp psp roundrobin device config set -d <naa_id> -I 1 -t iops'."
          ],
          options: [
            "Option A: Apply manually via vCenter GUI. Suitable for small environments.",
            "Option B (Recommended): Deploy ONTAP Tools for VMware (OTV) vSphere plugin. It automates host configuration checks and applies all NetApp best practice settings with one click."
          ],
          thirdParty: "VMware vSphere 7.x/8.x configurations. Directly impacts VM stability during storage port path failures."
        }
      }
    ],
    upgrades: {
      targetVersion: "9.13.1P8",
      urgency: "None",
      benefits: "Updates security certificates for VASA API communication."
    },
    contracts: {
      status: "normal",
      endDate: "2027-11-20",
      daysRemaining: 502,
      supportLevel: "SupportEdge Premium 4hr"
    },
    lifecycle: {
      eoaDate: "2027-06-30",
      eosDate: "2032-06-30",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "4.8:1",
      logicalUsedTB: 350.0,
      physicalUsedTB: 72.9,
      spaceSavedTB: 277.1,
      fabricPoolTieredTB: 85.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [
      {
        type: "VMware vSphere",
        version: "ESXi 8.0 Update 1",
        plugin: "VASA Provider 10.0 (Connected)",
        multipathing: "VMW_PSP_FIXED (Out of Compliance)",
        health: "Warning"
      }
    ]
  }
];

const DEFAULT_GROUPS = [
  {
    id: "group_us_prod",
    name: "US Production Clusters",
    systemSerials: ["622001234567", "622004445555"]
  },
  {
    id: "group_cvo_dr",
    name: "AWS Cloud DR",
    systemSerials: ["622002223333"]
  },
  {
    id: "group_sg_object",
    name: "Object Storage Tier",
    systemSerials: ["622003334444"]
  }
];

// 2. Global State Variable
let state = {
  currentTab: "overview",
  mockMode: true,
  systems: [...MOCK_SYSTEMS],
  groups: [...DEFAULT_GROUPS],
  selectedSystem: MOCK_SYSTEMS[0],
  activeSearchQuery: "",
  activeFilterType: "ALL", // "ALL", "CUSTOMER", "GROUP"
  activeFilterValue: ""    // Customer Name or Group ID
};

// 3. Storage & Groups Helpers
function loadConfig() {
  const mockModeVal = localStorage.getItem("aiq_mock_mode");
  state.mockMode = mockModeVal === null ? true : mockModeVal === "true";
  
  const refresh = localStorage.getItem("aiq_refresh_token") || "";
  const access = localStorage.getItem("aiq_access_token") || "";
  const expiry = localStorage.getItem("aiq_token_expiry") || "";
  
  // Load groups
  const savedGroups = localStorage.getItem("aiq_custom_groups");
  if (savedGroups) {
    state.groups = JSON.parse(savedGroups);
  } else {
    state.groups = [...DEFAULT_GROUPS];
  }
  
  return { refresh, access, expiry };
}

function saveConfig(refresh, access, expiry) {
  localStorage.setItem("aiq_refresh_token", refresh);
  localStorage.setItem("aiq_access_token", access);
  localStorage.setItem("aiq_token_expiry", expiry);
}

function saveGroups() {
  localStorage.setItem("aiq_custom_groups", JSON.stringify(state.groups));
}

function setMockMode(val) {
  state.mockMode = val;
  localStorage.setItem("aiq_mock_mode", val.toString());
  updateStatusIndicators();
}

// 4. Token & API Client Logic
async function getValidAccessToken() {
  if (state.mockMode) return "mock-token-abc-123";
  
  const refresh = localStorage.getItem("aiq_refresh_token");
  const access = localStorage.getItem("aiq_access_token");
  const expiry = parseFloat(localStorage.getItem("aiq_token_expiry") || "0");

  if (!refresh) {
    throw new Error("API Refresh Token not configured. Please visit the Settings tab.");
  }

  if (access && expiry > (Date.now() / 1000) + 300) {
    return access;
  }

  const response = await fetch(`${API_BASE}/tokens/accessToken`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh })
  });

  if (!response.ok) {
    throw new Error("Authentication failed. Please verify your Refresh Token in Settings.");
  }

  const data = await response.json();
  const newExpiry = (Date.now() / 1000) + 3600;
  saveConfig(data.refresh_token, data.access_token, newExpiry.toString());
  return data.access_token;
}

// Global API Fetch wrapper with auto-rotation
async function callActiveIQAPI(endpoint) {
  if (state.mockMode) {
    return simulateMockAPIResponse(endpoint);
  }
  
  try {
    const token = await getValidAccessToken();
    const response = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      }
    });
    
    if (!response.ok) {
      throw new Error(`API returned error: ${response.status} ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.error("Active IQ API Fetch Error: ", error);
    throw error;
  }
}

function simulateMockAPIResponse(endpoint) {
  if (endpoint.includes("/systems")) {
    const parts = endpoint.split("/");
    if (parts.length > 2) {
      const serial = parts[2];
      return MOCK_SYSTEMS.find(s => s.serialNumber === serial) || MOCK_SYSTEMS[0];
    }
    return MOCK_SYSTEMS;
  }
  return {};
}

// 5. DOM Render Utilities & Charts
let efficiencyChartInstance = null;
let capacityChartInstance = null;

function renderCharts() {
  const ctxEff = document.getElementById("efficiencyChart");
  const ctxCap = document.getElementById("capacityChart");
  
  if (!ctxEff || !ctxCap) return;
  
  const filteredSystems = getFilteredSystems();
  const logicalSum = filteredSystems.reduce((acc, sys) => acc + sys.efficiency.logicalUsedTB, 0);
  const physicalSum = filteredSystems.reduce((acc, sys) => acc + sys.efficiency.physicalUsedTB, 0);
  const savedSum = filteredSystems.reduce((acc, sys) => acc + sys.efficiency.spaceSavedTB, 0);

  if (efficiencyChartInstance) efficiencyChartInstance.destroy();
  if (capacityChartInstance) capacityChartInstance.destroy();

  if (typeof Chart === "undefined") {
    console.warn("Chart.js library not loaded yet.");
    return;
  }

  efficiencyChartInstance = new Chart(ctxEff, {
    type: 'doughnut',
    data: {
      labels: ['Physical Used Space (TB)', 'Space Saved by Efficiency (TB)'],
      datasets: [{
        data: [physicalSum.toFixed(1), savedSum.toFixed(1)],
        backgroundColor: ['rgba(0, 229, 255, 0.7)', 'rgba(0, 230, 118, 0.7)'],
        borderColor: ['#00e5ff', '#00e676'],
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#f3f4f6' }
        }
      }
    }
  });

  capacityChartInstance = new Chart(ctxCap, {
    type: 'bar',
    data: {
      labels: filteredSystems.map(s => s.systemName),
      datasets: [
        {
          label: 'On-Prem Flash Storage (TB)',
          data: filteredSystems.map(s => (s.efficiency.physicalUsedTB - s.efficiency.fabricPoolTieredTB).toFixed(1)),
          backgroundColor: 'rgba(79, 172, 254, 0.7)',
          borderColor: '#4facfe',
          borderWidth: 1
        },
        {
          label: 'FabricPool Tiered to Cloud (TB)',
          data: filteredSystems.map(s => s.efficiency.fabricPoolTieredTB.toFixed(1)),
          backgroundColor: 'rgba(0, 229, 255, 0.7)',
          borderColor: '#00e5ff',
          borderWidth: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255, 255, 255, 0.05)' } },
        y: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255, 255, 255, 0.05)' } }
      },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#f3f4f6' }
        }
      }
    }
  });
}

function getFilteredSystems() {
  if (state.activeFilterType === "CUSTOMER") {
    return state.systems.filter(s => s.customerName === state.activeFilterValue);
  } else if (state.activeFilterType === "GROUP") {
    const group = state.groups.find(g => g.id === state.activeFilterValue);
    if (group) {
      return state.systems.filter(s => group.systemSerials.includes(s.serialNumber));
    }
  }
  return state.systems; // default: show all
}

function updateOverviewKpis() {
  const filtered = getFilteredSystems();
  const totalSystems = filtered.length;
  const criticalRisksCount = filtered.reduce((acc, sys) => 
    acc + sys.risks.filter(r => r.severity === 'critical').length, 0);
  const warningRisksCount = filtered.reduce((acc, sys) => 
    acc + sys.risks.filter(r => r.severity === 'high' || r.severity === 'medium').length, 0);
  const expiringContracts = filtered.filter(sys => sys.contracts.daysRemaining <= 90).length;

  document.getElementById("kpiTotalSystems").innerText = totalSystems;
  document.getElementById("kpiCriticalRisks").innerText = criticalRisksCount;
  document.getElementById("kpiWarningRisks").innerText = warningRisksCount;
  document.getElementById("kpiContracts").innerText = expiringContracts;
  
  document.getElementById("kpiCriticalRisks").style.color = criticalRisksCount > 0 ? "var(--status-critical)" : "var(--status-normal)";
  document.getElementById("kpiWarningRisks").style.color = warningRisksCount > 0 ? "var(--status-warning)" : "var(--status-normal)";
  document.getElementById("kpiContracts").style.color = expiringContracts > 0 ? "var(--status-warning)" : "var(--status-normal)";
}

function renderOverviewTable() {
  const tbody = document.getElementById("overviewTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const query = state.activeSearchQuery.toLowerCase();
  const baseSystems = getFilteredSystems();
  
  const filteredSystems = baseSystems.filter(sys => 
    sys.systemName.toLowerCase().includes(query) || 
    sys.serialNumber.toLowerCase().includes(query) ||
    sys.clusterName.toLowerCase().includes(query) ||
    sys.customerName.toLowerCase().includes(query) ||
    sys.platform.toLowerCase().includes(query)
  );

  if (filteredSystems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No matching systems found.</td></tr>`;
    return;
  }

  filteredSystems.forEach(sys => {
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.onclick = () => selectSystem(sys.serialNumber);
    
    let statusBadge = `<span class="badge normal">Healthy</span>`;
    if (sys.status === "critical") statusBadge = `<span class="badge critical">Critical</span>`;
    else if (sys.status === "warning") statusBadge = `<span class="badge warning">Warning</span>`;

    let contractText = `${sys.contracts.endDate} (${sys.contracts.daysRemaining}d)`;
    if (sys.contracts.daysRemaining < 0) {
      contractText = `<span style="color: var(--status-critical); font-weight: 600;">Expired (${Math.abs(sys.contracts.daysRemaining)}d ago)</span>`;
    } else if (sys.contracts.daysRemaining <= 90) {
      contractText = `<span style="color: var(--status-warning); font-weight: 600;">${sys.contracts.endDate} (${sys.contracts.daysRemaining}d)</span>`;
    }

    tr.innerHTML = `
      <td style="font-weight: 600; color: var(--accent-cyan);">${sys.systemName}</td>
      <td><code>${sys.serialNumber}</code></td>
      <td>${sys.clusterName}</td>
      <td>${sys.customerName}</td>
      <td>${sys.platform}</td>
      <td>${statusBadge}</td>
      <td>${contractText}</td>
    `;
    tbody.appendChild(tr);
  });
}

function populateSystemSelectors() {
  const selectors = ["tamSystemSelect", "samSystemSelect", "csmSystemSelect"];
  const currentFiltered = getFilteredSystems();
  
  // If selectedSystem is not in the filtered scope, pick the first filtered system
  if (currentFiltered.length > 0 && !currentFiltered.some(s => s.serialNumber === state.selectedSystem.serialNumber)) {
    state.selectedSystem = currentFiltered[0];
  }
  
  selectors.forEach(id => {
    const select = document.getElementById(id);
    if (!select) return;
    select.innerHTML = "";
    currentFiltered.forEach(sys => {
      const opt = document.createElement("option");
      opt.value = sys.serialNumber;
      opt.innerText = `${sys.systemName} (${sys.platform})`;
      if (state.selectedSystem && sys.serialNumber === state.selectedSystem.serialNumber) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
    
    select.onchange = (e) => {
      const serial = e.target.value;
      const found = state.systems.find(s => s.serialNumber === serial);
      if (found) {
        state.selectedSystem = found;
        switchTab(state.currentTab);
      }
    };
  });
}

function openRemediationModal(riskId) {
  const sys = state.selectedSystem;
  if (!sys) return;
  const risk = sys.risks.find(r => r.id === riskId);
  if (!risk) return;

  const modal = document.getElementById("remediationModal");
  if (!modal) return;

  document.getElementById("modalRiskTitle").innerText = `Remediation Plan: ${risk.category} Risk`;
  document.getElementById("modalRiskDesc").innerText = risk.description;

  document.getElementById("modalDetailCause").innerText = risk.remediationPlan.cause;
  document.getElementById("modalDetailImpact").innerText = risk.remediationPlan.impact;
  
  const stepsList = document.getElementById("modalDetailSteps");
  stepsList.innerHTML = "";
  risk.remediationPlan.steps.forEach(step => {
    const li = document.createElement("li");
    li.innerText = step;
    li.style.marginBottom = "6px";
    stepsList.appendChild(li);
  });

  const optionsList = document.getElementById("modalDetailOptions");
  optionsList.innerHTML = "";
  risk.remediationPlan.options.forEach(opt => {
    const li = document.createElement("li");
    li.innerText = opt;
    li.style.marginBottom = "6px";
    optionsList.appendChild(li);
  });

  document.getElementById("modalDetailThirdParty").innerText = risk.remediationPlan.thirdParty;

  const kbBtn = document.getElementById("modalKbLink");
  kbBtn.href = risk.kbLink;

  modal.style.display = "flex";
}

function closeRemediationModal() {
  const modal = document.getElementById("remediationModal");
  if (modal) modal.style.display = "none";
}

function renderTAMTab() {
  populateSystemSelectors();
  const sys = state.selectedSystem;
  if (!sys) {
    document.getElementById("tamRisksTableBody").innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No systems available in current scope.</td></tr>`;
    document.getElementById("tamUpgradeContainer").innerHTML = "";
    return;
  }

  document.getElementById("tamActiveSystem").innerHTML = `
    <strong>System</strong>: ${sys.systemName} (S/N: ${sys.serialNumber}) | <strong>ONTAP</strong>: ${sys.ontapVersion}
  `;

  let riskRows = "";
  if (sys.risks.length === 0) {
    riskRows = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No active technical risks found. System is fully compliant.</td></tr>`;
  } else {
    sys.risks.forEach(r => {
      let sevBadge = `<span class="badge info">${r.severity}</span>`;
      if (r.severity === "critical") sevBadge = `<span class="badge critical">Critical</span>`;
      else if (r.severity === "high") sevBadge = `<span class="badge critical">High</span>`;
      else if (r.severity === "medium") sevBadge = `<span class="badge warning">Medium</span>`;
      else if (r.severity === "low") sevBadge = `<span class="badge info">Low</span>`;

      riskRows += `
        <tr>
          <td>${sevBadge}</td>
          <td style="font-weight: 600;">${r.category}</td>
          <td>
            <div style="font-weight: 500; margin-bottom: 4px;">${r.description}</div>
            <div style="color: var(--text-secondary); font-size: 0.8rem; margin-bottom: 6px;">${r.recommendation}</div>
          </td>
          <td>
            <div style="display: flex; gap: 8px;">
              <button class="action-btn" style="font-size: 0.75rem; padding: 6px 12px;" onclick="openRemediationModal(${r.id})">Remediation Plan</button>
              <a class="external-link" style="font-size: 0.75rem; display: flex; align-items: center;" href="${r.kbLink}" target="_blank">KB Art</a>
            </div>
          </td>
        </tr>
      `;
    });
  }

  const upgradeBox = document.getElementById("tamUpgradeContainer");
  if (sys.upgrades.targetVersion === "Up to Date") {
    upgradeBox.innerHTML = `
      <h3 style="color: var(--status-normal); margin-bottom: 12px;">✓ System Up to Date</h3>
      <p style="font-size: 0.9rem; color: var(--text-secondary);">This system is currently running a fully supported, stable release. No upgrades are required.</p>
    `;
  } else {
    upgradeBox.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <h3 style="font-size: 1.05rem;">Recommended OS Upgrade</h3>
        <span class="badge warning">${sys.upgrades.urgency}</span>
      </div>
      <div style="margin-bottom: 8px;">Current Version: <strong style="color: var(--text-muted);">${sys.ontapVersion}</strong></div>
      <div style="margin-bottom: 8px;">Target Version: <strong style="color: var(--accent-cyan);">${sys.upgrades.targetVersion}</strong></div>
      <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;">${sys.upgrades.benefits}</p>
    `;
  }

  document.getElementById("tamRisksTableBody").innerHTML = riskRows;
}

function renderSAMTab() {
  populateSystemSelectors();
  const sys = state.selectedSystem;
  if (!sys) {
    document.getElementById("samContractCard").innerHTML = "";
    document.getElementById("samLifecycleCard").innerHTML = "";
    document.getElementById("samHypervisorCard").innerHTML = "";
    document.getElementById("samFieldActionsBody").innerHTML = `<tr><td colspan="2" style="text-align: center; color: var(--text-muted);">No systems available in current scope.</td></tr>`;
    return;
  }

  document.getElementById("samActiveSystem").innerHTML = `
    <strong>System</strong>: ${sys.systemName} (S/N: ${sys.serialNumber}) | <strong>Platform</strong>: ${sys.platform}
  `;

  let contractBadge = `<span class="badge normal">Active</span>`;
  let expiryColor = "var(--text-primary)";
  if (sys.contracts.status === "critical") {
    contractBadge = `<span class="badge critical">Expired</span>`;
    expiryColor = "var(--status-critical)";
  } else if (sys.contracts.status === "warning") {
    contractBadge = `<span class="badge warning">Expiring Soon</span>`;
    expiryColor = "var(--status-warning)";
  }

  document.getElementById("samContractCard").innerHTML = `
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
      <h4 style="font-size: 0.9rem; color: var(--text-secondary);">Support Level: ${sys.contracts.supportLevel}</h4>
      ${contractBadge}
    </div>
    <div style="font-size: 1.4rem; font-weight: 700; margin-bottom: 6px; color: ${expiryColor};">
      Expires: ${sys.contracts.endDate}
    </div>
    <div style="font-size: 0.8rem; color: var(--text-muted);">
      ${sys.contracts.daysRemaining < 0 ? `Support ended ${Math.abs(sys.contracts.daysRemaining)} days ago.` : `${sys.contracts.daysRemaining} days remaining.`}
    </div>
  `;

  let lcStatus = `<span class="badge normal">Fully Supported</span>`;
  let eoaGlow = "var(--text-primary)";
  if (sys.lifecycle.isNearEos) {
    lcStatus = `<span class="badge critical">EOS Warning</span>`;
    eoaGlow = "var(--status-critical)";
  }

  document.getElementById("samLifecycleCard").innerHTML = `
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
      <h4 style="font-size: 0.9rem; color: var(--text-secondary);">End of Support (EOS)</h4>
      ${lcStatus}
    </div>
    <div style="font-size: 1.4rem; font-weight: 700; margin-bottom: 6px; color: ${eoaGlow};">
      EOS: ${sys.lifecycle.eosDate}
    </div>
    <div style="font-size: 0.8rem; color: var(--text-muted);">
      End of Availability (EOA): ${sys.lifecycle.eoaDate}
    </div>
  `;

  let faRows = "";
  if (sys.fieldActions.length === 0) {
    faRows = `<tr><td colspan="2" style="text-align: center; color: var(--text-muted);">No outstanding field actions. System is compliant.</td></tr>`;
  } else {
    sys.fieldActions.forEach(fa => {
      faRows += `
        <tr>
          <td style="font-weight: 600; color: var(--status-warning);"><code>${fa.id}</code></td>
          <td>
            <div style="font-weight: 500; margin-bottom: 4px;">${fa.title}</div>
            <div style="color: var(--text-secondary); font-size: 0.8rem;">${fa.actionRequired}</div>
          </td>
        </tr>
      `;
    });
  }
  document.getElementById("samFieldActionsBody").innerHTML = faRows;

  const hypContainer = document.getElementById("samHypervisorCard");
  if (hypContainer && sys.hypervisors && sys.hypervisors.length > 0) {
    const hyp = sys.hypervisors[0];
    let hBadge = `<span class="badge normal">${hyp.health}</span>`;
    if (hyp.health === "Warning" || hyp.health === "Critical") {
      hBadge = `<span class="badge warning">${hyp.health}</span>`;
    }
    hypContainer.innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h4 style="font-size: 0.9rem; color: var(--text-secondary);">3rd-Party Integrations</h4>
        ${hBadge}
      </div>
      <div style="font-size: 1.25rem; font-weight: 700; margin-bottom: 8px;">
        ${hyp.type} (v${hyp.version})
      </div>
      <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px;">
        Plugin: <strong>${hyp.plugin}</strong>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-secondary);">
        Multipathing: <strong>${hyp.multipathing}</strong>
      </div>
    `;
  } else if (hypContainer) {
    hypContainer.innerHTML = `<div style="color: var(--text-muted);">No hypervisor integrations tracked.</div>`;
  }
}

function renderCSMTab() {
  populateSystemSelectors();
  const sys = state.selectedSystem;
  if (!sys) {
    document.getElementById("csmSavingsCard").innerHTML = "";
    document.getElementById("csmCloudCard").innerHTML = "";
    document.getElementById("csmSnapmirrorCard").innerHTML = "";
    document.getElementById("csmAdoptionChecklist").innerHTML = "";
    return;
  }

  document.getElementById("csmActiveSystem").innerHTML = `
    <strong>System</strong>: ${sys.systemName} (S/N: ${sys.serialNumber}) | <strong>Customer</strong>: ${sys.customerName}
  `;

  document.getElementById("csmSavingsCard").innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 12px;">
      <div>
        <span style="font-size: 0.8rem; color: var(--text-secondary); text-transform: uppercase;">Storage Efficiency Ratio</span>
        <div style="font-size: 2.2rem; font-weight: 800; color: var(--status-normal);">${sys.efficiency.ratio}</div>
      </div>
      <div style="border-top: 1px solid var(--border-color); padding-top: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
        <div>
          <span style="font-size: 0.75rem; color: var(--text-muted);">Logical Space Used</span>
          <div style="font-weight: 600;">${sys.efficiency.logicalUsedTB.toFixed(1)} TB</div>
        </div>
        <div>
          <span style="font-size: 0.75rem; color: var(--text-muted);">Physical Space Used</span>
          <div style="font-weight: 600;">${sys.efficiency.physicalUsedTB.toFixed(1)} TB</div>
        </div>
      </div>
      <div style="background-color: rgba(0, 230, 118, 0.08); padding: 12px; border-radius: var(--radius-sm); border: 1px solid rgba(0, 230, 118, 0.2);">
        <div style="font-size: 0.75rem; color: var(--status-normal); font-weight: 700; text-transform: uppercase; margin-bottom: 2px;">Total Storage Saved</div>
        <div style="font-size: 1.2rem; font-weight: 700; color: #fff;">${sys.efficiency.spaceSavedTB.toFixed(1)} TB</div>
      </div>
    </div>
  `;

  const fpTiered = sys.efficiency.fabricPoolTieredTB;
  let fpStatusText = "";
  let fpAdoptionBadge = "";
  
  if (fpTiered > 0) {
    fpAdoptionBadge = `<span class="badge normal">Tiering Active</span>`;
    fpStatusText = `System is tiering <strong>${fpTiered.toFixed(1)} TB</strong> of cold data to public/private cloud object storage. This saves premium flash tier capacity.`;
  } else {
    fpAdoptionBadge = `<span class="badge warning">No Cloud Tiering</span>`;
    fpStatusText = `<span style="color: var(--status-warning);">Potential opportunity!</span> Enable FabricPool tiering to offload cold backup/snapshot data to cheaper object storage and free up premium flash capacity.`;
  }

  document.getElementById("csmCloudCard").innerHTML = `
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
      <h4 style="font-size: 0.9rem; color: var(--text-secondary);">FabricPool Integration</h4>
      ${fpAdoptionBadge}
    </div>
    <div style="font-size: 1.4rem; font-weight: 700; margin-bottom: 6px; color: ${fpTiered > 0 ? "var(--status-info)" : "var(--status-warning)"};">
      Cloud Tiered: ${fpTiered.toFixed(1)} TB
    </div>
    <p style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4;">
      ${fpStatusText}
    </p>
  `;

  const smContainer = document.getElementById("csmSnapmirrorCard");
  if (smContainer && sys.snapmirror) {
    let smBadge = `<span class="badge normal">Inactive</span>`;
    let relationshipsHTML = "";
    
    if (sys.snapmirror.enabled) {
      smBadge = `<span class="badge normal">Enabled</span>`;
      sys.snapmirror.relationships.forEach(rel => {
        relationshipsHTML += `
          <div style="margin-top: 8px; font-size: 0.8rem; border-top: 1px solid var(--border-color); padding-top: 8px;">
            <div>Dest: <strong>${rel.destination}</strong></div>
            <div>Type: <strong>${rel.type}</strong> | State: <strong>${rel.state}</strong></div>
            <div>Lag Time: <strong style="color: var(--accent-cyan);">${rel.lagTime}</strong></div>
          </div>
        `;
      });
    } else {
      relationshipsHTML = `<div style="color: var(--text-muted); font-size: 0.8rem; margin-top: 10px;">No SnapMirror relations mapped. Add sync/async links for remote backups.</div>`;
    }

    smContainer.innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h4 style="font-size: 0.9rem; color: var(--text-secondary);">SnapMirror replication</h4>
        ${smBadge}
      </div>
      ${relationshipsHTML}
    `;
  }

  const checklist = [
    { name: "ONTAP 9.10+ / StorageGRID 11.5+", completed: true },
    { name: "Storage Efficiency Enabled (>1.5:1)", completed: parseFloat(sys.efficiency.ratio.split(":")[0]) > 1.5 },
    { name: "Cloud FabricPool Configured", completed: fpTiered > 0 },
    { name: "SnapMirror DR Configured", completed: sys.snapmirror.enabled },
    { name: "Zero High/Critical Risks", completed: sys.risks.filter(r => r.severity === 'critical' || r.severity === 'high').length === 0 }
  ];

  let checklistHTML = "";
  checklist.forEach(item => {
    checklistHTML += `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px; background: rgba(255,255,255,0.01); border-bottom: 1px solid var(--border-color);">
        <span style="font-size: 0.85rem;">${item.name}</span>
        ${item.completed ? 
          `<span style="color: var(--status-normal); font-weight: bold; font-size: 1.1rem;">✓</span>` : 
          `<span style="color: var(--status-critical); font-weight: bold; font-size: 1rem;">✗</span>`
        }
      </div>
    `;
  });
  document.getElementById("csmAdoptionChecklist").innerHTML = checklistHTML;
}

// 6. JSON Import / Export & Configuration Panel
function exportConfigJSON() {
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(state.systems, null, 2));
  const link = document.createElement("a");
  link.setAttribute("href", dataStr);
  link.setAttribute("download", `ActiveIQ_AccountReportConfig_${new Date().toISOString().split('T')[0]}.json`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function triggerImportFileInput() {
  document.getElementById("importFileInput").click();
}

function handleJSONImport(event) {
  const file = event.target.files[0];
  if (!file) return;
  
  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const importedData = JSON.parse(e.target.result);
      if (Array.isArray(importedData)) {
        if (importedData.length > 0 && importedData[0].serialNumber) {
          state.systems = importedData;
          state.selectedSystem = importedData[0];
          alert(`Successfully imported configuration containing ${importedData.length} NetApp systems!`);
          switchTab("overview");
        } else {
          alert("Invalid file format. Systems must contain 'serialNumber' property.");
        }
      } else {
        alert("Invalid file format. Configuration must be a JSON array of systems.");
      }
    } catch (err) {
      alert("Failed to parse JSON configuration: " + err.message);
    }
  };
  reader.readAsText(file);
}

// 7. Action Plan Compiler
function populateActionPlanSelector() {
  const select = document.getElementById("planTargetSelect");
  if (!select) return;
  select.innerHTML = '<option value="ALL">All Account Systems (Customer View)</option>';
  
  const customers = [...new Set(state.systems.map(s => s.customerName))];
  customers.forEach(cust => {
    const opt = document.createElement("option");
    opt.value = `CUST:${cust}`;
    opt.innerText = `Customer: ${cust} (All Systems)`;
    select.appendChild(opt);
  });
  
  state.groups.forEach(grp => {
    const opt = document.createElement("option");
    opt.value = `GRP:${grp.id}`;
    opt.innerText = `Group: ${grp.name} (${grp.systemSerials.length} systems)`;
    select.appendChild(opt);
  });
  
  state.systems.forEach(sys => {
    const opt = document.createElement("option");
    opt.value = `SYS:${sys.serialNumber}`;
    opt.innerText = `System: ${sys.systemName} (${sys.platform})`;
    select.appendChild(opt);
  });
}

function generateActionPlan() {
  const selectValue = document.getElementById("planTargetSelect").value;
  const planBody = document.getElementById("generatedPlanBody");
  if (!planBody) return;
  
  let targetSystems = [];
  let scopeTitle = "";
  
  if (selectValue === "ALL") {
    targetSystems = state.systems;
    scopeTitle = "Total Account Portfolio";
  } else if (selectValue.startsWith("CUST:")) {
    const custName = selectValue.substring(5);
    targetSystems = state.systems.filter(s => s.customerName === custName);
    scopeTitle = `Customer: ${custName}`;
  } else if (selectValue.startsWith("GRP:")) {
    const groupId = selectValue.substring(4);
    const grp = state.groups.find(g => g.id === groupId);
    if (grp) {
      targetSystems = state.systems.filter(s => grp.systemSerials.includes(s.serialNumber));
      scopeTitle = `Custom Group: ${grp.name}`;
    }
  } else if (selectValue.startsWith("SYS:")) {
    const serial = selectValue.substring(4);
    const found = state.systems.find(s => s.serialNumber === serial);
    if (found) targetSystems = [found];
    scopeTitle = `System: ${found ? found.systemName : serial}`;
  }

  if (targetSystems.length === 0) {
    planBody.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 40px;">No systems found in the selected scope.</div>`;
    return;
  }

  const allRisks = [];
  const allUpgrades = [];
  const expiringContracts = [];
  const activeFAs = [];
  const allHypervisors = [];

  targetSystems.forEach(sys => {
    sys.risks.forEach(r => allRisks.push({ systemName: sys.systemName, ...r }));
    if (sys.upgrades.targetVersion !== "Up to Date") {
      allUpgrades.push({ systemName: sys.systemName, ...sys.upgrades });
    }
    if (sys.contracts.daysRemaining <= 90) {
      expiringContracts.push({ systemName: sys.systemName, ...sys.contracts });
    }
    sys.fieldActions.forEach(fa => activeFAs.push({ systemName: sys.systemName, ...fa }));
    if (sys.hypervisors) {
      sys.hypervisors.forEach(h => allHypervisors.push({ systemName: sys.systemName, ...h }));
    }
  });

  let html = `
    <div class="plan-document-header">
      <div style="font-size: 0.85rem; color: var(--accent-cyan); text-transform: uppercase; font-weight: 700; letter-spacing: 1px;">NetApp Operations & Advisory Plan</div>
      <h1 style="font-size: 1.8rem; margin: 8px 0 16px 0; color: #fff;">Executive Action Plan & Best Practices Guide</h1>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; font-size: 0.85rem; color: var(--text-secondary); border-top: 1px solid var(--border-color); padding-top: 12px;">
        <div>Scope: <strong>${scopeTitle}</strong></div>
        <div>Date Generated: <strong>${new Date().toISOString().split('T')[0]}</strong></div>
      </div>
    </div>

    <!-- Executive Summary Section -->
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">1. Executive Summary</h2>
      <p style="font-size: 0.9rem; line-height: 1.5; color: var(--text-secondary); margin-bottom: 12px;">
        This document represents the consolidated operational action plan generated from telemetry data analyzed by NetApp Active IQ Digital Advisor. 
        A total of <strong>${targetSystems.length}</strong> storage configuration(s) were audited.
      </p>
      <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 20px 0;">
        <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: var(--radius-sm); text-align: center; border: 1px solid var(--border-color);">
          <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Total Risks</div>
          <div style="font-size: 1.4rem; font-weight: 700; color: ${allRisks.length > 0 ? "var(--status-critical)" : "var(--status-normal)"}">${allRisks.length}</div>
        </div>
        <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: var(--radius-sm); text-align: center; border: 1px solid var(--border-color);">
          <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Pending OS Upgrades</div>
          <div style="font-size: 1.4rem; font-weight: 700; color: ${allUpgrades.length > 0 ? "var(--status-warning)" : "var(--status-normal)"}">${allUpgrades.length}</div>
        </div>
        <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: var(--radius-sm); text-align: center; border: 1px solid var(--border-color);">
          <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Support Expired/Expiring</div>
          <div style="font-size: 1.4rem; font-weight: 700; color: ${expiringContracts.length > 0 ? "var(--status-critical)" : "var(--status-normal)"}">${expiringContracts.length}</div>
        </div>
        <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: var(--radius-sm); text-align: center; border: 1px solid var(--border-color);">
          <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Active Field Actions</div>
          <div style="font-size: 1.4rem; font-weight: 700; color: ${activeFAs.length > 0 ? "var(--status-warning)" : "var(--status-normal)"}">${activeFAs.length}</div>
        </div>
      </div>
    </div>

    <!-- Technical Risks Section -->
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">2. Prioritized Technical Risks & Remediation Steps</h2>
  `;

  if (allRisks.length === 0) {
    html += `<p style="font-size: 0.85rem; color: var(--text-muted);">✓ No technical risk signatures identified across the monitored scope.</p>`;
  } else {
    allRisks.forEach((r, idx) => {
      let badgeColor = "var(--status-info)";
      if (r.severity === "critical" || r.severity === "high") badgeColor = "var(--status-critical)";
      else if (r.severity === "medium") badgeColor = "var(--status-warning)";

      html += `
        <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-left: 4px solid ${badgeColor}; padding: 18px; border-radius: var(--radius-sm); margin-bottom: 16px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <strong style="font-size: 0.95rem; color: #fff;">Item 2.${idx + 1}: ${r.category} Risk - ${r.systemName}</strong>
            <span class="badge ${r.severity}" style="font-size: 0.7rem;">${r.severity}</span>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-primary); margin-bottom: 8px;"><strong>Issue</strong>: ${r.description}</div>
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 12px; background: rgba(0,0,0,0.15); padding: 10px; border-radius: var(--radius-sm);">
            <strong>Root Cause Analysis:</strong><br>${r.remediationPlan.cause}
          </div>
          <div style="font-size: 0.85rem; color: var(--status-critical); margin-bottom: 12px; background: rgba(255, 51, 102, 0.03); padding: 10px; border-radius: var(--radius-sm); border: 1px solid rgba(255, 51, 102, 0.1);">
            <strong>Operations Impact:</strong><br>${r.remediationPlan.impact}
          </div>
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 12px;">
            <strong>Step-by-Step Remediation Plan:</strong>
            <ol style="margin-left: 20px; margin-top: 6px; font-family: monospace; line-height: 1.4;">
              ${r.remediationPlan.steps.map(s => `<li>${s}</li>`).join("")}
            </ol>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-muted);">
            <strong>Options & Trade-offs:</strong>
            <ul style="margin-left: 20px; margin-top: 4px; line-height: 1.4;">
              ${r.remediationPlan.options.map(o => `<li>${o}</li>`).join("")}
            </ul>
          </div>
        </div>
      `;
    });
  }

  html += `
    </div>

    <!-- OS/Firmware Upgrades Section -->
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">3. Recommended OS Upgrade Roadmaps</h2>
  `;

  if (allUpgrades.length === 0) {
    html += `<p style="font-size: 0.85rem; color: var(--text-muted);">✓ All systems are running target version baselines.</p>`;
  } else {
    allUpgrades.forEach(u => {
      html += `
        <div style="background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 16px; border-radius: var(--radius-sm); margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <strong>System: ${u.systemName}</strong>
            <span class="badge warning">${u.urgency}</span>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-secondary);">
            Target ONTAP/GRID Version: <strong style="color: var(--accent-cyan);">${u.targetVersion}</strong>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px;">
            <strong>Expected Upgrade Benefits:</strong> ${u.benefits}
          </div>
        </div>
      `;
    });
  }

  html += `
    </div>

    <!-- Support and Lifecycles Section -->
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">4. Support Agreements & Hardware Lifecycles</h2>
  `;

  if (expiringContracts.length === 0) {
    html += `<p style="font-size: 0.85rem; color: var(--text-muted);">✓ All support contracts have active status and exceed 90 days validity.</p>`;
  } else {
    expiringContracts.forEach(c => {
      const isExpired = c.daysRemaining < 0;
      const textClass = isExpired ? "color: var(--status-critical);" : "color: var(--status-warning);";
      html += `
        <div style="background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 16px; border-radius: var(--radius-sm); margin-bottom: 12px; ${textClass}">
          <strong>System: ${c.systemName} - Contract Expiry Warning</strong>
          <div style="font-size: 0.85rem; margin-top: 4px; color: var(--text-secondary);">
            Support Level: <strong>${c.supportLevel}</strong> | Expiration Date: <strong>${c.endDate}</strong> (${c.daysRemaining} days remaining)
          </div>
        </div>
      `;
    });
  }

  html += `
    </div>

    <!-- Guidelines and Proceeding Steps Section -->
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">5. Operational Guidelines & Proceeding Steps</h2>
      
      <div style="margin-bottom: 18px;">
        <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin-bottom: 6px;">A. Implementing Changes via NetApp Change Control</h4>
        <p style="font-size: 0.85rem; line-height: 1.4; color: var(--text-secondary);">
          To minimize risk when applying technical fixes (e.g., replacing hardware spare parts, updating shelf SAS cabling, or performing software firmware upgrades), ensure you adhere to NetApp change control guidelines:
        </p>
        <ul style="margin-left: 20px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4; margin-top: 6px;">
          <li><strong>Upgrade Advisor</strong>: Always run the 'Upgrade Advisor' script inside Active IQ Digital Advisor to generate a customized configuration checklist before performing any ONTAP updates.</li>
          <li><strong>Pre-upgrade Checklists</strong>: Run cluster health checks: 'system health alert show' and verify that replication paths are stable.</li>
          <li><strong>Maintenance Windows</strong>: Schedule all disk replacement and switch firmware modifications during off-peak periods, even if non-disruptive, to prevent application latency spikes.</li>
        </ul>
      </div>

      <div style="margin-bottom: 18px;">
        <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin-bottom: 6px;">B. 3rd-Party Virtualization & Hypervisor Integrations</h4>
        <p style="font-size: 0.85rem; line-height: 1.4; color: var(--text-secondary);">
          If systems back VM workloads (VMware ESXi or Kubernetes orchestrators), follow host compliance settings:
        </p>
        <ul style="margin-left: 20px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4; margin-top: 6px;">
          <li><strong>Multipathing PSP</strong>: Confirm ESXi hosts utilize VMW_PSP_RR Round Robin policies with IOPS limit=1 to distribute workload. Fixed pathing configurations should be corrected immediately using: 'esxcli storage nmp psp roundrobin device config set -d <naa_id> -I 1 -t iops'.</li>
          <li><strong>Trident Upgrades</strong>: Coordinate Astra Trident driver upgrades alongside Kubernetes API migrations to avoid CSI mount failures.</li>
        </ul>
      </div>

      <div>
        <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin-bottom: 6px;">C. Proceeding Milestones & Next Steps</h4>
        <ol style="margin-left: 20px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5; margin-top: 6px;">
          <li><strong>Coordinate support renewal quotes</strong> for all systems identified in Section 4.</li>
          <li><strong>Create internal IT ticket instances</strong> for the high-priority technical items in Section 2, attaching the generated remediation steps.</li>
          <li><strong>Download detailed upgrade advisor procedures</strong> from Active IQ Portal for the systems in Section 3.</li>
        </ol>
      </div>
    </div>
  `;

  planBody.innerHTML = html;
  document.getElementById("planControlsPanel").style.display = "flex";
}

function printActionPlan() {
  const printContent = document.getElementById("generatedPlanBody").innerHTML;
  const printWindow = window.open("", "_blank");
  printWindow.document.write(`
    <html>
      <head>
        <title>NetApp Active IQ Action Plan</title>
        <style>
          body {
            background-color: #ffffff;
            color: #000000;
            font-family: 'Segoe UI', -apple-system, sans-serif;
            padding: 40px;
          }
          h1, h2, h3, h4 { color: #000000; font-family: sans-serif; }
          h2 { border-bottom: 2px solid #00e5ff; padding-bottom: 8px; }
          .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; border: 1px solid #333; }
          .badge.critical { background: #ffe3e3; color: #cc0033; }
          .badge.warning { background: #fff8e3; color: #cc9900; }
          .badge.normal { background: #e3ffe3; color: #009933; }
          .badge.info { background: #e3f8ff; color: #0066cc; }
          ul, ol { margin-left: 20px; }
          li { margin-bottom: 6px; font-size: 0.85rem; }
          .plan-document-header { border-bottom: 1px solid #ddd; padding-bottom: 12px; margin-bottom: 24px; }
          @media print {
            body { padding: 0; }
            button { display: none; }
          }
        </style>
      </head>
      <body>
        ${printContent}
        <script>
          window.onload = function() {
            window.print();
            window.close();
          }
        </script>
      </body>
    </html>
  `);
  printWindow.document.close();
}

// 8. Collapsible Sidebar Groups Tree Builders
function renderSidebarGroups() {
  const container = document.getElementById("sidebarGroupsList");
  if (!container) return;
  container.innerHTML = "";

  // 1. Group by Customers (calculated dynamically)
  const customers = [...new Set(state.systems.map(s => s.customerName))];
  
  if (customers.length > 0) {
    const custHeader = document.createElement("div");
    custHeader.className = "tree-section-header";
    custHeader.innerText = "Customer Accounts";
    container.appendChild(custHeader);

    customers.forEach(cust => {
      const item = document.createElement("div");
      item.className = "tree-item";
      if (state.activeFilterType === "CUSTOMER" && state.activeFilterValue === cust) {
        item.classList.add("active");
      }
      item.onclick = (e) => {
        e.stopPropagation();
        setFilter("CUSTOMER", cust);
      };
      
      // Calculate active risks for badge
      const custSystems = state.systems.filter(s => s.customerName === cust);
      const riskCount = custSystems.reduce((acc, s) => acc + s.risks.length, 0);
      const badge = riskCount > 0 ? `<span class="tree-badge ${custSystems.some(s => s.status === 'critical') ? 'critical' : 'warning'}">${riskCount}</span>` : '';
      
      item.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
        <span class="tree-text">${cust}</span>
        ${badge}
      `;
      container.appendChild(item);
    });
  }

  // 2. Custom User Defined Groups
  if (state.groups.length > 0) {
    const groupHeader = document.createElement("div");
    groupHeader.className = "tree-section-header";
    groupHeader.style.marginTop = "16px";
    groupHeader.innerText = "Custom Subgroups";
    container.appendChild(groupHeader);

    state.groups.forEach(grp => {
      const item = document.createElement("div");
      item.className = "tree-item";
      if (state.activeFilterType === "GROUP" && state.activeFilterValue === grp.id) {
        item.classList.add("active");
      }
      item.onclick = (e) => {
        e.stopPropagation();
        setFilter("GROUP", grp.id);
      };

      const groupSystems = state.systems.filter(s => grp.systemSerials.includes(s.serialNumber));
      const riskCount = groupSystems.reduce((acc, s) => acc + s.risks.length, 0);
      const badge = riskCount > 0 ? `<span class="tree-badge ${groupSystems.some(s => s.status === 'critical') ? 'critical' : 'warning'}">${riskCount}</span>` : '';

      item.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
        <span class="tree-text">${grp.name}</span>
        ${badge}
      `;
      container.appendChild(item);
    });
  }
}

function setFilter(type, value) {
  state.activeFilterType = type;
  state.activeFilterValue = value;
  
  // Highlight tab or overview
  if (state.currentTab !== "overview") {
    switchTab("overview");
  } else {
    updateOverviewKpis();
    renderOverviewTable();
    renderCharts();
  }
  
  // Redraw sidebar tree highlights
  renderSidebarGroups();
}

function resetFilter() {
  state.activeFilterType = "ALL";
  state.activeFilterValue = "";
  switchTab("overview");
  renderSidebarGroups();
}

// 9. Custom Group Creation Form Logic (in Settings panel)
function populateGroupManagerSystems() {
  const container = document.getElementById("groupManagerSystemsList");
  if (!container) return;
  container.innerHTML = "";

  state.systems.forEach(sys => {
    const div = document.createElement("div");
    div.style.display = "flex";
    div.style.alignItems = "center";
    div.style.gap = "8px";
    div.style.marginBottom = "8px";
    div.style.fontSize = "0.85rem";

    div.innerHTML = `
      <input type="checkbox" class="group-system-checkbox" value="${sys.serialNumber}" id="chk_${sys.serialNumber}" style="cursor: pointer;">
      <label for="chk_${sys.serialNumber}" style="cursor: pointer;">${sys.systemName} (S/N: ${sys.serialNumber} - ${sys.platform})</label>
    `;
    container.appendChild(div);
  });
  
  // Render existing groups list in settings for deletion
  const listContainer = document.getElementById("settingsGroupsManagerList");
  if (!listContainer) return;
  listContainer.innerHTML = "";
  
  if (state.groups.length === 0) {
    listContainer.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-muted);">No custom subgroups defined.</div>`;
    return;
  }
  
  state.groups.forEach(grp => {
    const item = document.createElement("div");
    item.style.display = "flex";
    item.style.justifyContent = "space-between";
    item.style.alignItems = "center";
    item.style.padding = "8px 12px";
    item.style.background = "rgba(255,255,255,0.01)";
    item.style.border = "1px solid var(--border-color)";
    item.style.borderRadius = "var(--radius-sm)";
    item.style.marginBottom = "6px";
    item.style.fontSize = "0.8rem";

    item.innerHTML = `
      <div>
        <strong>${grp.name}</strong> (${grp.systemSerials.length} systems)
      </div>
      <button class="action-btn secondary" style="font-size: 0.7rem; padding: 4px 8px; color: var(--status-critical); border-color: rgba(255,51,102,0.2);" onclick="deleteCustomGroup('${grp.id}')">Delete</button>
    `;
    listContainer.appendChild(item);
  });
}

function handleCreateGroup() {
  const nameInput = document.getElementById("newGroupNameInput");
  const name = nameInput.value.trim();
  if (!name) {
    alert("Please enter a group name.");
    return;
  }

  const selectedSerials = [];
  document.querySelectorAll(".group-system-checkbox:checked").forEach(chk => {
    selectedSerials.push(chk.value);
  });

  if (selectedSerials.length === 0) {
    alert("Please select at least one system to assign to this group.");
    return;
  }

  const newGroup = {
    id: "group_" + Date.now(),
    name: name,
    systemSerials: selectedSerials
  };

  state.groups.push(newGroup);
  saveGroups();
  
  nameInput.value = "";
  document.querySelectorAll(".group-system-checkbox").forEach(chk => chk.checked = false);
  
  alert(`Group "${name}" created successfully!`);
  populateGroupManagerSystems();
  renderSidebarGroups();
}

function deleteCustomGroup(groupId) {
  state.groups = state.groups.filter(g => g.id !== groupId);
  saveGroups();
  alert("Group deleted successfully.");
  populateGroupManagerSystems();
  renderSidebarGroups();
}

// 10. Global active status visual indicators
function updateStatusIndicators() {
  const indicators = document.querySelectorAll(".indicator");
  const textLabel = document.getElementById("connectionStatusText");
  const { refresh } = loadConfig();

  indicators.forEach(ind => {
    ind.className = "indicator";
    if (state.mockMode) {
      ind.classList.add("mock");
      if (textLabel) textLabel.innerText = "Mock Server Mode";
    } else if (refresh) {
      ind.classList.add("connected");
      if (textLabel) textLabel.innerText = "API Connected";
    } else {
      ind.classList.add("disconnected");
      if (textLabel) textLabel.innerText = "No Credentials Configured";
    }
  });
}

function handleSearch(e) {
  state.activeSearchQuery = e.target.value;
  renderOverviewTable();
}

function exportCSV() {
  let csvContent = "data:text/csv;charset=utf-8,";
  csvContent += "System Name,Serial Number,Cluster Name,Customer Name,Platform,Status,ONTAP Version,Efficiency Ratio,Contracts Expiry,Risks Count\n";

  state.systems.forEach(s => {
    const risksCount = s.risks.length;
    const row = [
      s.systemName,
      s.serialNumber,
      s.clusterName,
      s.customerName,
      s.platform,
      s.status,
      s.ontapVersion,
      s.efficiency.ratio,
      s.contracts.endDate,
      risksCount
    ].map(v => `"${v}"`).join(",");
    csvContent += row + "\n";
  });

  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", `NetApp_ActiveIQ_AccountReport_${new Date().toISOString().split('T')[0]}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// 11. Initialization on Load
window.onload = function() {
  loadConfig();
  updateStatusIndicators();
  switchTab("overview");
  renderSidebarGroups();

  document.getElementById("searchInput").addEventListener("input", handleSearch);
  
  window.addEventListener('resize', () => {
    if (state.currentTab === "overview") {
      renderCharts();
    }
  });
};
