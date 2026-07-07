// Active IQ Web Client - Core Application Logic
//
// NOTE ON READ-ONLY DESIGN SAFETY:
// This tool is designed to be strictly READ-ONLY. Under no circumstances should
// this application perform mutating actions (POST, PUT, PATCH, DELETE) against 
// any Active IQ data configurations, customer assets, or cluster parameters.
// The single POST request made in this app is strictly for token authentication
// exchange (refreshing NSS tokens) and does not perform any data modifications.
//

// Determine API base dynamically to support zero-config CORS proxying when served locally
const locOrigin = window.location && window.location.origin ? window.location.origin : "";
const API_BASE = locOrigin.startsWith("http") ? "/api" : "https://api.activeiq.netapp.com/v1";

// 1. Mock Data Definitions (ONTAP, StorageGRID, CVO, MetroCluster, SnapMirror, Hypervisors, Logistics, Contacts, Sales Health, Capacity Projections, Security Bulletins, Support Cases)
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
    ],
    logistics: {
      deliveryAddress: "740 Broadway, Floor 8, New York, NY 10003, US",
      accessRestrictions: "Escort required. 24-hr advance notification to security lobby for loading dock B access.",
      shippingAlert: "None - Active logistics hubs running normal"
    },
    contacts: {
      name: "Sarah Jenkins",
      phone: "+1-212-555-0182",
      email: "sarah.jenkins@globalbank.com",
      nssUsername: "sjenkins_gb"
    },
    salesHealth: {
      accountManager: "David Vance (Senior AE)",
      supportTam: "Marcus Vance (CSM)",
      sentimentScore: 8.5,
      healthStatus: "High Satisfaction",
      upsellPotential: "AFF A900 hardware refresh upgrade",
      refreshWindow: "Q3 2026"
    },
    projections: {
      growthRateGBPerDay: 185,
      daysToLimit: 78,
      limitDate: "2026-09-22",
      peakIops: 28500,
      avgLatencyMs: 2.1,
      historicalCapacityMonths: [18.5, 20.1, 22.0, 24.2, 26.5, 28.7],
      projectedCapacityMonths: [30.5, 32.4, 34.3]
    },
    securityBulletins: [
      {
        id: "NTAP-SA-2024-0002",
        title: "NetApp ONTAP Web UI Multi-vector Denial of Service (DoS) vulnerability",
        severity: "high",
        status: "Vulnerable - Action Required",
        mitigation: "Upgrade to ONTAP 9.13.1P8 or restrict HTTP access on admin interface."
      },
      {
        id: "NTAP-SA-2023-0914",
        title: "OpenSSL Vulnerabilities in ONTAP cryptographic modules",
        severity: "medium",
        status: "Workaround Applied",
        mitigation: "Workaround applied: Disabled TLS 1.0/1.1 protocols. Upgrade recommended."
      }
    ],
    supportCases: [
      {
        id: "2009812234",
        title: "Aggregate aggr1_pcie SSD failure - disk replacement dispatch",
        severity: "S3 - Medium",
        status: "Open - Pending Parts Dispatch",
        criticality: "Moderate - Aggregate in degraded state but protected by RAID-DP. No active data outage.",
        nextActionBy: "NetApp Support Dispatcher",
        createdDate: "2026-06-28",
        lastUpdated: "2026-07-05",
        ownerNotes: "Replacement drive sent to site. Estimated delivery tomorrow morning. Site contact Samantha Ross notified."
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
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/requirements",
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
    ],
    logistics: {
      deliveryAddress: "AWS Cloud VPC (AWS US-East-1 region, Logical Instance)",
      accessRestrictions: "No physical site restrictions. API/IAM authorization configuration required.",
      shippingAlert: "Virtual cloud instance - No physical parts delivery required"
    },
    contacts: {
      name: "Robert Chen",
      phone: "+1-415-555-0923",
      email: "robert.chen@globalbank.com",
      nssUsername: "rchen_cloud_gb"
    },
    salesHealth: {
      accountManager: "David Vance (Senior AE)",
      supportTam: "Marcus Vance (CSM)",
      sentimentScore: 6.5,
      healthStatus: "Retention Risk",
      upsellPotential: "FabricPool cloud tiering expansion",
      refreshWindow: "Q4 2027"
    },
    projections: {
      growthRateGBPerDay: 320,
      daysToLimit: 145,
      limitDate: "2026-11-28",
      peakIops: 12400,
      avgLatencyMs: 4.5,
      historicalCapacityMonths: [45.0, 50.2, 55.4, 60.1, 65.8, 71.4],
      projectedCapacityMonths: [77.2, 83.0, 88.8]
    },
    securityBulletins: [
      {
        id: "NTAP-SA-2024-0015",
        title: "Astra Trident CSI provisioning unauthorized API validation bypass",
        severity: "high",
        status: "Vulnerable - Action Required",
        mitigation: "Upgrade Astra Trident driver to version 24.02.0."
      }
    ],
    supportCases: [
      {
        id: "2009813567",
        title: "CVO instance licensing mismatch warning on console",
        severity: "S2 - Major",
        status: "Open - NetApp Engineering",
        criticality: "High compliance risk - License termination warning active, potential read-only state threat.",
        nextActionBy: "NetApp SaaS Operations Escalation Desk",
        createdDate: "2026-07-02",
        lastUpdated: "2026-07-06",
        ownerNotes: "Escalated to SaaS subscription billing team. Waiting for verification check."
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
    ],
    logistics: {
      deliveryAddress: "550 Enterprise Dr, Data Center Row 4, Dallas, TX 75201, US",
      accessRestrictions: "Biometric check required. SATA drive chassis hot-swap only by certified NetApp engineers.",
      shippingAlert: "Dallas Transit Alert: Winter storm warning causing 24h shipping delays from local depot."
    },
    contacts: {
      name: "James Cole",
      phone: "+1-214-555-0374",
      email: "james.cole@globalbank.com",
      nssUsername: "jcole_infra_gb"
    },
    salesHealth: {
      accountManager: "David Vance (Senior AE)",
      supportTam: "Marcus Vance (CSM)",
      sentimentScore: 7.0,
      healthStatus: "Stable",
      upsellPotential: "Expansion of StorageGRID SGRID-SG6060 compute node shelf",
      refreshWindow: "Q2 2027"
    },
    projections: {
      growthRateGBPerDay: 1500,
      daysToLimit: 92,
      limitDate: "2026-10-06",
      peakIops: 8900,
      avgLatencyMs: 8.2,
      historicalCapacityMonths: [700.0, 730.0, 760.0, 790.0, 820.0, 850.0],
      projectedCapacityMonths: [880.0, 910.0, 940.0]
    },
    securityBulletins: [
      {
        id: "NTAP-SA-2024-0012",
        title: "StorageGRID Webscale Management Interface Remote Code Execution (RCE)",
        severity: "critical",
        status: "Vulnerable - Action Required",
        mitigation: "Apply security patch StorageGRID 11.8.0.2 or disable Management port 9443 access to untrusted networks."
      }
    ],
    supportCases: [
      {
        id: "2009814890",
        title: "Chassis temperature high warning on compute controller",
        severity: "S1 - Critical",
        status: "Open - Customer Action",
        criticality: "High risk - Potential automatic thermal shutdown of controller module node to prevent board damage.",
        nextActionBy: "Customer Data Center Operations Team",
        createdDate: "2026-07-04",
        lastUpdated: "2026-07-06",
        ownerNotes: "Advised customer to inspect fan module 2 immediately to prevent hardware speed throttling."
      }
    ]
  },
  {
    serialNumber: "622004445555",
    systemName: "netapp-mc-ip-a",
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
            "Option A: Clean optical fiber terminations using professional fiber pen.",
            "Option B: Replace faulty SFP+ physical transceiver module."
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
    ],
    logistics: {
      deliveryAddress: "Site A: 100 Plaza Dr, Secaucus, NJ 07094 | Site B: 200 Broad St, Newark, NJ 07102",
      accessRestrictions: "Requires custom high-security access clearance pass and photo ID.",
      shippingAlert: "None - Switch modules staged at Newark local storage"
    },
    contacts: {
      name: "Samantha Ross",
      phone: "+1-201-555-0988",
      email: "samantha.ross@globalbank.com",
      nssUsername: "sross_mc_gb"
    },
    salesHealth: {
      accountManager: "David Vance (Senior AE)",
      supportTam: "Marcus Vance (CSM)",
      sentimentScore: 9.0,
      healthStatus: "High Satisfaction",
      upsellPotential: "Switch support upgrade agreements",
      refreshWindow: "Q1 2028"
    },
    projections: {
      growthRateGBPerDay: 240,
      daysToLimit: 210,
      limitDate: "2027-02-01",
      peakIops: 34200,
      avgLatencyMs: 1.8,
      historicalCapacityMonths: [110.0, 115.4, 122.1, 128.5, 135.0, 142.1],
      projectedCapacityMonths: [148.5, 154.9, 161.3]
    },
    securityBulletins: [
      {
        id: "NTAP-SA-2023-1120",
        title: "Cisco switch hardware supervisor privilege escalation vulnerability",
        severity: "medium",
        status: "Mitigated",
        mitigation: "Cisco Nexus NX-OS patch applied at site A & B switches."
      }
    ],
    supportCases: []
  },
  {
    serialNumber: "622004445556",
    systemName: "netapp-mc-ip-b",
    clusterName: "NY-NJ-METROCLUSTER",
    customerName: "Global Bank Corp",
    ontapVersion: "9.12.1P10",
    platform: "FAS9000 MetroCluster IP",
    status: "normal",
    risks: [],
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
      logicalUsedTB: 512.0,
      physicalUsedTB: 134.7,
      spaceSavedTB: 377.3,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: true,
      relationships: [
        {
          destination: "NY-METROCLUSTER (Site A)",
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
    ],
    logistics: {
      deliveryAddress: "Site B: 200 Broad St, Newark, NJ 07102",
      accessRestrictions: "Requires custom high-security access clearance pass and photo ID.",
      shippingAlert: "None"
    },
    contacts: {
      name: "Samantha Ross",
      phone: "+1-201-555-0988",
      email: "samantha.ross@globalbank.com",
      nssUsername: "sross_mc_gb"
    },
    salesHealth: {
      accountManager: "David Vance (Senior AE)",
      supportTam: "Marcus Vance (CSM)",
      sentimentScore: 9.0,
      healthStatus: "High Satisfaction",
      upsellPotential: "Switch support upgrade agreements",
      refreshWindow: "Q1 2028"
    },
    projections: {
      growthRateGBPerDay: 220,
      daysToLimit: 220,
      limitDate: "2027-02-11",
      peakIops: 31000,
      avgLatencyMs: 1.7,
      historicalCapacityMonths: [100.0, 108.0, 114.0, 120.0, 128.0, 134.7],
      projectedCapacityMonths: [141.0, 147.0, 153.0]
    },
    securityBulletins: [],
    supportCases: []
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
    ],
    logistics: {
      deliveryAddress: "1000 Innovation Way, Server Room A, Sunnyvale, CA 94089, US",
      accessRestrictions: "Badged access required. Coordinate delivery with virtualization team 48 hours in advance.",
      shippingAlert: "None - Sunnyvale depot operations running normal"
    },
    contacts: {
      name: "Thomas Miller",
      phone: "+1-408-555-0456",
      email: "thomas.miller@globalbank.com",
      nssUsername: "tmiller_vm_gb"
    },
    salesHealth: {
      accountManager: "David Vance (Senior AE)",
      supportTam: "Marcus Vance (CSM)",
      sentimentScore: 5.8,
      healthStatus: "Retention Risk",
      upsellPotential: "Migrate VMware storage to ONTAP Tools v10",
      refreshWindow: "Q3 2026"
    },
    projections: {
      growthRateGBPerDay: 110,
      daysToLimit: 45,
      limitDate: "2026-08-20",
      peakIops: 19500,
      avgLatencyMs: 3.2,
      historicalCapacityMonths: [60.0, 62.5, 65.0, 67.5, 70.2, 72.9],
      projectedCapacityMonths: [75.2, 77.5, 79.8]
    },
    securityBulletins: [
      {
        id: "NTAP-SA-2024-0301",
        title: "NetApp NFS VAAI integration plugin for VMware heap overflow",
        severity: "high",
        status: "Vulnerable - Action Required",
        mitigation: "Install ESXi patch NetApp-NFS-VAAI-Plugin v2.1."
      }
    ],
    supportCases: [
      {
        id: "2009815001",
        title: "VASA Provider certificate sync failure",
        severity: "S3 - Medium",
        status: "Resolved - Pending Customer Close",
        criticality: "Low operational risk - certificate sync failure affects management but not data paths.",
        nextActionBy: "Customer Storage Admin (To Close Ticket)",
        createdDate: "2026-06-25",
        lastUpdated: "2026-07-03",
        ownerNotes: "Self-signed certificate renewed and vCenter connection re-established. Customer verifying."
      }
    ]
  },
  // NEW CUSTOMER: HealthCare Solutions Inc
  {
    serialNumber: "622007771111",
    systemName: "hc-ontap-primary",
    clusterName: "BOS-CLINIC-CLUST",
    customerName: "HealthCare Solutions Inc",
    ontapVersion: "9.13.1",
    platform: "AFF A250 (Hospital Core)",
    status: "normal",
    risks: [],
    upgrades: {
      targetVersion: "9.13.1P8",
      urgency: "None",
      benefits: "Applies stability fixes for NVMe-over-Fabric setups."
    },
    contracts: {
      status: "normal",
      endDate: "2028-09-30",
      daysRemaining: 816,
      supportLevel: "SupportEdge Premium 4hr"
    },
    lifecycle: {
      eoaDate: "2028-03-31",
      eosDate: "2033-03-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "3.2:1",
      logicalUsedTB: 80.0,
      physicalUsedTB: 25.0,
      spaceSavedTB: 55.0,
      fabricPoolTieredTB: 5.0
    },
    snapmirror: {
      enabled: true,
      relationships: [
        {
          destination: "hc-cvo-azure (Azure DR)",
          type: "XDP (Asynchronous)",
          schedule: "hourly",
          status: "Mirrored",
          state: "Snapmirrored",
          lagTime: "15 mins",
          healthy: true
        }
      ]
    },
    hypervisors: [
      {
        type: "VMware vSphere",
        version: "ESXi 7.0 Update 3",
        plugin: "VASA Provider 9.8 (Connected)",
        multipathing: "VMW_PSP_RR (Round Robin)",
        health: "Normal"
      }
    ],
    logistics: {
      deliveryAddress: "75 Francis St, Boston Clinic Building, Boston, MA 02115, US",
      accessRestrictions: "Sterile lab protocols. Badge ID and background medical clearance paperwork required.",
      shippingAlert: "None - Site operations running normal"
    },
    contacts: {
      name: "Dr. Alan Grant",
      phone: "+1-617-555-0811",
      email: "alan.grant@hcsolutions.org",
      nssUsername: "agrant_hc"
    },
    salesHealth: {
      accountManager: "Rebecca Loomis",
      supportTam: "Jerry Seinfeld",
      sentimentScore: 9.5,
      healthStatus: "High Satisfaction",
      upsellPotential: "AFF A400 expansion shelf",
      refreshWindow: "Q2 2028"
    },
    projections: {
      growthRateGBPerDay: 95,
      daysToLimit: 290,
      limitDate: "2027-04-22",
      peakIops: 15400,
      avgLatencyMs: 1.9,
      historicalCapacityMonths: [15.0, 17.2, 19.1, 21.0, 23.2, 25.0],
      projectedCapacityMonths: [27.1, 29.0, 31.0]
    },
    securityBulletins: [],
    supportCases: []
  },
  {
    serialNumber: "622007772222",
    systemName: "hc-grid-archive",
    clusterName: "GRID-ARCHIVE-100",
    customerName: "HealthCare Solutions Inc",
    ontapVersion: "11.7.0",
    platform: "StorageGRID SG100",
    status: "warning",
    risks: [
      {
        id: 701,
        severity: "medium",
        category: "Software",
        description: "StorageGRID OS version 11.7.0 is reaching End of Version Support.",
        recommendation: "Plan upgrade to StorageGRID 11.8.x. Refer to NetApp Upgrade Advisor.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/StorageGRID/How_to_upgrade_StorageGRID",
        remediationPlan: {
          cause: "Operating system baseline reaching official support retirement date.",
          impact: "Loss of developer hot-patches and security vulnerability coverage from NetApp engineering after this quarter.",
          steps: [
            "1. Run StorageGRID Pre-Upgrade Validator tool.",
            "2. Download StorageGRID 11.8 package.",
            "3. Execute rolling node upgrade starting with the primary Admin Node."
          ],
          options: [
            "Option A: Upgrade to 11.8.x (Recommended).",
            "Option B: Postpone update under extended support agreement."
          ],
          thirdParty: "Compatible with AWS S3 API v4."
        }
      }
    ],
    upgrades: {
      targetVersion: "11.8.0",
      urgency: "Recommended",
      benefits: "Resolves multiple open security CVEs and improves object recovery times."
    },
    contracts: {
      status: "normal",
      endDate: "2029-01-15",
      daysRemaining: 923,
      supportLevel: "SupportEdge Premium"
    },
    lifecycle: {
      eoaDate: "2028-06-30",
      eosDate: "2033-06-30",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "1.0:1",
      logicalUsedTB: 450.0,
      physicalUsedTB: 450.0,
      spaceSavedTB: 0.0,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [
      {
        type: "Bare Metal Grid Node",
        version: "SG100 Appliance",
        plugin: "None",
        multipathing: "LACP Bonded Interface",
        health: "Normal"
      }
    ],
    logistics: {
      deliveryAddress: "300 Tech Way, Boston Data Center Rack 12, Boston, MA 02109, US",
      accessRestrictions: "Escort required. Standard 24h advance scheduling.",
      shippingAlert: "None - depot operating normal"
    },
    contacts: {
      name: "Dr. Alan Grant",
      phone: "+1-617-555-0811",
      email: "alan.grant@hcsolutions.org",
      nssUsername: "agrant_hc"
    },
    salesHealth: {
      accountManager: "Rebecca Loomis",
      supportTam: "Jerry Seinfeld",
      sentimentScore: 8.0,
      healthStatus: "Stable",
      upsellPotential: "StorageGRID expansion node purchase",
      refreshWindow: "Q1 2029"
    },
    projections: {
      growthRateGBPerDay: 480,
      daysToLimit: 110,
      limitDate: "2026-10-24",
      peakIops: 4200,
      avgLatencyMs: 12.4,
      historicalCapacityMonths: [390.0, 400.0, 412.0, 425.0, 438.0, 450.0],
      projectedCapacityMonths: [462.1, 475.0, 488.0]
    },
    securityBulletins: [
      {
        id: "NTAP-SA-2023-0402",
        title: "Linux Kernel privilege escalation vulnerability on SG100 firmware",
        severity: "high",
        status: "Vulnerable - Action Required",
        mitigation: "Upgrade SG100 firmware to version 11.8."
      }
    ],
    supportCases: []
  },
  {
    serialNumber: "622007773333",
    systemName: "hc-cvo-azure",
    clusterName: "AZR-CVO-DR",
    customerName: "HealthCare Solutions Inc",
    ontapVersion: "9.14.1",
    platform: "Cloud Volumes ONTAP (Azure)",
    status: "normal",
    risks: [],
    upgrades: {
      targetVersion: "Up to Date",
      urgency: "None",
      benefits: ""
    },
    contracts: {
      status: "normal",
      endDate: "2027-05-20",
      daysRemaining: 318,
      supportLevel: "Cloud Volumes Premium"
    },
    lifecycle: {
      eoaDate: "2028-12-31",
      eosDate: "2033-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "2.8:1",
      logicalUsedTB: 140.0,
      physicalUsedTB: 50.0,
      spaceSavedTB: 90.0,
      fabricPoolTieredTB: 22.0
    },
    snapmirror: {
      enabled: true,
      relationships: [
        {
          destination: "hc-ontap-primary (Boston Primary)",
          type: "XDP (Asynchronous)",
          schedule: "hourly",
          status: "Mirrored",
          state: "Snapmirrored",
          lagTime: "15 mins",
          healthy: true
        }
      ]
    },
    hypervisors: [],
    logistics: {
      deliveryAddress: "Azure US-East Subnet 2 (Logical CVO Node)",
      accessRestrictions: "None - Cloud Instance. Managed via Azure Portal.",
      shippingAlert: "None"
    },
    contacts: {
      name: "Dr. Alan Grant",
      phone: "+1-617-555-0811",
      email: "alan.grant@hcsolutions.org",
      nssUsername: "agrant_hc"
    },
    salesHealth: {
      accountManager: "Rebecca Loomis",
      supportTam: "Jerry Seinfeld",
      sentimentScore: 9.0,
      healthStatus: "High Satisfaction",
      upsellPotential: "Azure backup integrations",
      refreshWindow: "Q2 2027"
    },
    projections: {
      growthRateGBPerDay: 80,
      daysToLimit: 400,
      limitDate: "2027-08-10",
      peakIops: 8200,
      avgLatencyMs: 3.5,
      historicalCapacityMonths: [38.0, 40.2, 42.1, 45.0, 48.2, 50.0],
      projectedCapacityMonths: [52.1, 54.0, 56.0]
    },
    securityBulletins: [],
    supportCases: []
  },
  // NEW CUSTOMER: Apex Retail Group
  {
    serialNumber: "622008881111",
    systemName: "apex-fas-01",
    clusterName: "DAL-RETAIL-01",
    customerName: "Apex Retail Group",
    ontapVersion: "9.11.1",
    platform: "FAS2720 (Store Primary)",
    status: "warning",
    risks: [
      {
        id: 801,
        severity: "medium",
        category: "Software",
        description: "Disk Shelf IOM3 firmware is outdated.",
        recommendation: "Upgrade IOM3 firmware. Refer to KB Article.",
        kbLink: "https://kb.netapp.com",
        remediationPlan: {
          cause: "Outdated firmware baseline.",
          impact: "Soft resets on SAS loops.",
          steps: ["1. Download bundle.", "2. Upload via CLI.", "3. Run background upgrade."],
          options: ["Option A: CLI.", "Option B: System Manager GUI."],
          thirdParty: "None."
        }
      }
    ],
    upgrades: {
      targetVersion: "9.12.1P8",
      urgency: "Recommended",
      benefits: "Improves overall storage shelf stability."
    },
    contracts: {
      status: "warning",
      endDate: "2026-07-20",
      daysRemaining: 14,
      supportLevel: "SupportEdge Standard"
    },
    lifecycle: {
      eoaDate: "2025-12-31",
      eosDate: "2030-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "1.8:1",
      logicalUsedTB: 54.0,
      physicalUsedTB: 30.0,
      spaceSavedTB: 24.0,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [],
    logistics: {
      deliveryAddress: "400 Store Way, Dallas Store Hub, Dallas, TX 75204, US",
      accessRestrictions: "Retail loading zone. Escort required.",
      shippingAlert: "None"
    },
    contacts: {
      name: "Marcus Aurelius",
      phone: "+1-214-555-0909",
      email: "maurelius@apexretail.com",
      nssUsername: "maurelius_ap"
    },
    salesHealth: {
      accountManager: "Livia Drusilla",
      supportTam: "Cicero",
      sentimentScore: 6.0,
      healthStatus: "Retention Risk",
      upsellPotential: "FAS upgrade swap",
      refreshWindow: "Q3 2026"
    },
    projections: {
      growthRateGBPerDay: 75,
      daysToLimit: 50,
      limitDate: "2026-08-25",
      peakIops: 2400,
      avgLatencyMs: 4.8,
      historicalCapacityMonths: [20.0, 22.0, 24.0, 26.0, 28.0, 30.0],
      projectedCapacityMonths: [32.0, 34.0, 36.0]
    },
    securityBulletins: [],
    supportCases: [
      {
        id: "2009819999",
        title: "Replacement SAS cable failure alert",
        severity: "S3 - Medium",
        status: "Open - NetApp Engineering",
        criticality: "Low operational risk - transient CRC error counts logged, but SAS multipathing is active.",
        nextActionBy: "NetApp Hardware Engineering Level 2 Support",
        createdDate: "2026-07-02",
        lastUpdated: "2026-07-05",
        ownerNotes: "Case opened, replacement cable dispatched."
      }
    ]
  },
  {
    serialNumber: "622008882222",
    systemName: "apex-fas-02",
    clusterName: "DAL-RETAIL-01",
    customerName: "Apex Retail Group",
    ontapVersion: "9.11.1",
    platform: "FAS2720 (Store Backup)",
    status: "normal",
    risks: [],
    upgrades: {
      targetVersion: "9.12.1P8",
      urgency: "None",
      benefits: "Brings feature alignment with apex-fas-01."
    },
    contracts: {
      status: "warning",
      endDate: "2026-07-20",
      daysRemaining: 14,
      supportLevel: "SupportEdge Standard"
    },
    lifecycle: {
      eoaDate: "2025-12-31",
      eosDate: "2030-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "1.8:1",
      logicalUsedTB: 54.0,
      physicalUsedTB: 30.0,
      spaceSavedTB: 24.0,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [],
    logistics: {
      deliveryAddress: "400 Store Way, Dallas Store Hub, Dallas, TX 75204, US",
      accessRestrictions: "Retail loading zone. Escort required.",
      shippingAlert: "None"
    },
    contacts: {
      name: "Marcus Aurelius",
      phone: "+1-214-555-0909",
      email: "maurelius@apexretail.com",
      nssUsername: "maurelius_ap"
    },
    salesHealth: {
      accountManager: "Livia Drusilla",
      supportTam: "Cicero",
      sentimentScore: 6.0,
      healthStatus: "Retention Risk",
      upsellPotential: "FAS upgrade swap",
      refreshWindow: "Q3 2026"
    },
    projections: {
      growthRateGBPerDay: 50,
      daysToLimit: 120,
      limitDate: "2026-11-03",
      peakIops: 1200,
      avgLatencyMs: 5.5,
      historicalCapacityMonths: [20.0, 22.0, 24.0, 26.0, 28.0, 30.0],
      projectedCapacityMonths: [31.5, 33.0, 34.5]
    },
    securityBulletins: [],
    supportCases: []
  },
  {
    serialNumber: "622008883333",
    systemName: "apex-cvo-gcp",
    clusterName: "GCP-CVO-PROD",
    customerName: "Apex Retail Group",
    ontapVersion: "9.13.1",
    platform: "Cloud Volumes ONTAP (GCP)",
    status: "normal",
    risks: [],
    upgrades: {
      targetVersion: "Up to Date",
      urgency: "None",
      benefits: ""
    },
    contracts: {
      status: "normal",
      endDate: "2027-10-10",
      daysRemaining: 461,
      supportLevel: "Cloud Volumes Premium"
    },
    lifecycle: {
      eoaDate: "2028-06-30",
      eosDate: "2033-06-30",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "3.4:1",
      logicalUsedTB: 170.0,
      physicalUsedTB: 50.0,
      spaceSavedTB: 120.0,
      fabricPoolTieredTB: 10.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [],
    logistics: {
      deliveryAddress: "GCP Subnet central-1 (Logical Instance)",
      accessRestrictions: "None",
      shippingAlert: "None"
    },
    contacts: {
      name: "Marcus Aurelius",
      phone: "+1-214-555-0909",
      email: "maurelius@apexretail.com",
      nssUsername: "maurelius_ap"
    },
    salesHealth: {
      accountManager: "Livia Drusilla",
      supportTam: "Cicero",
      sentimentScore: 7.5,
      healthStatus: "Stable",
      upsellPotential: "Expand tiering limits",
      refreshWindow: "Q4 2027"
    },
    projections: {
      growthRateGBPerDay: 190,
      daysToLimit: 220,
      limitDate: "2027-02-11",
      peakIops: 9500,
      avgLatencyMs: 2.8,
      historicalCapacityMonths: [35.0, 38.2, 41.0, 44.0, 47.0, 50.0],
      projectedCapacityMonths: [53.2, 56.4, 59.6]
    },
    securityBulletins: [],
    supportCases: []
  },
  {
    serialNumber: "622008884444",
    systemName: "apex-mc-fc",
    clusterName: "DAL-HOU-METRO",
    customerName: "Apex Retail Group",
    ontapVersion: "9.12.1",
    platform: "FAS9000 MetroCluster FC",
    status: "warning",
    risks: [
      {
        id: 840,
        severity: "medium",
        category: "MetroCluster",
        description: "FC Switch ATTO bridges firmware mismatch detected.",
        recommendation: "Align bridge firmware across sites. Refer to NetApp MetroCluster docs.",
        kbLink: "https://kb.netapp.com",
        remediationPlan: {
          cause: "Bridge firmware versions mismatched.",
          impact: "Possible failover stability delays.",
          steps: ["1. Stage firmware on ATTO bridges.", "2. Perform sequential update."],
          options: ["Option A: Sequential upgrade (Online)."],
          thirdParty: "None."
        }
      }
    ],
    upgrades: {
      targetVersion: "9.12.1P10",
      urgency: "Recommended",
      benefits: "Applies MetroCluster stability patches."
    },
    contracts: {
      status: "normal",
      endDate: "2027-11-30",
      daysRemaining: 512,
      supportLevel: "SupportEdge Premium 4hr"
    },
    lifecycle: {
      eoaDate: "2025-12-31",
      eosDate: "2030-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "2.5:1",
      logicalUsedTB: 350.0,
      physicalUsedTB: 140.0,
      spaceSavedTB: 210.0,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: true,
      relationships: [
        {
          destination: "HOUSTON-REPL (Site B)",
          type: "SyncMirror (Synchronous)",
          schedule: "Immediate",
          status: "In-Sync",
          state: "Snapmirrored",
          lagTime: "0 sec",
          healthy: true
        }
      ]
    },
    hypervisors: [],
    logistics: {
      deliveryAddress: "400 Store Way, Dallas Store Hub | Houston Backup Site, Houston, TX 77001",
      accessRestrictions: "Badged entry. Multi-site logistics coordination required.",
      shippingAlert: "None"
    },
    contacts: {
      name: "Marcus Aurelius",
      phone: "+1-214-555-0909",
      email: "maurelius@apexretail.com",
      nssUsername: "maurelius_ap"
    },
    salesHealth: {
      accountManager: "Livia Drusilla",
      supportTam: "Cicero",
      sentimentScore: 7.0,
      healthStatus: "Stable",
      upsellPotential: "Upgrade to MetroCluster IP systems",
      refreshWindow: "Q4 2027"
    },
    projections: {
      growthRateGBPerDay: 350,
      daysToLimit: 140,
      limitDate: "2026-11-23",
      peakIops: 28500,
      avgLatencyMs: 2.2,
      historicalCapacityMonths: [110.0, 115.0, 122.0, 128.0, 134.0, 140.0],
      projectedCapacityMonths: [149.2, 158.4, 167.6]
    },
    securityBulletins: [],
    supportCases: []
  },
  // NEW CUSTOMER: Federal Aero Systems
  {
    serialNumber: "622009991111",
    systemName: "fed-aff-ultra",
    clusterName: "DC-SECURE-CLUST",
    customerName: "Federal Aero Systems",
    ontapVersion: "9.12.1P8",
    platform: "AFF A900 (High-Security)",
    status: "normal",
    risks: [],
    upgrades: {
      targetVersion: "Up to Date",
      urgency: "None",
      benefits: ""
    },
    contracts: {
      status: "normal",
      endDate: "2030-05-15",
      daysRemaining: 1409,
      supportLevel: "SupportEdge GovSecure"
    },
    lifecycle: {
      eoaDate: "2030-12-31",
      eosDate: "2035-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "4.5:1",
      logicalUsedTB: 450.0,
      physicalUsedTB: 100.0,
      spaceSavedTB: 350.0,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [
      {
        type: "VMware vSphere (Secure)",
        version: "ESXi 8.0 Update 2",
        plugin: "VASA Provider 10.1",
        multipathing: "VMW_PSP_RR",
        health: "Normal"
      }
    ],
    logistics: {
      deliveryAddress: "Building 4, Pentagon Site South, Arlington, VA 22202, US",
      accessRestrictions: "Active Secret clearance, background checks, and escort required. Cell phones prohibited.",
      shippingAlert: "Security checkpoint delays: expect up to 3h delays for courier drop-off."
    },
    contacts: {
      name: "Gen. John Miller",
      phone: "+1-703-555-0111",
      email: "john.miller@fed-aero.gov",
      nssUsername: "jmiller_fed"
    },
    salesHealth: {
      accountManager: "Alexander Hamilton",
      supportTam: "Thomas Jefferson",
      sentimentScore: 10.0,
      healthStatus: "High Satisfaction",
      upsellPotential: "Government cloud integrations",
      refreshWindow: "Q2 2030"
    },
    projections: {
      growthRateGBPerDay: 550,
      daysToLimit: 610,
      limitDate: "2028-03-08",
      peakIops: 45000,
      avgLatencyMs: 1.2,
      historicalCapacityMonths: [80.0, 84.0, 88.0, 92.0, 96.0, 100.0],
      projectedCapacityMonths: [104.2, 108.4, 112.6]
    },
    securityBulletins: [],
    supportCases: []
  },
  {
    serialNumber: "622009992222",
    systemName: "fed-sg-secure",
    clusterName: "DC-SECURE-GRID",
    customerName: "Federal Aero Systems",
    ontapVersion: "11.8.0",
    platform: "StorageGRID SG6060",
    status: "normal",
    risks: [],
    upgrades: {
      targetVersion: "Up to Date",
      urgency: "None",
      benefits: ""
    },
    contracts: {
      status: "normal",
      endDate: "2030-05-15",
      daysRemaining: 1409,
      supportLevel: "SupportEdge GovSecure"
    },
    lifecycle: {
      eoaDate: "2029-12-31",
      eosDate: "2034-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "1.0:1",
      logicalUsedTB: 950.0,
      physicalUsedTB: 950.0,
      spaceSavedTB: 0.0,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [],
    logistics: {
      deliveryAddress: "Building 4, Pentagon Site South, Arlington, VA 22202, US",
      accessRestrictions: "Active Secret clearance, background checks, and escort required. Cell phones prohibited.",
      shippingAlert: "Security checkpoint delays: expect up to 3h delays for courier drop-off."
    },
    contacts: {
      name: "Gen. John Miller",
      phone: "+1-703-555-0111",
      email: "john.miller@fed-aero.gov",
      nssUsername: "jmiller_fed"
    },
    salesHealth: {
      accountManager: "Alexander Hamilton",
      supportTam: "Thomas Jefferson",
      sentimentScore: 9.5,
      healthStatus: "High Satisfaction",
      upsellPotential: "S3 Object lock configuration review",
      refreshWindow: "Q2 2030"
    },
    projections: {
      growthRateGBPerDay: 1200,
      daysToLimit: 320,
      limitDate: "2027-05-22",
      peakIops: 12400,
      avgLatencyMs: 6.8,
      historicalCapacityMonths: [800.0, 830.0, 860.0, 890.0, 920.0, 950.0],
      projectedCapacityMonths: [980.0, 1010.0, 1040.0]
    },
    securityBulletins: [],
    supportCases: []
  }
];

(function ensureMultiNodeClusters() {
  const clusterCounts = {};
  MOCK_SYSTEMS.forEach(sys => {
    clusterCounts[sys.clusterName] = (clusterCounts[sys.clusterName] || 0) + 1;
  });

  const singleNodeClusters = Object.keys(clusterCounts).filter(c => clusterCounts[c] === 1);

  const newNodes = [];
  MOCK_SYSTEMS.forEach(sys => {
    if (singleNodeClusters.includes(sys.clusterName)) {
      let partnerSerialNum = parseInt(sys.serialNumber) || 0;
      partnerSerialNum = partnerSerialNum + 1;
      const partnerSerial = partnerSerialNum.toString();
      
      let origName = sys.systemName;
      if (!origName.endsWith("-a") && !origName.endsWith("-01")) {
        sys.systemName = `${origName}-a`;
      }
      
      const partnerName = sys.systemName.replace(/-a$/, "-b").replace(/-01$/, "-02");
      
      const partnerNode = {
        ...sys,
        serialNumber: partnerSerial,
        systemName: partnerName,
        status: "normal",
        risks: [],
        switches: sys.switches ? sys.switches.map(sw => ({
          ...sw,
          serialNumber: sw.serialNumber + "-B"
        })) : undefined,
        contracts: {
          ...sys.contracts,
          daysRemaining: sys.contracts.daysRemaining + 2
        },
        efficiency: {
          ...sys.efficiency,
          logicalUsedTB: sys.efficiency.logicalUsedTB * 0.9,
          physicalUsedTB: sys.efficiency.physicalUsedTB * 0.9,
          spaceSavedTB: sys.efficiency.spaceSavedTB * 0.9
        }
      };
      newNodes.push(partnerNode);
    }
  });

  MOCK_SYSTEMS.push(...newNodes);
})();

// Dynamically generate additional systems to reach approximately 50 systems (with new customers)
(function generateExtraMockData() {
  const extraCustomers = [
    "RetailGiant Corp",
    "AutoDrive Labs",
    "MediaStream Inc",
    "EduCloud Academy",
    "FinServices Ltd",
    "BioTech Research",
    "EnergyGrid Co",
    "TeleCom Global"
  ];
  
  const platforms = [
    "AFF A400 (On-Prem)",
    "FAS8700 (On-Prem)",
    "Cloud Volumes ONTAP (AWS)",
    "Cloud Volumes ONTAP (Azure)",
    "StorageGRID SG6060",
    "AFF A900 (On-Prem)",
    "FAS2750 (On-Prem)",
    "AFF A250 (On-Prem)",
    "AFF A400 (MetroCluster IP)",
    "FAS8700 (MetroCluster FC)"
  ];
  
  const statuses = ["normal", "normal", "normal", "normal", "warning", "warning", "critical"];
  
  const ontapVersions = ["9.12.1P4", "9.11.1P8", "9.13.1P8", "9.10.1P12", "11.8.0", "9.14.1P2"];

  for (let i = 1; i <= 54; i++) {
    const custIndex = i % extraCustomers.length;
    const customer = extraCustomers[custIndex];
    const serial = (722000000000 + i).toString();
    const platIndex = i % platforms.length;
    const platform = platforms[platIndex];
    const status = statuses[i % statuses.length];
    
    const sysName = `${customer.toLowerCase().split(" ")[0]}-${platform.toLowerCase().substring(0, 3)}-0${Math.ceil(i/8)}`;
    const clusterName = `${customer.toUpperCase().split(" ")[0]}-CLUSTER-0${Math.ceil(i/8)}`;
    
    const risks = [];
    if (status === "critical") {
      const critScenario = i % 4;
      if (critScenario === 0) {
        risks.push({
          id: 200 + i,
          severity: "critical",
          category: "Hardware",
          description: "Multiple disk drive failures detected in Aggregate rg0.",
          recommendation: "Replace disk drives in slots 3 and 7 immediately. Refer to KB990211.",
          kbLink: "https://kb.netapp.com",
          remediationPlan: {
            cause: "Double disk failure on shelf 1 within RAID-DP group.",
            impact: "Aggregates are currently running in degraded state. A third disk failure will cause complete data loss.",
            steps: ["1. Order replacement disks.", "2. Replace disk 3.", "3. Wait for reconstruction.", "4. Replace disk 7."],
            options: ["Option A: Non-disruptive online hot-swap.", "Option B: Contact NetApp Support for dispatch."],
            thirdParty: "No external hypervisor impacts."
          }
        });
      } else if (critScenario === 1) {
        risks.push({
          id: 200 + i,
          severity: "critical",
          category: "Hardware",
          description: "SAS initiator port reset threshold exceeded on Controller A.",
          recommendation: "Inspect SAS cable connections between controller port 2a and shelf 1 port A. Swap SAS cable if errors persist.",
          kbLink: "https://kb.netapp.com",
          remediationPlan: {
            cause: "Degraded SAS link signaling causing port resets on port 2a.",
            impact: "SAS path redundancy lost. A secondary failure on path B will disrupt active storage access.",
            steps: ["1. Identify shelf ports.", "2. Re-seat SAS cable.", "3. Run CLI command: 'storage port show -port 2a' to verify link status."],
            options: ["Option A: Non-disruptive cable re-seat.", "Option B: Order replacement SAS cable."],
            thirdParty: "No impact on hypervisors."
          }
        });
      } else if (critScenario === 2) {
        risks.push({
          id: 200 + i,
          severity: "critical",
          category: "Software",
          description: "MetroCluster IP configuration synchronization failed.",
          recommendation: "Force site-to-site configuration sync. Upgrade firmware to resolve sync race condition.",
          kbLink: "https://kb.netapp.com",
          remediationPlan: {
            cause: "Sync timeout between local and remote site NVRAM logs.",
            impact: "Automatic unplanned switchover disabled. MetroCluster protection is compromised.",
            steps: ["1. Run 'metrocluster operation show'.", "2. Force sync using 'metrocluster configure syncforce'."],
            options: ["Option A: Non-disruptive syncforce CLI.", "Option B: Contact Support."],
            thirdParty: "VMware vSphere vMSC configuration will alert on path status."
          }
        });
      } else {
        risks.push({
          id: 200 + i,
          severity: "critical",
          category: "Hardware",
          description: "HA interconnect link status degraded (link 1 down).",
          recommendation: "Replace faulty SFP+ module on cluster interconnect switch port 5.",
          kbLink: "https://kb.netapp.com",
          remediationPlan: {
            cause: "Faulty physical SFP transceiver module on internal fabric interface.",
            impact: "Loss of HA failover synchronization path. Storage takeover capacity is impaired.",
            steps: ["1. Identify controller SFP.", "2. Hot-swap SFP module on switch port 5.", "3. Verify link status."],
            options: ["Option A: Online SFP hot-swap.", "Option B: Switch port reallocation."],
            thirdParty: "No hypervisor impact."
          }
        });
      }
    } else if (status === "warning") {
      const warnScenario = i % 4;
      if (warnScenario === 0) {
        risks.push({
          id: 300 + i,
          severity: "medium",
          category: "Software",
          description: "ONTAP upgrade advised to address TLS vulnerability.",
          recommendation: "Upgrade ONTAP to version 9.13.1 or newer.",
          kbLink: "https://kb.netapp.com",
          remediationPlan: {
            cause: "Older ONTAP version contains vulnerable TLS 1.0/1.1 protocols.",
            impact: "Non-compliance with PCI-DSS security standards.",
            steps: ["1. Perform Upgrade Advisor check.", "2. Update ONTAP cluster non-disruptively."],
            options: ["Option A: Upgrade ONTAP.", "Option B: Disable TLS 1.0 manually."],
            thirdParty: "Requires storage plugin compatibility checks."
          }
        });
      } else if (warnScenario === 1) {
        risks.push({
          id: 300 + i,
          severity: "medium",
          category: "Configuration",
          description: "NTP server synchronization drift exceeds 500ms.",
          recommendation: "Reconfigure cluster time synchronization with reliable active directory NTP server.",
          kbLink: "https://kb.netapp.com",
          remediationPlan: {
            cause: "Network latency or firewall blocking UDP port 123 to current server.",
            impact: "Disruptions in Kerberos authentication and active directory integration.",
            steps: ["1. Verify NTP server ping.", "2. Modify NTP server: 'cluster time-service ntp server modify -server time.windows.com'."],
            options: ["Option A: Set local AD server.", "Option B: Configure external pool NTP servers."],
            thirdParty: "Active directory integrated hypervisors will fail CIFS file share authentications."
          }
        });
      } else if (warnScenario === 2) {
        risks.push({
          id: 300 + i,
          severity: "medium",
          category: "Firmware",
          description: "Disk Shelf IOM12 firmware is outdated (current: 0240, target: 0260).",
          recommendation: "Schedule a non-disruptive shelf firmware upgrade using ONTAP System Manager.",
          kbLink: "https://kb.netapp.com",
          remediationPlan: {
            cause: "Shelf module firmware drift behind validated baseline.",
            impact: "Risk of soft path resets under heavy transactional traffic.",
            steps: ["1. Download firmware bundle.", "2. Upload via CLI.", "3. Run background upgrade."],
            options: ["Option A: Automated update.", "Option B: CLI background update."],
            thirdParty: "Ensure ESXi queue depths are configured correctly."
          }
        });
      } else {
        risks.push({
          id: 300 + i,
          severity: "medium",
          category: "Configuration",
          description: "Aggregates utilization exceeds 85% capacity threshold.",
          recommendation: "Initiate volume relocation to less utilized aggregate or enable thin provisioning.",
          kbLink: "https://kb.netapp.com",
          remediationPlan: {
            cause: "Unplanned storage growth in local snapshot copies.",
            impact: "Potential read-only fail-safes if aggregates fill to 100%.",
            steps: ["1. Identify thick-provisioned volumes.", "2. Convert to thin-provisioned or move volumes to node 2 aggregates."],
            options: ["Option A: Relocate volumes non-disruptively.", "Option B: Reclaim space by deleting snapshots."],
            thirdParty: "Virtual machine provisionings will fail."
          }
        });
      }
    }
    
    const daysRemaining = (i % 2 === 0) ? (30 + (i * 12)) : -(i * 2);
    const contractsStatus = daysRemaining < 0 ? "critical" : (daysRemaining <= 90 ? "warning" : "normal");
    const endDate = new Date(Date.now() + daysRemaining * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

    // Generate Switches configuration
    const switches = [];
    if (platform.includes("MetroCluster")) {
      switches.push({
        type: "MetroCluster Back-end",
        model: platform.includes("IP") ? "Cisco Nexus 9336C-FX2" : "Brocade G620 FC",
        serialNumber: `SW-MC-${serial.substring(6)}A`,
        firmware: i % 3 === 0 ? "9.3(8)" : "9.3(12)",
        targetFirmware: "9.3(12)",
        status: i % 3 === 0 ? "Warning" : "Optimal",
        ipAddress: `192.168.50.${100 + i}`,
        validationDetails: i % 3 === 0 ? "Firmware drift: NX-OS 9.3(8) is below the minimum Interoperability Matrix Tool (IMT) validated version." : "Optimal connection."
      });
      switches.push({
        type: "Cluster Interconnect",
        model: "Cisco Nexus 3132Q-V",
        serialNumber: `SW-CI-${serial.substring(6)}B`,
        firmware: "9.3(12)",
        targetFirmware: "9.3(12)",
        status: "Optimal",
        ipAddress: `192.168.50.${120 + i}`,
        validationDetails: "Optimal connection."
      });
      switches.push({
        type: "Front-end Storage",
        model: "Cisco MDS 9148T",
        serialNumber: `SW-FE-${serial.substring(6)}C`,
        firmware: i % 4 === 0 ? "8.4(2)" : "9.2(2)",
        targetFirmware: "9.2(2)",
        status: i % 4 === 0 ? "Warning" : "Optimal",
        ipAddress: `10.10.20.${150 + i}`,
        validationDetails: i % 4 === 0 ? "Firmware warning: MDS-OS v8.4(2) contains security vulnerability CVE-2023-20092. Upgrade advised." : "Optimal connection."
      });
    } else if (platform.includes("On-Prem")) {
      switches.push({
        type: "Cluster Interconnect",
        model: i % 5 === 0 ? "Broadcom BES-53248" : "Cisco Nexus 3132Q-V",
        serialNumber: `SW-CI-${serial.substring(6)}A`,
        firmware: i % 5 === 0 ? "EFOS 3.4.4.6" : "NX-OS 9.3(10)",
        targetFirmware: i % 5 === 0 ? "EFOS 3.8.0.2" : "NX-OS 9.3(12)",
        status: i % 5 === 0 ? "Warning" : (i % 7 === 0 ? "Critical" : "Optimal"),
        ipAddress: `192.168.60.${100 + i}`,
        validationDetails: i % 5 === 0 
          ? "Firmware drift detected: EFOS 3.4 is out of sync." 
          : (i % 7 === 0 ? "Critical Bug Alert: NX-OS 9.3(10) has a memory leak in ports telemetry. Urgent upgrade required." : "Optimal connection.")
      });
      switches.push({
        type: "Front-end Data",
        model: "Cisco Nexus 93180YC-FX",
        serialNumber: `SW-FE-${serial.substring(6)}B`,
        firmware: "9.3(12)",
        targetFirmware: "9.3(12)",
        status: "Optimal",
        ipAddress: `10.10.10.${100 + i}`,
        validationDetails: "Optimal connection."
      });
    } else if (platform.includes("StorageGRID")) {
      switches.push({
        type: "Grid Network",
        model: "Cisco Nexus 93180YC-FX",
        serialNumber: `SW-GRID-${serial.substring(6)}A`,
        firmware: i % 6 === 0 ? "9.3(8)" : "9.3(12)",
        targetFirmware: "9.3(12)",
        status: i % 6 === 0 ? "Warning" : "Optimal",
        ipAddress: `10.50.10.${100 + i}`,
        validationDetails: i % 6 === 0 ? "Firmware warning: upgrade NX-OS to address grid MTU packet loss bugs." : "Optimal connection."
      });
    }

    const sys = {
      serialNumber: serial,
      systemName: sysName,
      clusterName: clusterName,
      customerName: customer,
      ontapVersion: ontapVersions[i % ontapVersions.length],
      platform: platform,
      status: status,
      risks: risks,
      switches: switches,
      upgrades: {
        targetVersion: status === "normal" ? "Up to Date" : "9.13.1P8",
        urgency: status === "normal" ? "None" : "Recommended",
        benefits: "Enhances security standards and fixes multi-path signal checks."
      },
      contracts: {
        status: contractsStatus,
        endDate: endDate,
        daysRemaining: daysRemaining,
        supportLevel: "SupportEdge Premium"
      },
      lifecycle: {
        eoaDate: "2028-12-31",
        eosDate: "2033-12-31",
        isNearEos: false
      },
      fieldActions: [],
      efficiency: {
        ratio: "3.5:1",
        logicalUsedTB: 50.0 + (i * 5),
        physicalUsedTB: 15.0 + i,
        spaceSavedTB: 35.0 + (i * 4),
        fabricPoolTieredTB: (i % 3 === 0) ? (5.0 + i) : 0.0
      },
      snapmirror: {
        enabled: (i % 4 === 0),
        relationships: (i % 4 === 0) ? [
          {
            destination: `backup-cvo-${i}`,
            type: "XDP",
            schedule: "daily",
            status: "Mirrored",
            state: "Snapmirrored",
            lagTime: "3 hours",
            healthy: true
          }
        ] : []
      },
      hypervisors: (i % 3 === 0) ? [
        {
          type: "VMware vSphere",
          version: "ESXi 8.0",
          plugin: "VASA Provider 10.1",
          multipathing: "VMW_PSP_RR",
          health: "Normal"
        }
      ] : [],
      logistics: {
        deliveryAddress: `Warehouse ${i}, Tech Boulevard, Suite ${100 + i}, Silicon Valley, CA, US`,
        accessRestrictions: "General business hours. Escort required.",
        shippingAlert: "None"
      },
      contacts: {
        name: `Engineer ${i}`,
        phone: `+1-408-555-00${i}`,
        email: `ops-${i}@${customer.toLowerCase().split(" ")[0]}.com`,
        nssUsername: `nss_user_${i}`
      },
      salesHealth: {
        accountManager: "David Vance",
        supportTam: "Marcus Vance",
        sentimentScore: 8.0,
        healthStatus: "Stable",
        upsellPotential: "AFF capacity extension shelves",
        refreshWindow: "Q2 2028"
      },
      projections: {
        growthRateGBPerDay: 80 + i,
        daysToLimit: 120 + (i * 2),
        limitDate: new Date(Date.now() + (120 + (i * 2)) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        peakIops: 8000 + (i * 500),
        avgLatencyMs: 1.5,
        historicalCapacityMonths: [10, 11, 12, 13, 14, 15],
        projectedCapacityMonths: [16, 17, 18]
      },
      securityBulletins: [],
      supportCases: (i % 7 === 2) ? [
        (i % 3 === 0) ? {
          id: `200982${1000 + i}`,
          title: "S3 API Bucket read timeout errors in Grid node 3",
          severity: "S2 - Major",
          status: "Open - NetApp Engineering",
          criticality: "High risk - read latency spikes impacting Hadoop/Spark analytic processing speed.",
          nextActionBy: "NetApp Software Engineering Team",
          createdDate: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          lastUpdated: new Date().toISOString().split('T')[0],
          ownerNotes: "Investigating StorageGRID heap allocation limits for S3 metadata servers."
        } : (i % 3 === 1 ? {
          id: `200982${2000 + i}`,
          title: "NVMe over Fabrics (NVMe/FC) target port link flap",
          severity: "S1 - Critical",
          status: "Open - Customer Action",
          criticality: "Critical risk - host path failover occurred. A secondary link flap on port 1b will drop storage paths.",
          nextActionBy: "Customer SAN/Switch Operations Desk",
          createdDate: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          lastUpdated: new Date().toISOString().split('T')[0],
          ownerNotes: "Advised customer to inspect fibre channel port alignments and clean transceivers."
        } : {
          id: `200982${3000 + i}`,
          title: "Volume snapshot autodelete rule failure",
          severity: "S3 - Medium",
          status: "Open - NetApp Support",
          criticality: "Low risk - volume has 18% remaining capacity, no immediate read-only lock threat.",
          nextActionBy: "NetApp Support Core Team Specialist",
          createdDate: new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          lastUpdated: new Date().toISOString().split('T')[0],
          ownerNotes: "Evaluating ONTAP snapshot retention policy to check for active SnapMirror locks."
        })
      ] : []
    };

    MOCK_SYSTEMS.push(sys);

    // Generate Node B partner to ensure HA pair configuration in all clusters
    if (true) {
      const partnerSerial = (722000000000 + i + 500).toString();
      const partnerSysName = sysName.endsWith("a") ? sysName.replace(/a$/, "b") : `${sysName}b`;
      
      const partnerSys = {
        ...sys,
        serialNumber: partnerSerial,
        systemName: partnerSysName,
        supportCases: [],
        switches: sys.switches.map(sw => ({
          ...sw,
          serialNumber: sw.serialNumber.replace(serial.substring(6), partnerSerial.substring(6))
        })),
        contracts: {
          ...sys.contracts,
          daysRemaining: sys.contracts.daysRemaining + 1
        },
        efficiency: {
          ...sys.efficiency,
          logicalUsedTB: sys.efficiency.logicalUsedTB * 0.95,
          physicalUsedTB: sys.efficiency.physicalUsedTB * 0.95,
          spaceSavedTB: sys.efficiency.spaceSavedTB * 0.95
        }
      };
      
      if (!sys.systemName.endsWith("a")) {
        sys.systemName = `${sys.systemName}a`;
      }
      
      MOCK_SYSTEMS.push(partnerSys);
    }
  }
})();


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

const MOCK_WATCHLISTS = [
  {
    id: "wl_prod",
    name: "Production Clusters Watchlist",
    systemSerials: ["622001234567", "622007771111", "622009998888"]
  },
  {
    id: "wl_cvo",
    name: "Cloud CVO Watchlist",
    systemSerials: ["622002223333"]
  },
  {
    id: "wl_critical",
    name: "Critical Attention Watchlist",
    systemSerials: ["622005557777", "622008881111"]
  },
  {
    id: "wl_storagegrid",
    name: "StorageGRID Infra Watchlist",
    systemSerials: ["622003334444"]
  },
  {
    id: "wl_metrocluster",
    name: "MetroCluster DR Watchlist",
    systemSerials: ["622007771111", "622007772222", "622007773333"]
  }
];

// 2. Global State Variable
let state = {
  currentTab: "overview",
  mockMode: true,
  systems: [...MOCK_SYSTEMS],
  groups: [...DEFAULT_GROUPS],
  watchlists: [],
  selectedSystem: MOCK_SYSTEMS[0],
  selectedTAMSerials: [],
  activeVisualizerNodeSerial: "",
  activeSearchQuery: "",
  activeFilterType: "ALL", // "ALL", "CUSTOMER", "GROUP", "WATCHLIST"
  activeFilterValue: "",   // Customer Name, Group ID, or Watchlist ID
  overviewSortKey: "systemName",
  overviewSortOrder: "asc",
  activeKpiFilter: "NONE", // "NONE", "ALL", "CRITICAL", "WARNING", "CONTRACT"
  
  // Sort states for sub-tab tables
  tamRisksSortKey: "severity",
  tamRisksSortOrder: "asc",
  tamSwitchesSortKey: "systemName",
  tamSwitchesSortOrder: "asc",
  tamSecuritySortKey: "severity",
  tamSecuritySortOrder: "asc",
  samCasesSortKey: "severity",
  samCasesSortOrder: "asc",
  samFieldActionsSortKey: "id",
  samFieldActionsSortOrder: "asc"
};
window.state = state;

// Safe localStorage wrappers to prevent DOMException under local file:// protocol
function safeGetItem(key) {
  try {
    return localStorage.getItem(key);
  } catch (e) {
    console.warn("Storage access blocked:", e);
    return null;
  }
}

function safeSetItem(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (e) {
    console.warn("Storage write blocked:", e);
  }
}

// 3. Storage & Groups Helpers
function loadConfig() {
  const mockModeVal = safeGetItem("aiq_mock_mode");
  state.mockMode = mockModeVal === null ? true : mockModeVal === "true";
  
  const refresh = safeGetItem("aiq_refresh_token") || "";
  const access = safeGetItem("aiq_access_token") || "";
  const expiry = safeGetItem("aiq_token_expiry") || "";
  
  // Safeguard: If mockMode is false but no API token is configured, auto-enable mock mode
  if (!state.mockMode && !refresh) {
    state.mockMode = true;
    safeSetItem("aiq_mock_mode", "true");
  }
  
  // Load systems db if exists in local storage
  const schemaVer = safeGetItem("aiq_systems_schema_v4");
  const savedSystems = safeGetItem("aiq_systems_db");
  
  if (savedSystems && schemaVer === "v4") {
    try {
      const parsed = JSON.parse(savedSystems);
      if (Array.isArray(parsed) && parsed.length >= MOCK_SYSTEMS.length) {
        state.systems = parsed;
      } else {
        state.systems = [...MOCK_SYSTEMS];
        saveSystems();
      }
    } catch (e) {
      console.warn("Failed to parse saved systems, falling back to mock systems:", e);
      state.systems = [...MOCK_SYSTEMS];
      saveSystems();
    }
  } else {
    state.systems = [...MOCK_SYSTEMS];
    safeSetItem("aiq_systems_schema_v4", "v4");
    saveSystems();
  }

  // Pick first system as selected
  if (state.systems.length > 0) {
    state.selectedSystem = state.systems[0];
  }

  // Load groups
  const savedGroups = safeGetItem("aiq_custom_groups");
  if (savedGroups) {
    try {
      state.groups = JSON.parse(savedGroups);
    } catch (e) {
      console.warn("Failed to parse custom groups, falling back to defaults:", e);
      state.groups = [...DEFAULT_GROUPS];
    }
  } else {
    state.groups = [...DEFAULT_GROUPS];
  }

  // Load watchlists
  const savedWatchlists = safeGetItem("aiq_watchlists_db");
  if (savedWatchlists) {
    try {
      state.watchlists = JSON.parse(savedWatchlists);
      if (state.watchlists.length < MOCK_WATCHLISTS.length) {
        state.watchlists = [...MOCK_WATCHLISTS];
      }
    } catch (e) {
      console.warn("Failed to parse watchlists, falling back to defaults:", e);
      state.watchlists = [...MOCK_WATCHLISTS];
    }
  } else {
    state.watchlists = [...MOCK_WATCHLISTS];
  }
  
  return { refresh, access, expiry };
}

function saveConfig(refresh, access, expiry) {
  safeSetItem("aiq_refresh_token", refresh);
  safeSetItem("aiq_access_token", access);
  safeSetItem("aiq_token_expiry", expiry);
}

function saveSystems() {
  safeSetItem("aiq_systems_db", JSON.stringify(state.systems));
  updateSearchSuggestions();
}

function saveGroups() {
  safeSetItem("aiq_custom_groups", JSON.stringify(state.groups));
}

function saveWatchlists() {
  safeSetItem("aiq_watchlists_db", JSON.stringify(state.watchlists));
}

function setMockMode(val) {
  state.mockMode = val;
  safeSetItem("aiq_mock_mode", val.toString());
  updateStatusIndicators();
}

// 4. Token & API Client Logic
async function getValidAccessToken() {
  if (state.mockMode) return "mock-token-abc-123";
  
  const refresh = safeGetItem("aiq_refresh_token");
  const access = safeGetItem("aiq_access_token");
  const expiry = parseFloat(safeGetItem("aiq_token_expiry") || "0");

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

// Global GraphQL fetch client dispatcher
async function callActiveIQGraphQL(query, variables = {}) {
  if (state.mockMode) {
    // Wrap inside a promise to simulate network latency
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve(simulateMockGraphQLResponse(query, variables));
      }, 150);
    });
  }
  
  try {
    const token = await getValidAccessToken();
    const response = await fetch("/graphql", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ query, variables })
    });
    
    if (!response.ok) {
      throw new Error(`GraphQL API returned error: ${response.status} ${response.statusText}`);
    }
    const result = await response.json();
    if (result.errors) {
      throw new Error(result.errors.map(e => e.message).join(", "));
    }
    return result.data;
  } catch (error) {
    console.error("Active IQ GraphQL Fetch Error: ", error);
    throw error;
  }
}

// Local mock resolver simulating dynamic GraphQL resolution
function simulateMockGraphQLResponse(query, variables = {}) {
  let filtered = [...state.systems];
  
  // Extract query filters from variables or query body
  if (variables.customerName) {
    filtered = filtered.filter(s => s.customerName === variables.customerName);
  } else if (variables.serialNumber) {
    filtered = filtered.filter(s => s.serialNumber === variables.serialNumber);
  } else {
    const custMatch = query.match(/customerName:\s*"([^"]+)"/);
    if (custMatch) {
      filtered = filtered.filter(s => s.customerName === custMatch[1]);
    }
    const serialMatch = query.match(/serialNumber:\s*"([^"]+)"/);
    if (serialMatch) {
      filtered = filtered.filter(s => s.serialNumber === serialMatch[1]);
    }
  }
  
  // Clean query string to perform field matching checks
  const cleanQuery = query.replace(/\s+/g, "");
  
  const resultSystems = filtered.map(sys => {
    const resolvedSys = {};
    
    // Select dynamic system fields based on GraphQL selection set query pattern
    if (cleanQuery.includes("serialNumber")) resolvedSys.serialNumber = sys.serialNumber;
    if (cleanQuery.includes("systemName")) resolvedSys.systemName = sys.systemName;
    if (cleanQuery.includes("clusterName")) resolvedSys.clusterName = sys.clusterName;
    if (cleanQuery.includes("customerName")) resolvedSys.customerName = sys.customerName;
    if (cleanQuery.includes("platform")) resolvedSys.platform = sys.platform;
    if (cleanQuery.includes("status")) resolvedSys.status = sys.status;
    if (cleanQuery.includes("ontapVersion")) resolvedSys.ontapVersion = sys.ontapVersion;
    
    if (cleanQuery.includes("contracts")) resolvedSys.contracts = sys.contracts;
    if (cleanQuery.includes("supportCases")) resolvedSys.supportCases = sys.supportCases;
    if (cleanQuery.includes("risks")) resolvedSys.risks = sys.risks;
    if (cleanQuery.includes("projections")) resolvedSys.projections = sys.projections;
    if (cleanQuery.includes("switches")) resolvedSys.switches = sys.switches;
    
    // Default fallback if no fields were parsed
    if (Object.keys(resolvedSys).length === 0) {
      return {
        serialNumber: sys.serialNumber,
        systemName: sys.systemName,
        platform: sys.platform,
        status: sys.status
      };
    }
    return resolvedSys;
  });
  
  return {
    systems: resultSystems
  };
}

function simulateMockAPIResponse(endpoint) {
  if (endpoint.includes("/systems")) {
    const parts = endpoint.split("/");
    if (parts.length > 2) {
      const serial = parts[2];
      return state.systems.find(s => s.serialNumber === serial) || state.systems[0];
    }
    return state.systems;
  }
  return {};
}

// 5. DOM Render Utilities & Charts
let efficiencyChartInstance = null;
let capacityChartInstance = null;
let projectionsChartInstance = null; // Line chart for capacity & performance trends

function renderCharts() {
  const ctxEff = document.getElementById("efficiencyChart");
  const ctxCap = document.getElementById("capacityChart");
  
  if (!ctxEff || !ctxCap) return;
  
  const filteredSystems = getFilteredSystems();
  
  if (filteredSystems.length === 0) {
    if (efficiencyChartInstance) efficiencyChartInstance.destroy();
    if (capacityChartInstance) capacityChartInstance.destroy();
    return;
  }

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

function getFilteredSystems(excludeKpiFilter = false) {
  let filtered = state.systems;

  // 1. Sidebar customer/group/watchlist filters
  if (state.activeFilterType === "CUSTOMER") {
    filtered = state.systems.filter(s => s.customerName === state.activeFilterValue);
  } else if (state.activeFilterType === "GROUP") {
    const group = state.groups.find(g => g.id === state.activeFilterValue);
    if (group) {
      filtered = state.systems.filter(s => group.systemSerials.includes(s.serialNumber));
    }
  } else if (state.activeFilterType === "WATCHLIST") {
    const wl = state.watchlists.find(w => w.id === state.activeFilterValue);
    if (wl) {
      filtered = state.systems.filter(s => wl.systemSerials.includes(s.serialNumber));
    }
  }

  // 2. Main Search Query filter (multi-term support)
  const query = (state.activeSearchQuery || "").toLowerCase().trim();
  if (query) {
    const terms = query.split(",").map(t => t.trim()).filter(t => t.length > 0);
    filtered = filtered.filter(sys => {
      return terms.some(term => 
        sys.systemName.toLowerCase().includes(term) || 
        sys.serialNumber.toLowerCase().includes(term) ||
        sys.clusterName.toLowerCase().includes(term) ||
        sys.customerName.toLowerCase().includes(term) ||
        sys.platform.toLowerCase().includes(term)
      );
    });
  }

  // 3. KPI Card Drill-Down filter (except when calculating the KPI values themselves)
  if (!excludeKpiFilter && state.activeKpiFilter && state.activeKpiFilter !== "NONE") {
    if (state.activeKpiFilter === "CRITICAL") {
      filtered = filtered.filter(s => s.status === "critical" || s.risks.some(r => r.severity === "critical"));
    } else if (state.activeKpiFilter === "WARNING") {
      filtered = filtered.filter(s => s.status === "warning" || s.risks.some(r => r.severity === "high" || r.severity === "medium"));
    } else if (state.activeKpiFilter === "CONTRACT") {
      filtered = filtered.filter(s => s.contracts.daysRemaining <= 90);
    }
  }

  return filtered;
}

function updateOverviewKpis() {
  const filtered = getFilteredSystems(true); // Exclude activeKpiFilter to calculate accurate KPI counts
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
  
  document.getElementById("kpiTotalSystems").style.color = "var(--text-primary)";
  document.getElementById("kpiCriticalRisks").style.color = criticalRisksCount > 0 ? "var(--status-critical)" : "var(--status-normal)";
  document.getElementById("kpiWarningRisks").style.color = warningRisksCount > 0 ? "var(--status-warning)" : "var(--status-normal)";
  document.getElementById("kpiContracts").style.color = expiringContracts > 0 ? "var(--status-warning)" : "var(--status-normal)";
}

function setKpiFilter(filterType) {
  if (state.activeKpiFilter === filterType) {
    state.activeKpiFilter = "NONE"; // toggle off
  } else {
    state.activeKpiFilter = filterType;
  }
  
  // Update visual card active highlight states
  const cards = {
    "ALL": "kpiCardAll",
    "CRITICAL": "kpiCardCritical",
    "WARNING": "kpiCardWarning",
    "CONTRACT": "kpiCardContract"
  };
  
  Object.keys(cards).forEach(key => {
    const el = document.getElementById(cards[key]);
    if (!el) return;
    if (state.activeKpiFilter === key) {
      el.classList.add("active");
    } else {
      el.classList.remove("active");
    }
  });

  // Re-render overview table and switch/update tabs accordingly
  renderOverviewTable();
}

function sortTable(tableId, key) {
  if (arguments.length === 1) {
    key = tableId;
    tableId = "overview";
  }

  const keyProp = `${tableId}SortKey`;
  const orderProp = `${tableId}SortOrder`;
  
  if (state[keyProp] === key) {
    state[orderProp] = state[orderProp] === "asc" ? "desc" : "asc";
  } else {
    state[keyProp] = key;
    state[orderProp] = "asc";
  }

  if (tableId === "overview") {
    renderOverviewTable();
  } else if (tableId === "tamRisks" || tableId === "tamSwitches" || tableId === "tamSecurity") {
    renderTAMTab();
  } else if (tableId === "samCases" || tableId === "samFieldActions") {
    renderSAMTab();
  }
}

function updateSortIndicatorsGeneric(tableId, headersMap) {
  const activeKey = state[`${tableId}SortKey`] || "";
  const activeOrder = state[`${tableId}SortOrder`] || "asc";
  
  Object.keys(headersMap).forEach(key => {
    const el = document.getElementById(headersMap[key]);
    if (!el) return;
    if (activeKey === key) {
      el.innerText = activeOrder === "asc" ? " ▲" : " ▼";
      el.style.opacity = "1";
      el.style.color = "var(--accent-cyan)";
    } else {
      el.innerText = " ↕";
      el.style.opacity = "0.3";
      el.style.color = "inherit";
    }
  });
}

function updateSortIndicators() {
  updateSortIndicatorsGeneric("overview", {
    "systemName": "sort-systemName",
    "serialNumber": "sort-serialNumber",
    "clusterName": "sort-clusterName",
    "customerName": "sort-customerName",
    "platform": "sort-platform",
    "status": "sort-status",
    "contracts.endDate": "sort-contracts-endDate"
  });

  updateSortIndicatorsGeneric("tamRisks", {
    "severity": "sort-tamRisks-severity",
    "category": "sort-tamRisks-category",
    "systemName": "sort-tamRisks-systemName",
    "description": "sort-tamRisks-description"
  });

  updateSortIndicatorsGeneric("tamSwitches", {
    "systemName": "sort-tamSwitches-systemName",
    "model": "sort-tamSwitches-model",
    "type": "sort-tamSwitches-type",
    "firmware": "sort-tamSwitches-firmware",
    "status": "sort-tamSwitches-status"
  });

  updateSortIndicatorsGeneric("tamSecurity", {
    "id": "sort-tamSecurity-id",
    "title": "sort-tamSecurity-title",
    "severity": "sort-tamSecurity-severity",
    "status": "sort-tamSecurity-status"
  });

  updateSortIndicatorsGeneric("samCases", {
    "id": "sort-samCases-id",
    "title": "sort-samCases-title",
    "severity": "sort-samCases-severity",
    "status": "sort-samCases-status",
    "createdDate": "sort-samCases-createdDate"
  });

  updateSortIndicatorsGeneric("samFieldActions", {
    "id": "sort-samFieldActions-id",
    "title": "sort-samFieldActions-title"
  });
}

function sortDataList(list, sortKey, sortOrder) {
  if (!list || !Array.isArray(list)) return;
  list.sort((a, b) => {
    let valA = a;
    let valB = b;

    const keys = sortKey.split(".");
    keys.forEach(k => {
      if (valA) valA = valA[k];
      if (valB) valB = valB[k];
    });

    const strA = valA ? valA.toString().toLowerCase().trim() : "";
    const strB = valB ? valB.toString().toLowerCase().trim() : "";

    const priority = { 
      "critical": 1, "s1": 1, "s1 - critical": 1,
      "high": 2, "s2": 2, "s2 - high": 2, "warning": 2,
      "medium": 3, "s3": 3, "s3 - medium": 3,
      "low": 4, "s4": 4, "s4 - low": 4, "normal": 4, "healthy": 4, "optimal": 4
    };

    let usePriority = false;
    if (sortKey === "status" || sortKey === "severity") {
      if (priority[strA] !== undefined || priority[strB] !== undefined) {
        usePriority = true;
      }
    }

    if (usePriority) {
      const priorityA = priority[strA] !== undefined ? priority[strA] : 99;
      const priorityB = priority[strB] !== undefined ? priority[strB] : 99;
      if (priorityA < priorityB) return sortOrder === "asc" ? -1 : 1;
      if (priorityA > priorityB) return sortOrder === "asc" ? 1 : -1;
      return 0;
    }

    if (valA === undefined || valA === null) valA = "";
    if (valB === undefined || valB === null) valB = "";

    if (typeof valA === "string") valA = valA.toLowerCase();
    if (typeof valB === "string") valB = valB.toLowerCase();

    if (valA < valB) return sortOrder === "asc" ? -1 : 1;
    if (valA > valB) return sortOrder === "asc" ? 1 : -1;
    return 0;
  });
}

function renderOverviewTable() {
  const tbody = document.getElementById("overviewTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const filteredSystems = getFilteredSystems();

  // Sort filteredSystems based on state.overviewSortKey and state.overviewSortOrder
  const sortKey = state.overviewSortKey || "systemName";
  const sortOrder = state.overviewSortOrder || "asc";

  sortDataList(filteredSystems, sortKey, sortOrder);

  // Update visual sort indicators on table headers
  updateSortIndicators();

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

    let nameHtml = sys.systemName;
    if (sys.supportCases && sys.supportCases.length > 0) {
      nameHtml += ` <span class="badge warning" style="font-size: 0.65rem; padding: 2px 4px; vertical-align: middle; margin-left: 4px; background-color: var(--status-info); border-color: rgba(0, 230, 118, 0.2); cursor: pointer;" onclick="navigateToSupportCases('SYSTEM', '${sys.serialNumber}', event)" data-tooltip="Click to view active support cases for this system">✉ ${sys.supportCases.length} Open</span>`;
    }

    tr.innerHTML = `
      <td style="font-weight: 600; color: var(--accent-cyan);">${nameHtml}</td>
      <td>
        <code class="copyable-code" onclick="copyToClipboard('${sys.serialNumber}', event)" title="Click to copy Serial Number">
          ${sys.serialNumber}
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        </code>
      </td>
      <td>${sys.clusterName}</td>
      <td>${sys.customerName}</td>
      <td>${sys.platform}</td>
      <td>${statusBadge}</td>
      <td>${contractText}</td>
    `;
    tbody.appendChild(tr);
  });
}

function selectSystem(serial) {
  const found = state.systems.find(s => s.serialNumber === serial);
  if (found) {
    state.selectedSystem = found;
    state.selectedTAMSerials = [serial];
    switchTab("tam"); // Switch to Technical Audit details on system click
  }
}

function populateSystemSelectors() {
  const currentFiltered = getFilteredSystems();
  
  // Safe check for null/undefined selectedSystem
  const hasSelectedSystem = state.selectedSystem && typeof state.selectedSystem === 'object';
  const selectedSerial = hasSelectedSystem ? state.selectedSystem.serialNumber : null;
  
  if (currentFiltered.length > 0) {
    const isStillInScope = selectedSerial && currentFiltered.some(s => s.serialNumber === selectedSerial);
    if (!isStillInScope) {
      state.selectedSystem = currentFiltered[0];
    }
  } else {
    state.selectedSystem = null;
  }
  
  // Initialize tab selectors if undefined
  if (state.selectedSAMSystemSerial === undefined) state.selectedSAMSystemSerial = "ALL";
  if (state.selectedCSMSystemSerial === undefined) state.selectedCSMSystemSerial = "ALL";
  
  // Prune/initialize selectedTAMSerials based on current scope
  const allSerialsInScope = currentFiltered.map(s => s.serialNumber);
  if (!state.selectedTAMSerials) {
    state.selectedTAMSerials = [];
  }
  
  // Default TAM serials to ALL systems in scope when filter changes
  const hasTAMFilterMismatch = state.selectedTAMSerials.some(ser => !allSerialsInScope.includes(ser)) || 
                                (state.selectedTAMSerials.length === 0 && currentFiltered.length > 0);
  if (hasTAMFilterMismatch) {
    state.selectedTAMSerials = [...allSerialsInScope];
  }
  
  // Populate SAM System Selector
  const samSelect = document.getElementById("samSystemSelect");
  if (samSelect) {
    samSelect.innerHTML = "";
    if (currentFiltered.length > 0) {
      const grpPortfolio = document.createElement("optgroup");
      grpPortfolio.label = "Portfolio View";
      const optAll = document.createElement("option");
      optAll.value = "ALL";
      optAll.innerText = `All Systems (Account View - ${currentFiltered.length} nodes)`;
      if (state.selectedSAMSystemSerial === "ALL") optAll.selected = true;
      grpPortfolio.appendChild(optAll);
      samSelect.appendChild(grpPortfolio);
      
      const uniqueClusters = [...new Set(currentFiltered.map(s => s.clusterName))];
      if (uniqueClusters.length > 0) {
        const grpClusters = document.createElement("optgroup");
        grpClusters.label = "Clusters (Aggregated)";
        uniqueClusters.forEach(clusterName => {
          const clusterNodes = currentFiltered.filter(s => s.clusterName === clusterName);
          const opt = document.createElement("option");
          opt.value = `CLUSTER:${clusterName}`;
          opt.innerText = `Cluster: ${clusterName} (${clusterNodes.length} nodes)`;
          if (state.selectedSAMSystemSerial === `CLUSTER:${clusterName}`) opt.selected = true;
          grpClusters.appendChild(opt);
        });
        samSelect.appendChild(grpClusters);
      }
      
      const grpNodes = document.createElement("optgroup");
      grpNodes.label = "Nodes (Individual)";
      currentFiltered.forEach(sys => {
        const opt = document.createElement("option");
        opt.value = `NODE:${sys.serialNumber}`;
        opt.innerText = `Node: ${sys.systemName} (${sys.platform})`;
        if (state.selectedSAMSystemSerial === `NODE:${sys.serialNumber}` || state.selectedSAMSystemSerial === sys.serialNumber) opt.selected = true;
        grpNodes.appendChild(opt);
      });
      samSelect.appendChild(grpNodes);
    }
    samSelect.onchange = (e) => {
      const val = e.target.value;
      state.selectedSAMSystemSerial = val;
      if (val !== "ALL" && !val.startsWith("CLUSTER:")) {
        const serial = val.startsWith("NODE:") ? val.substring(5) : val;
        const found = state.systems.find(s => s.serialNumber === serial);
        if (found) state.selectedSystem = found;
      }
      switchTab("sam");
    };
  }

  // Populate CSM System Selector
  const csmSelect = document.getElementById("csmSystemSelect");
  if (csmSelect) {
    csmSelect.innerHTML = "";
    if (currentFiltered.length > 0) {
      const grpPortfolio = document.createElement("optgroup");
      grpPortfolio.label = "Portfolio View";
      const optAll = document.createElement("option");
      optAll.value = "ALL";
      optAll.innerText = `All Systems (Account View - ${currentFiltered.length} nodes)`;
      if (state.selectedCSMSystemSerial === "ALL") optAll.selected = true;
      grpPortfolio.appendChild(optAll);
      csmSelect.appendChild(grpPortfolio);
      
      const uniqueClusters = [...new Set(currentFiltered.map(s => s.clusterName))];
      if (uniqueClusters.length > 0) {
        const grpClusters = document.createElement("optgroup");
        grpClusters.label = "Clusters (Aggregated)";
        uniqueClusters.forEach(clusterName => {
          const clusterNodes = currentFiltered.filter(s => s.clusterName === clusterName);
          const opt = document.createElement("option");
          opt.value = `CLUSTER:${clusterName}`;
          opt.innerText = `Cluster: ${clusterName} (${clusterNodes.length} nodes)`;
          if (state.selectedCSMSystemSerial === `CLUSTER:${clusterName}`) opt.selected = true;
          grpClusters.appendChild(opt);
        });
        csmSelect.appendChild(grpClusters);
      }
      
      const grpNodes = document.createElement("optgroup");
      grpNodes.label = "Nodes (Individual)";
      currentFiltered.forEach(sys => {
        const opt = document.createElement("option");
        opt.value = `NODE:${sys.serialNumber}`;
        opt.innerText = `Node: ${sys.systemName} (${sys.platform})`;
        if (state.selectedCSMSystemSerial === `NODE:${sys.serialNumber}` || state.selectedCSMSystemSerial === sys.serialNumber) opt.selected = true;
        grpNodes.appendChild(opt);
      });
      csmSelect.appendChild(grpNodes);
    }
    csmSelect.onchange = (e) => {
      const val = e.target.value;
      state.selectedCSMSystemSerial = val;
      if (val !== "ALL" && !val.startsWith("CLUSTER:")) {
        const serial = val.startsWith("NODE:") ? val.substring(5) : val;
        const found = state.systems.find(s => s.serialNumber === serial);
        if (found) state.selectedSystem = found;
      }
      switchTab("csm");
    };
  }

  // Render custom multi-select checkbox dropdown for Technical Audit
  const customDropdown = document.getElementById("tamMultiSelectDropdown");
  if (customDropdown) {
    customDropdown.innerHTML = "";
    
    if (currentFiltered.length === 0) {
      customDropdown.innerHTML = `<div style="padding: 8px 12px; font-size: 0.8rem; color: var(--text-muted);">No systems in current scope.</div>`;
    } else {
      // Select All Option
      const selectAllDiv = document.createElement("div");
      selectAllDiv.style.padding = "6px 12px";
      selectAllDiv.style.display = "flex";
      selectAllDiv.style.alignItems = "center";
      selectAllDiv.style.gap = "8px";
      selectAllDiv.style.cursor = "pointer";
      selectAllDiv.style.borderBottom = "1px solid var(--border-color)";
      selectAllDiv.style.background = "rgba(255, 255, 255, 0.02)";
      
      const allSelected = allSerialsInScope.length > 0 && allSerialsInScope.every(ser => state.selectedTAMSerials.includes(ser));
      
      selectAllDiv.innerHTML = `
        <input type="checkbox" id="chk_tam_all" ${allSelected ? 'checked' : ''} style="cursor: pointer;">
        <label for="chk_tam_all" style="cursor: pointer; font-weight: 700; font-size: 0.8rem; flex: 1;">Select All Systems</label>
      `;
      selectAllDiv.onclick = (e) => e.stopPropagation();
      
      const selectAllChk = selectAllDiv.querySelector("input");
      selectAllChk.onchange = (e) => {
        if (e.target.checked) {
          state.selectedTAMSerials = [...allSerialsInScope];
        } else {
          state.selectedTAMSerials = [];
        }
        updateTAMSelectLabel();
        renderTAMTab();
      };
      customDropdown.appendChild(selectAllDiv);
      
      // Group systems by cluster
      const clustersMap = new Map();
      currentFiltered.forEach(sys => {
        if (!clustersMap.has(sys.clusterName)) {
          clustersMap.set(sys.clusterName, []);
        }
        clustersMap.get(sys.clusterName).push(sys);
      });
      
      clustersMap.forEach((nodes, clusterName) => {
        const clusterDiv = document.createElement("div");
        clusterDiv.style.padding = "6px 12px";
        clusterDiv.style.background = "rgba(0, 229, 255, 0.02)";
        clusterDiv.style.borderBottom = "1px solid rgba(255, 255, 255, 0.05)";
        clusterDiv.style.display = "flex";
        clusterDiv.style.alignItems = "center";
        clusterDiv.style.gap = "8px";
        clusterDiv.style.cursor = "pointer";
        
        const nodeSerials = nodes.map(n => n.serialNumber);
        const allClusterNodesChecked = nodeSerials.every(ser => state.selectedTAMSerials.includes(ser));
        
        clusterDiv.innerHTML = `
          <input type="checkbox" id="chk_cluster_${clusterName}" ${allClusterNodesChecked ? 'checked' : ''} style="cursor: pointer;">
          <label for="chk_cluster_${clusterName}" style="cursor: pointer; font-weight: 600; font-size: 0.8rem; color: var(--accent-cyan); flex: 1;">
            Cluster: ${clusterName}
          </label>
        `;
        clusterDiv.onclick = (e) => e.stopPropagation();
        
        const clusterChk = clusterDiv.querySelector("input");
        clusterChk.onchange = (e) => {
          if (e.target.checked) {
            nodeSerials.forEach(ser => {
              if (!state.selectedTAMSerials.includes(ser)) {
                state.selectedTAMSerials.push(ser);
              }
            });
          } else {
            state.selectedTAMSerials = state.selectedTAMSerials.filter(ser => !nodeSerials.includes(ser));
          }
          updateTAMSelectLabel();
          renderTAMTab();
        };
        customDropdown.appendChild(clusterDiv);
        
        nodes.forEach(sys => {
          const itemDiv = document.createElement("div");
          itemDiv.style.padding = "6px 12px 6px 28px";
          itemDiv.style.display = "flex";
          itemDiv.style.alignItems = "center";
          itemDiv.style.gap = "8px";
          itemDiv.style.cursor = "pointer";
          
          const isChecked = state.selectedTAMSerials.includes(sys.serialNumber);
          
          itemDiv.innerHTML = `
            <input type="checkbox" value="${sys.serialNumber}" id="chk_tam_${sys.serialNumber}" ${isChecked ? 'checked' : ''} style="cursor: pointer;">
            <label for="chk_tam_${sys.serialNumber}" style="cursor: pointer; font-size: 0.8rem; flex: 1;">Node: ${sys.systemName} (${sys.platform})</label>
          `;
          itemDiv.onclick = (e) => e.stopPropagation();
          
          const chk = itemDiv.querySelector("input");
          chk.onchange = (e) => {
            const serial = sys.serialNumber;
            if (e.target.checked) {
              if (!state.selectedTAMSerials.includes(serial)) {
                state.selectedTAMSerials.push(serial);
              }
            } else {
              state.selectedTAMSerials = state.selectedTAMSerials.filter(s => s !== serial);
            }
            updateTAMSelectLabel();
            renderTAMTab();
          };
          customDropdown.appendChild(itemDiv);
        });
      });
  }
}

updateTAMSelectLabel();
}

function toggleTAMMultiSelect(event) {
  if (event) event.stopPropagation();
  const dropdown = document.getElementById("tamMultiSelectDropdown");
  if (!dropdown) return;
  dropdown.style.display = dropdown.style.display === "none" ? "block" : "none";
}

function updateTAMSelectLabel() {
  const label = document.getElementById("tamMultiSelectLabel");
  if (!label) return;
  const currentFiltered = getFilteredSystems();
  const allSerialsInScope = currentFiltered.map(s => s.serialNumber);
  const activeInScope = state.selectedTAMSerials.filter(ser => allSerialsInScope.includes(ser));
  
  if (activeInScope.length === 0) {
    label.innerText = "No Systems Selected";
  } else if (activeInScope.length === allSerialsInScope.length) {
    label.innerText = `All Systems (${activeInScope.length})`;
  } else if (activeInScope.length === 1) {
    const sys = currentFiltered.find(s => s.serialNumber === activeInScope[0]);
    label.innerText = sys ? sys.systemName : "1 System Selected";
  } else {
    label.innerText = `${activeInScope.length} Systems Selected`;
  }
}

function getLatestSupportedVersion(platform) {
  const p = (platform || "").toLowerCase();
  if (p.includes("storagegrid")) {
    return "StorageGRID 11.9.0";
  } else if (p.includes("cisco") || p.includes("mds") || p.includes("nexus")) {
    return "NX-OS 9.3(12)";
  } else if (p.includes("brocade") || p.includes("switch")) {
    return "Fabric OS (FOS) 9.2.1";
  } else {
    return "ONTAP 9.15.1P1";
  }
}

function openRemediationModal(riskId) {
  let risk = null;
  let ownerSys = null;
  for (const s of state.systems) {
    if (s.risks) {
      risk = s.risks.find(r => r.id === riskId);
      if (risk) {
        ownerSys = s;
        break;
      }
    }
  }
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

  const contextSection = document.getElementById("modalUpgradeContextSection");
  const contextText = document.getElementById("modalDetailUpgradeContext");
  if (contextSection && contextText) {
    if (ownerSys && (risk.category === "Software" || risk.category === "Firmware")) {
      const minVer = ownerSys.upgrades ? ownerSys.upgrades.targetVersion : "Unknown";
      const latestVer = getLatestSupportedVersion(ownerSys.platform);
      contextText.innerHTML = `
        Platform Type: <strong>${ownerSys.platform}</strong><br>
        Current OS/Firmware Version: <strong style="color: var(--text-muted);">${ownerSys.ontapVersion}</strong><br>
        Minimum Required Version (to resolve this issue): <strong style="color: var(--accent-cyan);">${minVer}</strong><br>
        Latest Supported OS Version for Platform: <strong style="color: var(--status-normal);">${latestVer}</strong>
      `;
      contextSection.style.display = "block";
    } else {
      contextSection.style.display = "none";
    }
  }

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
  
  const currentFiltered = getFilteredSystems();
  const allSerialsInScope = currentFiltered.map(s => s.serialNumber);
  
  // Prune/initialize active serials
  const activeSerials = (state.selectedTAMSerials || []).filter(ser => allSerialsInScope.includes(ser));
  
  if (activeSerials.length === 0) {
    document.getElementById("tamRisksTableBody").innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No systems selected in current scope.</td></tr>`;
    document.getElementById("tamUpgradeContainer").innerHTML = "";
    document.getElementById("tamSecurityBulletinsBody").innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No bulletins.</td></tr>`;
    document.getElementById("tamSwitchesTableBody").innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No switch components monitored.</td></tr>`;
    document.getElementById("tamActiveSystem").innerHTML = `<strong>No Systems Selected</strong>`;
    return;
  }
  
  const selectedSystems = state.systems.filter(s => activeSerials.includes(s.serialNumber));
  
  // Render active systems list description and physical cabling node layout
  const visualCard = document.getElementById("tamNodeVisualCard");
  if (selectedSystems.length > 0) {
    if (visualCard) {
      visualCard.style.display = "block";
    }
    
    if (!state.activeVisualizerNodeSerial || !activeSerials.includes(state.activeVisualizerNodeSerial)) {
      state.activeVisualizerNodeSerial = selectedSystems[0].serialNumber;
    }
    
    const activeSys = selectedSystems.find(s => s.serialNumber === state.activeVisualizerNodeSerial) || selectedSystems[0];
    renderNodeVisualLayout(selectedSystems, activeSys);
  } else {
    if (visualCard) {
      visualCard.style.display = "none";
    }
  }

  // Update header text
  if (selectedSystems.length === 1) {
    const sys = selectedSystems[0];
    document.getElementById("tamActiveSystem").innerHTML = `
      <strong>System</strong>: ${sys.systemName} (S/N: <code class="copyable-code" onclick="copyToClipboard('${sys.serialNumber}', event)" title="Click to copy Serial Number">${sys.serialNumber} <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></code>) | <strong>ONTAP</strong>: ${sys.ontapVersion}
    `;
  } else if (selectedSystems.length > 1) {
    const names = selectedSystems.map(s => s.systemName).join(", ");
    document.getElementById("tamActiveSystem").innerHTML = `
      <strong>Selected Systems (${selectedSystems.length})</strong>: <span style="font-size: 0.8rem; color: var(--text-primary);">${names}</span>
    `;
  }
  
  // Compile Combined Risks
  let riskRows = "";
  const allRisks = [];
  selectedSystems.forEach(sys => {
    (sys.risks || []).forEach(r => {
      allRisks.push({ ...r, systemName: sys.systemName });
    });
  });
  
  sortDataList(allRisks, state.tamRisksSortKey, state.tamRisksSortOrder);
  
  if (allRisks.length === 0) {
    riskRows = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No active technical risks found. Systems are fully compliant.</td></tr>`;
  } else {
    allRisks.forEach(r => {
      let sevBadge = `<span class="badge info">${r.severity}</span>`;
      if (r.severity === "critical") sevBadge = `<span class="badge critical">Critical</span>`;
      else if (r.severity === "high") sevBadge = `<span class="badge critical">High</span>`;
      else if (r.severity === "medium") sevBadge = `<span class="badge warning">Medium</span>`;
      else if (r.severity === "low") sevBadge = `<span class="badge info">Low</span>`;
      
      riskRows += `
        <tr>
          <td>${sevBadge}</td>
          <td>
            <div style="font-weight: 600;">${r.category}</div>
            <div style="font-size: 0.72rem; color: var(--accent-cyan); margin-top: 2px;">System: ${r.systemName}</div>
          </td>
          <td>
            <div style="font-weight: 500; margin-bottom: 4px;">${r.description}</div>
            <div style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 6px;">${r.recommendation}</div>
          </td>
          <td>
            <div style="display: flex; gap: 8px;">
              <button class="action-btn" style="font-size: 0.75rem; padding: 6px 12px;" onclick="openRemediationModal(${r.id})" data-tooltip="View detailed step-by-step remediation procedures, action paths, and third-party environment considerations for this risk.">Remediation Plan</button>
              <a class="external-link" style="font-size: 0.75rem; display: flex; align-items: center;" href="${r.kbLink}" target="_blank" onclick="window.open(this.href, '_blank'); return false;">KB Art</a>
            </div>
          </td>
        </tr>
      `;
    });
  }
  document.getElementById("tamRisksTableBody").innerHTML = riskRows;
  
  // Compile Combined OS Upgrades
  const upgradeBox = document.getElementById("tamUpgradeContainer");
  upgradeBox.innerHTML = "";
  
  const upgradeItems = [];
  selectedSystems.forEach(sys => {
    if (sys.upgrades && sys.upgrades.targetVersion !== "Up to Date") {
      upgradeItems.push({
        systemName: sys.systemName,
        currentVersion: sys.ontapVersion,
        targetVersion: sys.upgrades.targetVersion,
        urgency: sys.upgrades.urgency,
        benefits: sys.upgrades.benefits,
        platform: sys.platform
      });
    }
  });
  
  if (upgradeItems.length === 0) {
    upgradeBox.innerHTML = `
      <h3 style="color: var(--status-normal); margin-bottom: 12px;">✓ Systems Up to Date</h3>
      <p style="font-size: 0.9rem; color: var(--text-secondary);">All ${selectedSystems.length} selected systems are currently running fully supported, stable releases. No upgrades required.</p>
    `;
  } else {
    let upgradeHtml = `<h3 style="font-size: 1.05rem; margin-bottom: 16px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">Recommended OS Upgrades</h3>`;
    upgradeItems.forEach(item => {
      const latestVer = getLatestSupportedVersion(item.platform);
      upgradeHtml += `
        <div style="margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px dashed var(--border-color);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <strong style="color: var(--text-primary); font-size: 0.9rem;">${item.systemName}</strong>
            <span class="badge warning">${item.urgency}</span>
          </div>
          <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px; line-height: 1.4;">
            Current: <strong style="color: var(--text-muted);">${item.currentVersion}</strong> | 
            Min. Required (To Fix): <strong style="color: var(--accent-cyan);">${item.targetVersion}</strong> | 
            Latest Supported: <strong style="color: var(--status-normal);">${latestVer}</strong>
          </div>
          <p style="font-size: 0.78rem; color: var(--text-secondary); margin: 0; line-height: 1.4;">${item.benefits}</p>
        </div>
      `;
    });
    upgradeBox.innerHTML = upgradeHtml;
  }
  
  // Compile Combined Switch Validation
  let switchRows = "";
  const allSwitches = [];
  selectedSystems.forEach(sys => {
    const sws = getSystemSwitches(sys);
    sws.forEach(sw => {
      allSwitches.push({ ...sw, systemName: sys.systemName });
    });
  });

  sortDataList(allSwitches, state.tamSwitchesSortKey, state.tamSwitchesSortOrder);

  if (allSwitches.length === 0) {
    switchRows = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No switch components monitored for these platforms.</td></tr>`;
  } else {
    allSwitches.forEach(sw => {
      let statusBadge = `<span class="badge normal">Optimal</span>`;
      if (sw.status === "Critical") statusBadge = `<span class="badge critical">Critical</span>`;
      else if (sw.status === "Warning") statusBadge = `<span class="badge warning">Warning</span>`;
      
      let actionText = "None required. Switch configuration matches validated baseline.";
      if (sw.status === "Warning") {
        actionText = `Plan firmware update to target release: <strong>${sw.targetFirmware}</strong>. Reference IMT baseline.`;
      } else if (sw.status === "Critical") {
        actionText = `<strong style="color: var(--status-critical);">Immediate action required:</strong> Schedule window to install recommended version <strong>${sw.targetFirmware}</strong> to resolve bug or security vulnerability.`;
      }
      
      switchRows += `
        <tr>
          <td><strong style="color: var(--text-primary); font-size: 0.85rem;">${sw.systemName}</strong></td>
          <td>
            <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-primary);">${sw.model}</div>
            <div style="font-size: 0.72rem; color: var(--text-muted); font-family: monospace;">S/N: ${sw.serialNumber}</div>
          </td>
          <td><span style="font-size: 0.8rem; font-weight: 500;">${sw.type}</span></td>
          <td>
            <div style="font-size: 0.8rem; color: var(--text-secondary);">Current: <code style="color: var(--text-muted);">${sw.firmware}</code></div>
            <div style="font-size: 0.8rem; color: var(--accent-cyan);">Target: <code style="color: var(--accent-cyan); font-weight: 600;">${sw.targetFirmware}</code></div>
          </td>
          <td>${statusBadge}</td>
          <td>
            <div style="font-size: 0.8rem; color: var(--text-primary); margin-bottom: 4px;">${sw.validationDetails}</div>
            <div style="font-size: 0.78rem; color: var(--text-secondary); font-style: italic;">${actionText}</div>
          </td>
        </tr>
      `;
    });
  }
  document.getElementById("tamSwitchesTableBody").innerHTML = switchRows;
  
  // Compile Combined Security & Technical Bulletins
  let bulletinRows = "";
  const allBulletins = [];
  selectedSystems.forEach(sys => {
    if (sys.securityBulletins) {
      sys.securityBulletins.forEach(b => {
        allBulletins.push({ ...b, systemName: sys.systemName });
      });
    }
  });
  
  sortDataList(allBulletins, state.tamSecuritySortKey, state.tamSecuritySortOrder);
  
  if (allBulletins.length === 0) {
    bulletinRows = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No active security advisories mapped.</td></tr>`;
  } else {
    allBulletins.forEach(b => {
      let bBadge = `<span class="badge warning">${b.severity}</span>`;
      if (b.severity === "critical") bBadge = `<span class="badge critical">Critical</span>`;
      else if (b.severity === "high") bBadge = `<span class="badge critical">High</span>`;
      
      bulletinRows += `
        <tr>
          <td>
            <strong style="color: var(--accent-cyan); font-family: monospace;">${b.id}</strong>
            <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">${b.systemName}</div>
          </td>
          <td>
            <div style="font-weight: 600; font-size: 0.85rem; margin-bottom: 4px; color: var(--text-primary);">${b.title}</div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.3;">${b.mitigation}</div>
          </td>
          <td>${bBadge}</td>
          <td><code style="color: var(--status-warning); font-size: 0.78rem;">${b.status}</code></td>
        </tr>
      `;
    });
  }
  document.getElementById("tamSecurityBulletinsBody").innerHTML = bulletinRows;
  updateSortIndicators();
}

function getSystemSwitches(sys) {
  if (sys.switches) return sys.switches;
  
  const seed = parseInt(sys.serialNumber) || 0;
  const switches = [];
  
  if (sys.platform.includes("MetroCluster")) {
    switches.push({
      type: "MetroCluster Back-end",
      model: sys.platform.includes("IP") ? "Cisco Nexus 9336C-FX2" : "Brocade G620 FC",
      serialNumber: `SW-MC-${sys.serialNumber.substring(6)}A`,
      firmware: seed % 3 === 0 ? "9.3(8)" : "9.3(12)",
      targetFirmware: "9.3(12)",
      status: seed % 3 === 0 ? "Warning" : "Optimal",
      ipAddress: `192.168.50.100`,
      validationDetails: seed % 3 === 0 ? "Firmware drift: NX-OS 9.3(8) is below the minimum Interoperability Matrix Tool (IMT) validated version." : "Optimal connection."
    });
    switches.push({
      type: "Cluster Interconnect",
      model: "Cisco Nexus 3132Q-V",
      serialNumber: `SW-CI-${sys.serialNumber.substring(6)}B`,
      firmware: "9.3(12)",
      targetFirmware: "9.3(12)",
      status: "Optimal",
      ipAddress: `192.168.50.120`,
      validationDetails: "Optimal connection."
    });
    switches.push({
      type: "Front-end Storage",
      model: "Cisco MDS 9148T",
      serialNumber: `SW-FE-${sys.serialNumber.substring(6)}C`,
      firmware: seed % 4 === 0 ? "8.4(2)" : "9.2(2)",
      targetFirmware: "9.2(2)",
      status: seed % 4 === 0 ? "Warning" : "Optimal",
      ipAddress: `10.10.20.150`,
      validationDetails: seed % 4 === 0 ? "Firmware warning: MDS-OS v8.4(2) contains security vulnerability CVE-2023-20092. Upgrade advised." : "Optimal connection."
    });
  } else if (sys.platform.includes("On-Prem") || sys.platform.includes("FAS") || sys.platform.includes("AFF")) {
    switches.push({
      type: "Cluster Interconnect",
      model: seed % 5 === 0 ? "Broadcom BES-53248" : "Cisco Nexus 3132Q-V",
      serialNumber: `SW-CI-${sys.serialNumber.substring(6)}A`,
      firmware: seed % 5 === 0 ? "EFOS 3.4.4.6" : "NX-OS 9.3(10)",
      targetFirmware: seed % 5 === 0 ? "EFOS 3.8.0.2" : "NX-OS 9.3(12)",
      status: seed % 5 === 0 ? "Warning" : (seed % 7 === 0 ? "Critical" : "Optimal"),
      ipAddress: `192.168.60.100`,
      validationDetails: seed % 5 === 0 
        ? "Firmware drift detected: EFOS 3.4 is out of sync." 
        : (seed % 7 === 0 ? "Critical Bug Alert: NX-OS 9.3(10) has a memory leak in ports telemetry. Urgent upgrade required." : "Optimal connection.")
    });
    switches.push({
      type: "Front-end Data",
      model: "Cisco Nexus 93180YC-FX",
      serialNumber: `SW-FE-${sys.serialNumber.substring(6)}B`,
      firmware: "9.3(12)",
      targetFirmware: "9.3(12)",
      status: "Optimal",
      ipAddress: `10.10.10.100`,
      validationDetails: "Optimal connection."
    });
  } else if (sys.platform.includes("StorageGRID")) {
    switches.push({
      type: "Grid Network",
      model: "Cisco Nexus 93180YC-FX",
      serialNumber: `SW-GRID-${sys.serialNumber.substring(6)}A`,
      firmware: seed % 6 === 0 ? "9.3(8)" : "9.3(12)",
      targetFirmware: "9.3(12)",
      status: seed % 6 === 0 ? "Warning" : "Optimal",
      ipAddress: `10.50.10.100`,
      validationDetails: seed % 6 === 0 ? "Firmware warning: upgrade NX-OS to address grid MTU packet loss bugs." : "Optimal connection."
    });
  }
  
  return switches;
}

function getSystemIntegrations(sys) {
  if (sys.integrations) return sys.integrations;
  
  const seed = parseInt(sys.serialNumber) || 0;
  
  let virtualization = { type: "None", version: "", status: "Not Configured", plugin: "None", multipathing: "None" };
  let database = { type: "None", version: "", status: "Not Configured", details: "None" };
  let backup = { type: "None", version: "", status: "Not Configured", details: "None" };
  
  const modVal = seed % 5;
  
  if (sys.platform.includes("StorageGRID")) {
    virtualization = {
      type: "OpenStack Swift Object",
      version: "Bobcat (v28.0)",
      status: "Optimal",
      plugin: "StorageGRID Keystone integration",
      multipathing: "N/A (HTTPS Object)"
    };
    database = {
      type: "Apache Spark / Hadoop S3A",
      version: "v3.5.0",
      status: "Configured",
      details: "S3A connector configured for high-concurrency object access"
    };
    backup = {
      type: "Commvault Metallic SaaS",
      version: "SaaS Enterprise",
      status: "Optimal",
      details: "S3 Object lock enabled for WORM compliance storage tier"
    };
  } else if (modVal === 0) {
    virtualization = {
      type: "VMware vSphere",
      version: "8.0 Update 2",
      status: "Optimal",
      plugin: "ONTAP Tools for VMware (VASA v10.1)",
      multipathing: "VMW_PSP_RR (Round Robin)"
    };
    database = {
      type: "Oracle Database (RAC)",
      version: "19c (19.21)",
      status: "Configured (dNFS)",
      details: "Direct NFS client active on 25GbE network channels"
    };
    backup = {
      type: "Commvault IntelliSnap",
      version: "v11.32 SP3",
      status: "Optimal",
      details: "IntelliSnap NetApp engine configured with hardware snapshots"
    };
  } else if (modVal === 1) {
    virtualization = {
      type: "Microsoft Hyper-V",
      version: "Windows Server 2022",
      status: "Optimal",
      plugin: "ONTAP VSS Provider for Hyper-V",
      multipathing: "Microsoft MPIO (Round Robin)"
    };
    database = {
      type: "MS SQL Server",
      version: "2022 Enterprise",
      status: "Optimal",
      details: "SnapCenter MSSQL Plug-in v5.0 active with dynamic restores"
    };
    backup = {
      type: "Veritas NetBackup",
      version: "v10.3",
      status: "Configured",
      details: "NetBackup snapshot manager agent deployed on array"
    };
  } else if (modVal === 2) {
    virtualization = {
      type: "Kubernetes (EKS / OpenShift)",
      version: "v1.29",
      status: "Optimal",
      plugin: "NetApp Astra Trident CSI v24.02",
      multipathing: "N/A (CSI Managed)"
    };
    database = {
      type: "SAP HANA",
      version: "2.0 SPS07",
      status: "Configured",
      details: "NFSv4.1 partitions configured with HANA System Replication (HSR)"
    };
    backup = {
      type: "Veeam Backup & Replication",
      version: "v12.1",
      status: "Configured",
      details: "ONTAP hardware snapshot and SnapMirror replication orchestration"
    };
  } else if (modVal === 3) {
    virtualization = {
      type: "OpenStack Cinder",
      version: "Antelope (v2023.2)",
      status: "Optimal",
      plugin: "ONTAP Cinder Unified Driver",
      multipathing: "Multipathd (iSCSI ALUA)"
    };
    database = {
      type: "Apache Spark / PostgreSQL",
      version: "v15.4",
      status: "Configured",
      details: "Spark streaming analytics using ONTAP S3 object storage buckets"
    };
    backup = {
      type: "NetApp SnapCenter",
      version: "v5.0",
      status: "Optimal",
      details: "Native application-consistent snapshot & clone orchestrator"
    };
  } else {
    virtualization = {
      type: "NVIDIA AI BasePOD",
      version: "Kubeflow / Slurm v23.02",
      status: "Optimal",
      plugin: "Astra Trident CSI + GPUDirect Storage (GDS)",
      multipathing: "NFS over RDMA (RoCEv2)"
    };
    database = {
      type: "AI/ML Training Pipeline",
      version: "PyTorch / TensorFlow",
      status: "Configured",
      details: "Massive scale parallel read dataset streaming on local NFS mount points"
    };
    backup = {
      type: "Commvault Metallic SaaS",
      version: "SaaS Enterprise",
      status: "Optimal",
      details: "Active backup targeting ONTAP S3 compliance bucket"
    };
  }
  
  return { virtualization, database, backup };
}

function getSystemWorkloadRecommendations(sys) {
  const ints = getSystemIntegrations(sys);
  const recs = [];
  
  if (sys.platform.includes("MetroCluster")) {
    recs.push(`<strong>[MetroCluster]</strong> Active-Active stretch cluster detected. Best Practice: Configure VMware vSphere HA Admission Control with 50% CPU and memory reservations to ensure failover capacity.`);
    recs.push(`<strong>[MetroCluster]</strong> Best Practice: Verify that automatic unplanned switchover (AUSO) is enabled via ONTAP command: <code>metrocluster operation show</code> to protect against sudden power loss.`);
  }

  // Virtualization Recommendations
  if (ints.virtualization.type.includes("VMware vSphere")) {
    recs.push(`<strong>[VMware]</strong> ONTAP Tools VASA Provider is active. Best Practice: Ensure VAAI (vStorage APIs for Array Integration) is enabled on ESXi hosts to offload copy operations.`);
    recs.push(`<strong>[VMware]</strong> Multipathing is set to Round Robin (VMW_PSP_RR). Best Practice: Modify default path switching from 1000 IOPS to 1 IOPS for optimal performance on SAN LUNs.`);
  } else if (ints.virtualization.type.includes("Microsoft Hyper-V")) {
    recs.push(`<strong>[Hyper-V]</strong> Windows Server MPIO with NetApp DSM/MPIO driver detected. Best Practice: Configure Path Verification Period to 30 seconds to prevent premature path failovers.`);
    recs.push(`<strong>[Hyper-V]</strong> Best Practice: Store virtual machines on SMB3 Continuous Availability (CA) shares with <code>OdxEnabled</code> set to true to offload VM cloning operations.`);
  } else if (ints.virtualization.type.includes("Kubernetes")) {
    recs.push(`<strong>[Kubernetes]</strong> Astra Trident CSI driver is active. Best Practice: Configure storage classes with <code>spaceReserve: none</code> (Thin Provisioning) to utilize ONTAP storage savings.`);
    recs.push(`<strong>[Kubernetes]</strong> Pods mount PVs via NFS. Best Practice: Increase Trident's mount options to use <code>nfsvers=4.1</code> for better locking performance.`);
  } else if (ints.virtualization.type.includes("OpenStack")) {
    recs.push(`<strong>[OpenStack]</strong> ONTAP Cinder driver is configured. Best Practice: Enable Cinder volume multi-attach only for clustered filesystems to prevent partition corruption.`);
    recs.push(`<strong>[OpenStack]</strong> StorageGRID Swift API identity integration. Best Practice: Enable SSL/TLS encryption for all Keystone endpoints to prevent session token sniffing.`);
  } else if (ints.virtualization.type.includes("NVIDIA AI")) {
    recs.push(`<strong>[NVIDIA AI]</strong> GPUDirect Storage (GDS) with NFS over RDMA enabled. Best Practice: Set <code>mount -o rdma,port=20049</code> and ensure RoCEv2 flow control (PFC/ECN) is configured on network switches.`);
    recs.push(`<strong>[NVIDIA AI]</strong> Large scale datasets. Best Practice: Enable ONTAP FlexGroup volumes to distribute unstructured training data across all controller nodes in the cluster.`);
  }
  
  // Database Recommendations
  if (ints.database.type.includes("Oracle Database")) {
    recs.push(`<strong>[Oracle]</strong> Direct NFS (dNFS) is enabled. Best Practice: Configure <code>filesystemio_options=SETALL</code> in init.ora parameter file to enable asynchronous I/O.`);
    recs.push(`<strong>[Oracle]</strong> Best Practice: Distribute data files and redo log files across separate ONTAP aggregates to prevent disk contention.`);
  } else if (ints.database.type.includes("MS SQL Server")) {
    recs.push(`<strong>[MS SQL]</strong> SnapCenter MSSQL plugin is active. Best Practice: Configure SnapCenter policies to perform transaction log backups every 15 minutes, with storage-level verification.`);
    recs.push(`<strong>[MS SQL]</strong> Best Practice: Format SAN LUNs hosting database files with a 64KB NTFS allocation unit size to align with SQL Server's extent architecture.`);
  } else if (ints.database.type.includes("SAP HANA")) {
    recs.push(`<strong>[SAP HANA]</strong> NFSv4 mount detected. Best Practice: Tune mount options to <code>rw,bg,hard,timeo=600,rsize=262144,wsize=262144</code> for optimal latency performance.`);
  } else if (ints.database.type.includes("Spark") || ints.database.type.includes("Hadoop")) {
    recs.push(`<strong>[Hadoop/Spark]</strong> S3A connector detected. Best Practice: Configure the S3A client to use <code>fs.s3a.fast.upload=true</code> to leverage StorageGRID's high-speed uploads.`);
  } else if (ints.database.type.includes("AI/ML Training")) {
    recs.push(`<strong>[AI Workloads]</strong> PyTorch/TensorFlow dataset loading. Best Practice: Configure local read cache on GPU nodes using NFS CacheFilesd (FS-Cache) to reduce redundant network transfers.`);
  }
  
  // Backup Recommendations
  if (ints.backup.type.includes("Veeam")) {
    recs.push(`<strong>[Veeam]</strong> ONTAP Hardware Snapshot Integration is active. Best Practice: Limit the number of concurrent storage snapshots to 5 per volume to prevent ONTAP metadata lock contention.`);
  } else if (ints.backup.type.includes("Commvault IntelliSnap")) {
    recs.push(`<strong>[Commvault]</strong> IntelliSnap NetApp engine is active. Best Practice: Ensure NetApp OCUM/AIQUM portal credentials are up-to-date in Commvault's Array Management.`);
  } else if (ints.backup.type.includes("Veritas")) {
    recs.push(`<strong>[Veritas]</strong> NetBackup Snapshot Manager is active. Best Practice: Create snapshot policies that clean up deleted or orphaned snapshots older than 7 days using the NetApp REST API.`);
  } else if (ints.backup.type.includes("SnapCenter")) {
    recs.push(`<strong>[SnapCenter]</strong> Native application-consistent backups. Best Practice: Schedule backup jobs outside of ONTAP system background processes (such as deduplication or scrub schedules).`);
  } else if (ints.backup.type.includes("Commvault Metallic")) {
    recs.push(`<strong>[Metallic SaaS]</strong> SaaS backup to cloud storage. Best Practice: Enable ONTAP S3 Object Lock (WORM) on bucket destination to protect against ransomware injection.`);
  }
  
  return recs;
}

function renderSAMTab() {
  populateSystemSelectors();
  
  const currentFiltered = getFilteredSystems();
  const targetSAMSystems = [];
  if (state.selectedSAMSystemSerial === "ALL") {
    targetSAMSystems.push(...currentFiltered);
  } else if (state.selectedSAMSystemSerial.startsWith("CLUSTER:")) {
    const cluster = state.selectedSAMSystemSerial.substring(8);
    targetSAMSystems.push(...currentFiltered.filter(s => s.clusterName === cluster));
  } else {
    const serial = state.selectedSAMSystemSerial.startsWith("NODE:") ? state.selectedSAMSystemSerial.substring(5) : state.selectedSAMSystemSerial;
    const found = currentFiltered.find(s => s.serialNumber === serial);
    if (found) targetSAMSystems.push(found);
  }
  
  if (targetSAMSystems.length === 0) {
    document.getElementById("samContractCard").innerHTML = "";
    document.getElementById("samLifecycleCard").innerHTML = "";
    document.getElementById("samHypervisorCard").innerHTML = "";
    document.getElementById("samLogisticsCard").innerHTML = "";
    document.getElementById("samSalesHealthCard").innerHTML = "";
    if (document.getElementById("samWorkloadVirtualization")) document.getElementById("samWorkloadVirtualization").innerHTML = "";
    if (document.getElementById("samWorkloadDatabase")) document.getElementById("samWorkloadDatabase").innerHTML = "";
    if (document.getElementById("samWorkloadBackup")) document.getElementById("samWorkloadBackup").innerHTML = "";
    if (document.getElementById("samWorkloadRecommendations")) document.getElementById("samWorkloadRecommendations").innerHTML = "";
    document.getElementById("samFieldActionsBody").innerHTML = `<tr><td colspan="2" style="text-align: center; color: var(--text-muted);">No systems available in current scope.</td></tr>`;
    document.getElementById("samSupportCasesBody").innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No systems available.</td></tr>`;
    return;
  }

  const isMulti = targetSAMSystems.length > 1;

  if (isMulti) {
    document.getElementById("samActiveSystem").innerHTML = `
      <strong>Selected Systems (${targetSAMSystems.length})</strong>: <span style="font-size: 0.8rem; color: var(--text-primary);">${targetSAMSystems.map(s => s.systemName).join(", ")}</span>
    `;

    // 1. Contract aggregate
    let activeCount = 0, warningCount = 0, criticalCount = 0;
    targetSAMSystems.forEach(s => {
      if (s.contracts.status === "critical") criticalCount++;
      else if (s.contracts.status === "warning") warningCount++;
      else activeCount++;
    });
    let cBadge = `<span class="badge normal">Active</span>`;
    let cColor = "var(--text-primary)";
    if (criticalCount > 0) {
      cBadge = `<span class="badge critical">${criticalCount} Expired</span>`;
      cColor = "var(--status-critical)";
    } else if (warningCount > 0) {
      cBadge = `<span class="badge warning">${warningCount} Expiring</span>`;
      cColor = "var(--status-warning)";
    }
    document.getElementById("samContractCard").innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h4 style="font-size: 0.9rem; color: var(--text-secondary);">Contracts Summary</h4>
        ${cBadge}
      </div>
      <div style="font-size: 1.3rem; font-weight: 700; margin-bottom: 6px; color: ${cColor};">
        ${targetSAMSystems.length} Monitored Contracts
      </div>
      <div style="font-size: 0.8rem; color: var(--text-muted); display: flex; gap: 8px;">
        <span style="color: var(--status-normal);">Active: ${activeCount}</span> | 
        <span style="color: var(--status-warning);">Expiring: ${warningCount}</span> | 
        <span style="color: var(--status-critical);">Expired: ${criticalCount}</span>
      </div>
    `;

    // 2. Lifecycle aggregate
    let nearEosCount = 0;
    targetSAMSystems.forEach(s => {
      if (s.lifecycle && s.lifecycle.isNearEos) nearEosCount++;
    });
    let lBadge = `<span class="badge normal">Active</span>`;
    if (nearEosCount > 0) lBadge = `<span class="badge critical">${nearEosCount} Near EOS</span>`;
    document.getElementById("samLifecycleCard").innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h4 style="font-size: 0.9rem; color: var(--text-secondary);">Lifecycle Summary</h4>
        ${lBadge}
      </div>
      <div style="font-size: 1.25rem; font-weight: 700; margin-bottom: 6px;">
        ${targetSAMSystems.length} Hardware Assets
      </div>
      <div style="font-size: 0.8rem; color: var(--text-muted);">
        Near End-of-Support: <strong style="color: ${nearEosCount > 0 ? "var(--status-critical)" : "var(--status-normal)"};">${nearEosCount} nodes</strong>
      </div>
    `;

    // 3. Hypervisors / Integrations Summary
    const virtTypes = {};
    targetSAMSystems.forEach(s => {
      const ints = getSystemIntegrations(s);
      const vt = ints.virtualization.type.split(" (")[0]; // Clean version suffix
      virtTypes[vt] = (virtTypes[vt] || 0) + 1;
    });
    
    let virtHtml = "";
    Object.entries(virtTypes).forEach(([type, count]) => {
      virtHtml += `<div>• ${type}: <strong>${count}</strong> system${count > 1 ? 's' : ''}</div>`;
    });
    
    document.getElementById("samHypervisorCard").innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h4 style="font-size: 0.9rem; color: var(--text-secondary);">Integrations Overview</h4>
      </div>
      <div style="font-size: 1.15rem; font-weight: 700; margin-bottom: 8px;">Workload Types</div>
      <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.45;">
        ${virtHtml || "<div>No workloads active.</div>"}
      </div>
    `;

    // 4. 3rd-party Workload Alignment cards
    let hypervisorAgg = {}, databaseAgg = {}, backupAgg = {};
    targetSAMSystems.forEach(s => {
      const ints = getSystemIntegrations(s);
      hypervisorAgg[ints.virtualization.type] = (hypervisorAgg[ints.virtualization.type] || 0) + 1;
      databaseAgg[ints.database.type] = (databaseAgg[ints.database.type] || 0) + 1;
      backupAgg[ints.backup.type] = (backupAgg[ints.backup.type] || 0) + 1;
    });
    
    document.getElementById("samWorkloadVirtualization").innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h5 style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin: 0;">Orchestration & Hypervisors</h5>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-primary); line-height: 1.5;">
        ${Object.entries(hypervisorAgg).map(([k, v]) => `<div><strong>${k}</strong>: ${v} systems</div>`).join("")}
      </div>
    `;

    document.getElementById("samWorkloadDatabase").innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h5 style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin: 0;">Database & Workload</h5>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-primary); line-height: 1.5;">
        ${Object.entries(databaseAgg).map(([k, v]) => `<div><strong>${k}</strong>: ${v} systems</div>`).join("")}
      </div>
    `;

    document.getElementById("samWorkloadBackup").innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h5 style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin: 0;">Data Protection & Backup</h5>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-primary); line-height: 1.5;">
        ${Object.entries(backupAgg).map(([k, v]) => `<div><strong>${k}</strong>: ${v} systems</div>`).join("")}
      </div>
    `;

    // 5. Logistics Card Summary
    const uniqueAddrs = new Set(targetSAMSystems.map(s => (s.logistics ? s.logistics.deliveryAddress : null)).filter(Boolean));
    const totalContacts = new Set(targetSAMSystems.map(s => (s.contacts ? s.contacts.name : null)).filter(Boolean));
    let aggAlertsCount = 0;
    targetSAMSystems.forEach(s => {
      const l = s.logistics || {};
      if (l.shippingAlert && l.shippingAlert.toLowerCase() !== "none" && !l.shippingAlert.toLowerCase().includes("normal")) {
        aggAlertsCount++;
      }
    });

    document.getElementById("samLogisticsCard").innerHTML = `
      <div class="card-title" style="color: var(--accent-cyan); margin-bottom: 16px;">Site Logistics Summary</div>
      <div style="display: grid; grid-template-columns: 1.2fr 1fr; gap: 20px;">
        <div>
          <div style="margin-bottom: 8px;">Unique Sites: <strong>${uniqueAddrs.size} addresses</strong></div>
          <div style="margin-bottom: 8px;">Active logistics alerts: <strong style="color: ${aggAlertsCount > 0 ? "var(--status-critical)" : "var(--status-normal)"};">${aggAlertsCount} alerts</strong></div>
          <div style="font-size: 0.75rem; color: var(--text-secondary);">Parts shipping pathways are verified across all locations.</div>
        </div>
        <div style="border-left: 1px solid var(--border-color); padding-left: 20px;">
          <div>Key Contacts: <strong>${totalContacts.size} unique users</strong></div>
          <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">Primary accounts synced with NetApp Support Site (NSS) credentials.</div>
        </div>
      </div>
    `;

    // 6. Sales Health Card Summary
    let totalScore = 0, countScore = 0;
    let ams = new Set(), tams = new Set();
    targetSAMSystems.forEach(s => {
      if (s.salesHealth) {
        totalScore += s.salesHealth.sentimentScore;
        countScore++;
        ams.add(s.salesHealth.accountManager);
        tams.add(s.salesHealth.supportTam);
      }
    });
    const avgScore = countScore > 0 ? (totalScore / countScore) : 8.0;
    const avgPct = avgScore * 10;
    let shColor = "var(--status-normal)";
    if (avgScore < 6.0) shColor = "var(--status-critical)";
    else if (avgScore < 7.5) shColor = "var(--status-warning)";

    document.getElementById("samSalesHealthCard").innerHTML = `
      <div class="card-title" style="color: var(--accent-cyan); margin-bottom: 16px;">Sales & Account Health Scorecard</div>
      <div style="display: grid; grid-template-columns: 1fr 1.2fr; gap: 20px;">
        <div>
          <div style="margin-bottom: 12px;">
            <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase; display: block; margin-bottom: 4px;">Average CSAT Sentiment</span>
            <div style="display: flex; align-items: center; gap: 10px;">
              <div style="font-size: 1.8rem; font-weight: 800; color: ${shColor};">${avgScore.toFixed(1)}<span style="font-size: 0.9rem; font-weight: 500; color: var(--text-muted);">/10</span></div>
            </div>
            <div class="health-bar-container" style="background: rgba(255,255,255,0.05); height: 6px; border-radius: 3px; margin-top: 6px; overflow: hidden;">
              <div style="background: ${shColor}; height: 100%; width: ${avgPct}%;"></div>
            </div>
          </div>
          <div style="font-size: 0.8rem;">
            Managers: <strong>${[...ams].join(", ") || "Under Review"}</strong>
          </div>
        </div>
        <div style="border-left: 1px solid var(--border-color); padding-left: 20px;">
          <div>Support TAMs: <strong>${[...tams].join(", ") || "Under Review"}</strong></div>
          <div style="font-size: 0.72rem; color: var(--accent-cyan); font-weight: 700; text-transform: uppercase; margin-top: 8px;">Pipeline Status</div>
          <div style="font-size: 0.78rem; color: var(--text-secondary); font-style: italic;">Account is under regular quarterly review.</div>
        </div>
      </div>
    `;

    // 7. Field Actions Table: aggregate all field actions
    let faRows = "";
    const allFAs = [];
    targetSAMSystems.forEach(s => {
      if (s.fieldActions) {
        s.fieldActions.forEach(fa => {
          allFAs.push({ ...fa, systemName: s.systemName });
        });
      }
    });
    
    sortDataList(allFAs, state.samFieldActionsSortKey, state.samFieldActionsSortOrder);
    
    if (allFAs.length === 0) {
      faRows = `<tr><td colspan="2" style="text-align: center; color: var(--text-muted);">No outstanding field actions. Systems are compliant.</td></tr>`;
    } else {
      allFAs.forEach(fa => {
        faRows += `
          <tr>
            <td>
              <code style="font-weight: 600; color: var(--status-warning);">${fa.id}</code>
              <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">${fa.systemName}</div>
            </td>
            <td>
              <div style="font-weight: 500; margin-bottom: 4px;">${fa.title}</div>
              <div style="color: var(--text-secondary); font-size: 0.8rem;">${fa.actionRequired}</div>
            </td>
          </tr>
        `;
      });
    }
    document.getElementById("samFieldActionsBody").innerHTML = faRows;

    // 8. Active Technical Support Cases Table: aggregate all support cases
    let caseRows = "";
    const allCases = [];
    targetSAMSystems.forEach(s => {
      if (s.supportCases) {
        s.supportCases.forEach(sc => {
          allCases.push({ ...sc, systemName: s.systemName });
        });
      }
    });
    
    sortDataList(allCases, state.samCasesSortKey, state.samCasesSortOrder);
    
    if (allCases.length === 0) {
      caseRows = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No active support cases open.</td></tr>`;
    } else {
      allCases.forEach(c => {
        let badgeColor = "info";
        if (c.severity.includes("S1")) badgeColor = "critical";
        else if (c.severity.includes("S2")) badgeColor = "warning";
        
        caseRows += `
          <tr>
            <td><strong style="color: var(--accent-cyan); font-family: monospace;">${c.id}</strong></td>
            <td>
              <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-primary);">${c.title}</div>
              <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">System: ${c.systemName}</div>
              <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                <strong>Next Action By:</strong> <span style="color: var(--status-warning); font-weight: 600;">${c.nextActionBy || "Under Investigation"}</span>
              </div>
              <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 2px;">
                <strong>Criticality:</strong> ${c.criticality || "Normal"}
              </div>
              <div style="font-size: 0.72rem; color: var(--text-secondary); font-style: italic; background: rgba(255,255,255,0.02); padding: 4px 8px; border-radius: 4px; border-left: 2px solid var(--accent-cyan); margin-top: 6px;">
                "${c.ownerNotes}"
              </div>
            </td>
            <td><span class="badge ${badgeColor}">${c.severity}</span></td>
            <td><code style="color: var(--status-info); font-size: 0.78rem;">${c.status}</code></td>
            <td>
              <div style="font-size: 0.75rem;">Opened: ${c.createdDate}</div>
              <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">Updated: ${c.lastUpdated}</div>
            </td>
          </tr>
        `;
      });
    }
    document.getElementById("samSupportCasesBody").innerHTML = caseRows;
    
    // Virtualized workload recommendations
    const recMap = new Map();
    targetSAMSystems.forEach(s => {
      const list = getSystemWorkloadRecommendations(s);
      list.forEach(rec => {
        const match = rec.match(/^<strong>\[(.*?)\]<\/strong> (.*)$/);
        if (match) {
          const category = match[1];
          const body = match[2];
          const key = `${category}||${body}`;
          if (!recMap.has(key)) {
            recMap.set(key, []);
          }
          recMap.get(key).push(s.systemName);
        } else {
          if (!recMap.has(rec)) {
            recMap.set(rec, []);
          }
          recMap.get(rec).push(s.systemName);
        }
      });
    });

    const recsContainer = document.getElementById("samWorkloadRecommendations");
    if (recsContainer) {
      recsContainer.innerHTML = "";
      if (recMap.size === 0) {
        recsContainer.innerHTML = `<li>No active optimization recommendations for this workload portfolio.</li>`;
      } else {
        recMap.forEach((sysNames, key) => {
          const li = document.createElement("li");
          if (key.includes("||")) {
            const [category, body] = key.split("||");
            const systemsStr = sysNames.length === targetSAMSystems.length 
              ? "All Systems" 
              : (sysNames.length > 3 ? `${sysNames.length} Systems` : sysNames.join(", "));
            li.innerHTML = `<strong>[${category}]</strong> <span style="font-size: 0.72rem; color: var(--accent-cyan); font-weight: 600; margin-right: 6px;">(${systemsStr})</span> ${body}`;
          } else {
            const systemsStr = sysNames.join(", ");
            li.innerHTML = `<span style="font-size: 0.72rem; color: var(--accent-cyan); font-weight: 600; margin-right: 6px;">(${systemsStr})</span> ${key}`;
          }
          recsContainer.appendChild(li);
        });
      }
    }
    updateSortIndicators();
    return;
  }

  const sys = targetSAMSystems[0];
  if (!sys) {
    document.getElementById("samContractCard").innerHTML = "";
    document.getElementById("samLifecycleCard").innerHTML = "";
    document.getElementById("samHypervisorCard").innerHTML = "";
    document.getElementById("samLogisticsCard").innerHTML = "";
    document.getElementById("samSalesHealthCard").innerHTML = "";
    if (document.getElementById("samWorkloadVirtualization")) document.getElementById("samWorkloadVirtualization").innerHTML = "";
    if (document.getElementById("samWorkloadDatabase")) document.getElementById("samWorkloadDatabase").innerHTML = "";
    if (document.getElementById("samWorkloadBackup")) document.getElementById("samWorkloadBackup").innerHTML = "";
    if (document.getElementById("samWorkloadRecommendations")) document.getElementById("samWorkloadRecommendations").innerHTML = "";
    document.getElementById("samFieldActionsBody").innerHTML = `<tr><td colspan="2" style="text-align: center; color: var(--text-muted);">No systems available in current scope.</td></tr>`;
    document.getElementById("samSupportCasesBody").innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No systems available.</td></tr>`;
    return;
  }

  document.getElementById("samActiveSystem").innerHTML = `
    <strong>System</strong>: ${sys.systemName} (S/N: <code class="copyable-code" onclick="copyToClipboard('${sys.serialNumber}', event)" title="Click to copy Serial Number">${sys.serialNumber} <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></code>) | <strong>Platform</strong>: ${sys.platform}
  `;

  // Contract details
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
      <h4 style="font-size: 0.9rem; color: var(--text-secondary);">Support Level</h4>
      ${contractBadge}
    </div>
    <div style="font-size: 1.25rem; font-weight: 700; margin-bottom: 6px; color: ${expiryColor};">
      ${sys.contracts.supportLevel}
    </div>
    <div style="font-size: 0.85rem; color: var(--text-primary); margin-bottom: 4px;">
      Expires: <strong>${sys.contracts.endDate}</strong>
    </div>
    <div style="font-size: 0.8rem; color: var(--text-muted);">
      ${sys.contracts.daysRemaining < 0 ? `Support ended ${Math.abs(sys.contracts.daysRemaining)} days ago.` : `${sys.contracts.daysRemaining} days remaining.`}
    </div>
  `;

  // Lifecycles
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
    <div style="font-size: 1.25rem; font-weight: 700; margin-bottom: 6px; color: ${eoaGlow};">
      EOS: ${sys.lifecycle.eosDate}
    </div>
    <div style="font-size: 0.85rem; color: var(--text-primary); margin-bottom: 4px;">
      End of Availability: <strong>${sys.lifecycle.eoaDate}</strong>
    </div>
  `;

  // Hypervisors
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
    hypContainer.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem; padding-top: 12px;">No hypervisor integrations tracked on this appliance.</div>`;
  }

  // 3rd-Party Integrations & Workloads Audit
  const ints = getSystemIntegrations(sys);
  
  let virtBadge = `<span class="badge normal">${ints.virtualization.status}</span>`;
  if (ints.virtualization.status === "Warning" || ints.virtualization.status === "Out of Date") {
    virtBadge = `<span class="badge warning">${ints.virtualization.status}</span>`;
  }
  document.getElementById("samWorkloadVirtualization").innerHTML = `
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
      <h5 style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin: 0;">Orchestration & Hypervisor</h5>
      ${virtBadge}
    </div>
    <div style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;">
      ${ints.virtualization.type}
    </div>
    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px;">
      Version: <strong>${ints.virtualization.version || "N/A"}</strong>
    </div>
    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px;">
      Plugin: <strong>${ints.virtualization.plugin}</strong>
    </div>
    <div style="font-size: 0.8rem; color: var(--text-secondary);">
      Multipathing: <strong>${ints.virtualization.multipathing}</strong>
    </div>
  `;

  document.getElementById("samWorkloadDatabase").innerHTML = `
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
      <h5 style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin: 0;">Database & Workload</h5>
      <span class="badge normal">${ints.database.status}</span>
    </div>
    <div style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;">
      ${ints.database.type}
    </div>
    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px;">
      Version: <strong>${ints.database.version || "N/A"}</strong>
    </div>
    <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.3;">
      Details: <strong>${ints.database.details}</strong>
    </div>
  `;

  document.getElementById("samWorkloadBackup").innerHTML = `
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
      <h5 style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin: 0;">Data Protection & Backup</h5>
      <span class="badge normal">${ints.backup.status}</span>
    </div>
    <div style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;">
      ${ints.backup.type}
    </div>
    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px;">
      Version: <strong>${ints.backup.version || "N/A"}</strong>
    </div>
    <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.3;">
      Details: <strong>${ints.backup.details}</strong>
    </div>
  `;

  const recMap = new Map();
  const list = getSystemWorkloadRecommendations(sys);
  list.forEach(rec => {
    const match = rec.match(/^<strong>\[(.*?)\]<\/strong> (.*)$/);
    if (match) {
      const category = match[1];
      const body = match[2];
      const key = `${category}||${body}`;
      if (!recMap.has(key)) {
        recMap.set(key, []);
      }
      recMap.get(key).push(sys.systemName);
    } else {
      if (!recMap.has(rec)) {
        recMap.set(rec, []);
      }
      recMap.get(rec).push(sys.systemName);
    }
  });

  const recsContainer = document.getElementById("samWorkloadRecommendations");
  if (recsContainer) {
    recsContainer.innerHTML = "";
    if (recMap.size === 0) {
      recsContainer.innerHTML = `<li>No active optimization recommendations for this appliance workload.</li>`;
    } else {
      recMap.forEach((sysNames, key) => {
        const li = document.createElement("li");
        if (key.includes("||")) {
          const [category, body] = key.split("||");
          li.innerHTML = `<strong>[${category}]</strong> ${body}`;
        } else {
          li.innerHTML = key;
        }
        recsContainer.appendChild(li);
      });
    }
  }

  // Logistics & Site Access Card
  const logistics = sys.logistics || { deliveryAddress: "Not Set", accessRestrictions: "Not Set", shippingAlert: "None" };
  const contacts = sys.contacts || { name: "Not Set", phone: "Not Set", email: "Not Set", nssUsername: "Not Set" };
  const logAlertActive = logistics.shippingAlert && logistics.shippingAlert.toLowerCase() !== "none" && !logistics.shippingAlert.toLowerCase().includes("normal");
  
  document.getElementById("samLogisticsCard").innerHTML = `
    <div class="card-title" style="color: var(--accent-cyan); margin-bottom: 16px;">Site Logistics & Contacts</div>
    <div style="display: grid; grid-template-columns: 1.2fr 1fr; gap: 20px;">
      <div>
        <div style="margin-bottom: 12px;">
          <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase;">Delivery Address</span>
          <div style="font-size: 0.85rem; color: var(--text-primary); margin-top: 4px; font-style: italic;">${logistics.deliveryAddress}</div>
        </div>
        <div style="margin-bottom: 12px;">
          <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase;">Site Access & Security Rules</span>
          <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px; line-height: 1.3;">${logistics.accessRestrictions}</div>
        </div>
        ${logAlertActive ? `
          <div style="background-color: rgba(255, 51, 102, 0.06); border: 1px solid rgba(255, 51, 102, 0.2); padding: 10px; border-radius: var(--radius-sm); color: var(--status-critical); font-size: 0.78rem;">
            <strong>⚠️ Logistics Transit Alert:</strong> ${logistics.shippingAlert}
          </div>
        ` : `
          <div style="background-color: rgba(0, 230, 118, 0.05); border: 1px solid rgba(0, 230, 118, 0.15); padding: 8px 12px; border-radius: var(--radius-sm); color: var(--status-normal); font-size: 0.75rem; display: inline-flex; align-items: center; gap: 6px;">
            <span>✓</span> Parts Logistics Hubs Normal
          </div>
        `}
      </div>
      <div style="border-left: 1px solid var(--border-color); padding-left: 20px;">
        <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase; display: block; margin-bottom: 8px;">Primary Site Contact</span>
        <div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 4px;">${contacts.name}</div>
        <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 2px;">📞 ${contacts.phone}</div>
        <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 8px;">✉️ <a href="mailto:${contacts.email}" style="color: var(--accent-cyan); text-decoration: none;">${contacts.email}</a></div>
        <div style="font-size: 0.75rem; color: var(--text-muted); padding-top: 6px; border-top: 1px dashed var(--border-color);">
          NSS Account ID: <code style="color: var(--text-primary); font-size: 0.75rem;">${contacts.nssUsername}</code>
        </div>
      </div>
    </div>
  `;

  // Sales & Customer Health Card
  const health = sys.salesHealth || { accountManager: "Not Set", supportTam: "Not Set", sentimentScore: 7.0, healthStatus: "Stable", upsellPotential: "None", refreshWindow: "Under Review" };
  const sentimentPct = health.sentimentScore * 10;
  let healthColor = "var(--status-normal)";
  if (health.sentimentScore < 6.0) healthColor = "var(--status-critical)";
  else if (health.sentimentScore < 7.5) healthColor = "var(--status-warning)";

  document.getElementById("samSalesHealthCard").innerHTML = `
    <div class="card-title" style="color: var(--accent-cyan); margin-bottom: 16px;">Sales & Account Health Scorecard</div>
    <div style="display: grid; grid-template-columns: 1fr 1.2fr; gap: 20px;">
      <div>
        <div style="margin-bottom: 12px;">
          <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase; display: block; margin-bottom: 4px;">Customer CSAT Sentiment</span>
          <div style="display: flex; align-items: center; gap: 10px;">
            <div style="font-size: 1.8rem; font-weight: 800; color: ${healthColor};">${health.sentimentScore.toFixed(1)}<span style="font-size: 0.9rem; font-weight: 500; color: var(--text-muted);">/10</span></div>
            <span class="badge" style="background-color: rgba(255,255,255,0.03); border-color: var(--border-color); color: ${healthColor}; font-size: 0.7rem; font-weight: 700;">${health.healthStatus}</span>
          </div>
          <div class="health-bar-container" style="background: rgba(255,255,255,0.05); height: 6px; border-radius: 3px; margin-top: 6px; overflow: hidden;">
            <div style="background: ${healthColor}; height: 100%; width: ${sentimentPct}%;"></div>
          </div>
        </div>
        <div style="margin-bottom: 4px;">
          <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase;">Sales Account Manager</span>
          <div style="font-size: 0.85rem; color: var(--text-primary); font-weight: 600; margin-top: 2px;">${health.accountManager}</div>
        </div>
        <div>
          <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase;">Support Lead TAM/SAM</span>
          <div style="font-size: 0.85rem; color: var(--text-primary); margin-top: 2px;">${health.supportTam}</div>
        </div>
      </div>
      <div style="border-left: 1px solid var(--border-color); padding-left: 20px; display: flex; flex-direction: column; justify-content: space-between;">
        <div style="margin-bottom: 10px;">
          <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase;">Upcoming Refresh Window</span>
          <div style="font-size: 0.85rem; color: var(--status-warning); font-weight: 700; margin-top: 4px;">${health.refreshWindow}</div>
        </div>
        <div style="background-color: rgba(0, 229, 255, 0.04); border: 1px solid rgba(0, 229, 255, 0.15); padding: 10px; border-radius: var(--radius-sm);">
          <div style="font-size: 0.72rem; color: var(--accent-cyan); font-weight: 700; text-transform: uppercase; margin-bottom: 2px;">CSM Upsell Pipeline Opportunity</div>
          <div style="font-size: 0.8rem; color: var(--text-primary); font-weight: 500; line-height: 1.3;">${health.upsellPotential}</div>
        </div>
      </div>
    </div>
  `;

  // Field Actions
  let faRows = "";
  const fas = [...(sys.fieldActions || [])];
  sortDataList(fas, state.samFieldActionsSortKey, state.samFieldActionsSortOrder);
  if (fas.length === 0) {
    faRows = `<tr><td colspan="2" style="text-align: center; color: var(--text-muted);">No outstanding field actions. System is compliant.</td></tr>`;
  } else {
    fas.forEach(fa => {
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

  // Render Open Support Cases Table
  const cases = [...(sys.supportCases || [])];
  sortDataList(cases, state.samCasesSortKey, state.samCasesSortOrder);
  let caseRows = "";
  if (cases.length === 0) {
    caseRows = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No active technical support cases open.</td></tr>`;
  } else {
    cases.forEach(c => {
      let sevBadge = `<span class="badge info">${c.severity}</span>`;
      if (c.severity.includes("S1")) sevBadge = `<span class="badge critical">${c.severity}</span>`;
      else if (c.severity.includes("S2")) sevBadge = `<span class="badge warning">${c.severity}</span>`;

      caseRows += `
        <tr>
          <td><strong style="color: var(--accent-cyan); font-family: monospace;">${c.id}</strong></td>
          <td>
            <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-primary);">${c.title}</div>
            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
              <strong>Next Action By:</strong> <span style="color: var(--status-warning); font-weight: 600;">${c.nextActionBy || "Under Investigation"}</span>
            </div>
            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 2px;">
              <strong>Criticality:</strong> ${c.criticality || "Normal"}
            </div>
            <div style="font-size: 0.72rem; color: var(--text-secondary); font-style: italic; background: rgba(255,255,255,0.02); padding: 4px 8px; border-radius: 4px; border-left: 2px solid var(--accent-cyan); margin-top: 6px;">
              "${c.ownerNotes}"
            </div>
          </td>
          <td>${sevBadge}</td>
          <td><code style="color: var(--status-info); font-size: 0.78rem;">${c.status}</code></td>
          <td style="font-size: 0.78rem; color: var(--text-muted);">
            Opened: ${c.createdDate}<br>Updated: ${c.lastUpdated}
          </td>
        </tr>
      `;
    });
  }
  document.getElementById("samSupportCasesBody").innerHTML = caseRows;
  updateSortIndicators();
}

function renderCSMTab() {
  populateSystemSelectors();
  
  const currentFiltered = getFilteredSystems();
  const targetCSMSystems = [];
  if (state.selectedCSMSystemSerial === "ALL") {
    targetCSMSystems.push(...currentFiltered);
  } else if (state.selectedCSMSystemSerial.startsWith("CLUSTER:")) {
    const cluster = state.selectedCSMSystemSerial.substring(8);
    targetCSMSystems.push(...currentFiltered.filter(s => s.clusterName === cluster));
  } else {
    const serial = state.selectedCSMSystemSerial.startsWith("NODE:") ? state.selectedCSMSystemSerial.substring(5) : state.selectedCSMSystemSerial;
    const found = currentFiltered.find(s => s.serialNumber === serial);
    if (found) targetCSMSystems.push(found);
  }
  
  if (targetCSMSystems.length === 0) {
    document.getElementById("csmSavingsCard").innerHTML = "";
    document.getElementById("csmCloudCard").innerHTML = "";
    document.getElementById("csmSnapmirrorCard").innerHTML = "";
    document.getElementById("csmAdoptionChecklist").innerHTML = "";
    document.getElementById("csmGrowthRateText").innerText = "";
    document.getElementById("csmDaysToLimitText").innerText = "-";
    document.getElementById("csmLimitDateText").innerText = "-";
    document.getElementById("csmPeakIopsText").innerText = "-";
    document.getElementById("csmAvgLatencyText").innerText = "-";
    return;
  }

  const isMulti = targetCSMSystems.length > 1;

  if (isMulti) {
    document.getElementById("csmActiveSystem").innerHTML = `
      <strong>Selected Systems (${targetCSMSystems.length})</strong>: <span style="font-size: 0.8rem; color: var(--text-primary);">${targetCSMSystems.map(s => s.systemName).join(", ")}</span>
    `;

    // 1. Efficiency aggregate
    let totalLogical = 0, totalPhysical = 0, totalSaved = 0;
    targetCSMSystems.forEach(s => {
      totalLogical += s.efficiency.logicalUsedTB;
      totalPhysical += s.efficiency.physicalUsedTB;
      totalSaved += s.efficiency.spaceSavedTB;
    });
    const avgRatio = totalPhysical > 0 ? (totalLogical / totalPhysical).toFixed(1) : "1.0";

    document.getElementById("csmSavingsCard").innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 12px;">
        <div>
          <span style="font-size: 0.8rem; color: var(--text-secondary); text-transform: uppercase;">Overall Account Efficiency</span>
          <div style="font-size: 2.2rem; font-weight: 800; color: var(--status-normal);">${avgRatio}:1</div>
        </div>
        <div style="border-top: 1px solid var(--border-color); padding-top: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <div>
            <span style="font-size: 0.75rem; color: var(--text-muted);">Logical Space Used</span>
            <div style="font-weight: 600;">${totalLogical.toFixed(1)} TB</div>
          </div>
          <div>
            <span style="font-size: 0.75rem; color: var(--text-muted);">Physical Space Used</span>
            <div style="font-weight: 600;">${totalPhysical.toFixed(1)} TB</div>
          </div>
        </div>
        <div style="background-color: rgba(0, 230, 118, 0.08); padding: 12px; border-radius: var(--radius-sm); border: 1px solid rgba(0, 230, 118, 0.2);">
          <div style="font-size: 0.75rem; color: var(--status-normal); font-weight: 700; text-transform: uppercase; margin-bottom: 2px;">Total Storage Saved</div>
          <div style="font-size: 1.2rem; font-weight: 700; color: #fff;">${totalSaved.toFixed(1)} TB</div>
        </div>
      </div>
    `;

    // 2. FabricPool aggregate
    let totalFP = 0, activeFPCount = 0;
    targetCSMSystems.forEach(s => {
      const fp = s.efficiency.fabricPoolTieredTB || 0;
      totalFP += fp;
      if (fp > 0) activeFPCount++;
    });
    let fpBadge = activeFPCount > 0 ? `<span class="badge normal">${activeFPCount} active tiering</span>` : `<span class="badge warning">No Cloud Tiering</span>`;
    document.getElementById("csmCloudCard").innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h4 style="font-size: 0.9rem; color: var(--text-secondary);">FabricPool Integration</h4>
        ${fpBadge}
      </div>
      <div style="font-size: 1.4rem; font-weight: 700; margin-bottom: 6px; color: ${totalFP > 0 ? "var(--status-info)" : "var(--status-warning)"};">
        Cloud Tiered: ${totalFP.toFixed(1)} TB
      </div>
      <p style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4;">
        ${activeFPCount} out of ${targetCSMSystems.length} systems are tiering cold data to public/private cloud object storage.
      </p>
    `;

    // 3. SnapMirror aggregate
    let smEnabledCount = 0;
    let relationshipsHTML = "";
    targetCSMSystems.forEach(s => {
      if (s.snapmirror && s.snapmirror.enabled) {
        smEnabledCount++;
        s.snapmirror.relationships.forEach(rel => {
          relationshipsHTML += `
            <div style="margin-top: 8px; font-size: 0.78rem; border-top: 1px solid var(--border-color); padding-top: 6px; display: flex; justify-content: space-between;">
              <span>Sys: <strong>${s.systemName}</strong> -> <strong>${rel.destination}</strong></span>
              <span style="color: var(--accent-cyan);">${rel.lagTime}</span>
            </div>
          `;
        });
      }
    });
    if (relationshipsHTML === "") {
      relationshipsHTML = `<div style="color: var(--text-muted); font-size: 0.8rem; margin-top: 10px;">No SnapMirror relations mapped.</div>`;
    }
    document.getElementById("csmSnapmirrorCard").innerHTML = `
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <h4 style="font-size: 0.9rem; color: var(--text-secondary);">SnapMirror replication</h4>
        <span class="badge normal">${smEnabledCount} Enabled</span>
      </div>
      <div style="max-height: 120px; overflow-y: auto; padding-right: 4px;">
        ${relationshipsHTML}
      </div>
    `;

    // 4. Checklist aggregate
    let efficiencyPass = 0, cloudPass = 0, drPass = 0, riskPass = 0;
    targetCSMSystems.forEach(s => {
      if (parseFloat(s.efficiency.ratio.split(":")[0]) > 1.5) efficiencyPass++;
      if (s.efficiency.fabricPoolTieredTB > 0) cloudPass++;
      if (s.snapmirror && s.snapmirror.enabled) drPass++;
      if (s.risks.filter(r => r.severity === 'critical' || r.severity === 'high').length === 0) riskPass++;
    });
    const checklist = [
      { name: "ONTAP 9.10+ / StorageGRID 11.5+", completedCount: targetCSMSystems.length },
      { name: "Storage Efficiency Enabled (>1.5:1)", completedCount: efficiencyPass },
      { name: "Cloud FabricPool Configured", completedCount: cloudPass },
      { name: "SnapMirror DR Configured", completedCount: drPass },
      { name: "Zero High/Critical Risks", completedCount: riskPass }
    ];
    let checklistHTML = "";
    checklist.forEach(item => {
      checklistHTML += `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px; background: rgba(255,255,255,0.01); border-bottom: 1px solid var(--border-color);">
          <span style="font-size: 0.85rem;">${item.name}</span>
          <span style="font-size: 0.85rem; font-weight: 600; color: ${item.completedCount === targetCSMSystems.length ? "var(--status-normal)" : "var(--status-warning)"};">
            ${item.completedCount}/${targetCSMSystems.length} Done
          </span>
        </div>
      `;
    });
    document.getElementById("csmAdoptionChecklist").innerHTML = checklistHTML;

    // 5. Projections aggregate
    let totalGrowth = 0, minDaysToLimit = 9999, worstLimitDate = "N/A", worstSystemName = "";
    let totalPeakIops = 0, sumAvgLatency = 0, countAvgLatency = 0;
    
    const aggHist = Array(6).fill(0);
    const aggProj = Array(3).fill(0);
    
    targetCSMSystems.forEach(s => {
      const p = s.projections || { growthRateGBPerDay: 100, daysToLimit: 120, limitDate: "Under Review", peakIops: 10000, avgLatencyMs: 2.5, historicalCapacityMonths: [10, 11, 12, 13, 14, 15], projectedCapacityMonths: [16, 17, 18] };
      totalGrowth += p.growthRateGBPerDay;
      if (p.daysToLimit < minDaysToLimit) {
        minDaysToLimit = p.daysToLimit;
        worstLimitDate = p.limitDate;
        worstSystemName = s.systemName;
      }
      totalPeakIops += p.peakIops;
      sumAvgLatency += p.avgLatencyMs;
      countAvgLatency++;
      
      for (let m = 0; m < 6; m++) {
        aggHist[m] += p.historicalCapacityMonths[m] || 0;
      }
      for (let m = 0; m < 3; m++) {
        aggProj[m] += p.projectedCapacityMonths[m] || 0;
      }
    });
    
    const avgLatency = countAvgLatency > 0 ? (sumAvgLatency / countAvgLatency) : 2.5;

    document.getElementById("csmGrowthRateText").innerText = `Aggregate Growth: +${totalGrowth} GB/day`;
    
    const limitLabel = document.getElementById("csmDaysToLimitText");
    limitLabel.innerText = `${minDaysToLimit} Days`;
    limitLabel.style.color = minDaysToLimit <= 60 ? "var(--status-critical)" : (minDaysToLimit <= 120 ? "var(--status-warning)" : "var(--status-normal)");
    
    document.getElementById("csmLimitDateText").innerText = `Est. limit reached on ${worstSystemName}: ${worstLimitDate}`;
    document.getElementById("csmPeakIopsText").innerText = `${totalPeakIops.toLocaleString()} IOPS`;
    document.getElementById("csmAvgLatencyText").innerText = `Avg Latency: ${avgLatency.toFixed(1)} ms`;

    const aggProjObj = {
      historicalCapacityMonths: aggHist,
      projectedCapacityMonths: aggProj
    };
    renderProjectionsChart(aggProjObj, "Consolidated Account Portfolio");
    return;
  }

  const sys = targetCSMSystems[0];
  if (!sys) {
    document.getElementById("csmSavingsCard").innerHTML = "";
    document.getElementById("csmCloudCard").innerHTML = "";
    document.getElementById("csmSnapmirrorCard").innerHTML = "";
    document.getElementById("csmAdoptionChecklist").innerHTML = "";
    document.getElementById("csmGrowthRateText").innerText = "";
    document.getElementById("csmDaysToLimitText").innerText = "-";
    document.getElementById("csmLimitDateText").innerText = "-";
    document.getElementById("csmPeakIopsText").innerText = "-";
    document.getElementById("csmAvgLatencyText").innerText = "-";
    return;
  }

  document.getElementById("csmActiveSystem").innerHTML = `
    <strong>System</strong>: ${sys.systemName} (S/N: <code class="copyable-code" onclick="copyToClipboard('${sys.serialNumber}', event)" title="Click to copy Serial Number">${sys.serialNumber} <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></code>) | <strong>Customer</strong>: ${sys.customerName}
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
  let fpAdoptionBadge = "";
  let fpStatusText = "";
  
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
      relationshipsHTML = `<div style="color: var(--text-muted); font-size: 0.8rem; margin-top: 10px;">No SnapMirror relations mapped. Add sync/async replication for disaster recovery.</div>`;
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

  // Render Projections & Forecasting Metrics & Line Chart
  const proj = sys.projections || { growthRateGBPerDay: 100, daysToLimit: 120, limitDate: "Under Review", peakIops: 10000, avgLatencyMs: 2.5, historicalCapacityMonths: [10, 11, 12, 13, 14, 15], projectedCapacityMonths: [16, 17, 18] };
  
  document.getElementById("csmGrowthRateText").innerText = `Average Growth: +${proj.growthRateGBPerDay} GB/day`;
  
  const limitLabel = document.getElementById("csmDaysToLimitText");
  limitLabel.innerText = `${proj.daysToLimit} Days`;
  limitLabel.style.color = proj.daysToLimit <= 60 ? "var(--status-critical)" : (proj.daysToLimit <= 120 ? "var(--status-warning)" : "var(--status-normal)");
  
  document.getElementById("csmLimitDateText").innerText = `Est. Limit reached: ${proj.limitDate}`;
  document.getElementById("csmPeakIopsText").innerText = `${proj.peakIops.toLocaleString()} IOPS`;
  document.getElementById("csmAvgLatencyText").innerText = `Avg Latency: ${proj.avgLatencyMs.toFixed(1)} ms`;

  // Draw capacity/performance projection line chart
  renderProjectionsChart(proj, sys.systemName);
}

function renderProjectionsChart(proj, systemName) {
  const ctx = document.getElementById("csmProjectionsChart");
  if (!ctx) return;

  if (projectionsChartInstance) {
    projectionsChartInstance.destroy();
  }

  if (typeof Chart === "undefined") return;

  // Generate labels representing past 6 months + next 3 months
  const labels = ["Month -6", "Month -5", "Month -4", "Month -3", "Month -2", "Current", "Month +1 (Proj)", "Month +2 (Proj)", "Month +3 (Proj)"];
  
  // Format datasets: historical capacity stops at "Current", projected capacity continues from "Current"
  const histData = [...proj.historicalCapacityMonths, ...Array(3).fill(null)];
  const projData = [...Array(5).fill(null), proj.historicalCapacityMonths[5], ...proj.projectedCapacityMonths];

  projectionsChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Historical Storage Utilized (TB)',
          data: histData,
          borderColor: '#00e5ff',
          backgroundColor: 'rgba(0, 229, 255, 0.05)',
          borderWidth: 3,
          tension: 0.2,
          fill: true
        },
        {
          label: 'Projected Growth Trend (TB)',
          data: projData,
          borderColor: '#ffb300',
          borderDash: [5, 5],
          backgroundColor: 'transparent',
          borderWidth: 3,
          tension: 0.2,
          pointStyle: 'rectRot',
          pointRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          ticks: { color: '#9ca3af', font: { size: 10 } },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        y: {
          ticks: { color: '#9ca3af', font: { size: 10 } },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        }
      },
      plugins: {
        legend: {
          position: 'top',
          labels: { color: '#f3f4f6', boxWidth: 12, font: { size: 11 } }
        }
      }
    }
  });
}

// 7. Action Plan Compiler
function populateActionPlanSelector() {
  const select = document.getElementById("planTargetSelect");
  if (!select) return;
  select.innerHTML = '<option value="ALL">All Account Systems (Filtered Context)</option>';
  
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

  if (state.watchlists) {
    state.watchlists.forEach(wl => {
      const opt = document.createElement("option");
      opt.value = `WL:${wl.id}`;
      opt.innerText = `Watchlist: ${wl.name} (${wl.systemSerials.length} systems)`;
      select.appendChild(opt);
    });
  }
  
  state.systems.forEach(sys => {
    const opt = document.createElement("option");
    opt.value = `SYS:${sys.serialNumber}`;
    opt.innerText = `System: ${sys.systemName} (${sys.platform})`;
    select.appendChild(opt);
  });

  // Automatically align selected action planner target with active sidebar filter
  if (state.activeFilterType === "CUSTOMER") {
    select.value = `CUST:${state.activeFilterValue}`;
  } else if (state.activeFilterType === "GROUP") {
    select.value = `GRP:${state.activeFilterValue}`;
  } else if (state.activeFilterType === "WATCHLIST") {
    select.value = `WL:${state.activeFilterValue}`;
  } else {
    select.value = "ALL";
  }
}

function generateActionPlan() {
  const selectValue = document.getElementById("planTargetSelect").value;
  const planBody = document.getElementById("generatedPlanBody");
  if (!planBody) return;
  
  let targetSystems = [];
  let scopeTitle = "";
  
  if (selectValue === "ALL") {
    targetSystems = getFilteredSystems();
    const query = (state.activeSearchQuery || "").trim();
    if (state.activeFilterType !== "ALL" || query !== "") {
      scopeTitle = "Filtered Account Portfolio";
    } else {
      scopeTitle = "Total Account Portfolio";
    }
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
  } else if (selectValue.startsWith("WL:")) {
    const wlId = selectValue.substring(3);
    const wl = state.watchlists.find(w => w.id === wlId);
    if (wl) {
      targetSystems = state.systems.filter(s => wl.systemSerials.includes(s.serialNumber));
      scopeTitle = `Watchlist: ${wl.name}`;
    }
  } else if (selectValue.startsWith("SYS:")) {
    const serial = selectValue.substring(4);
    const found = state.systems.find(s => s.serialNumber === serial);
    if (found) targetSystems = [found];
    scopeTitle = `System: ${found ? found.systemName : serial}`;
  }

  if (targetSystems.length === 0) {
    planBody.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 40px;">No systems found in selected scope.</div>`;
    return;
  }

  const allRisks = [];
  const allUpgrades = [];
  const expiringContracts = [];
  const activeFAs = [];
  const allHypervisors = [];
  const allSecurityAdvisories = [];
  const allSupportCases = [];

  targetSystems.forEach(sys => {
    sys.risks.forEach(r => allRisks.push({ systemName: sys.systemName, ...r }));
    if (sys.upgrades.targetVersion !== "Up to Date") {
      allUpgrades.push({ systemName: sys.systemName, platform: sys.platform, ...sys.upgrades });
    }
    if (sys.contracts.daysRemaining <= 90) {
      expiringContracts.push({ systemName: sys.systemName, ...sys.contracts });
    }
    sys.fieldActions.forEach(fa => activeFAs.push({ systemName: sys.systemName, ...fa }));
    if (sys.hypervisors) {
      sys.hypervisors.forEach(h => allHypervisors.push({ systemName: sys.systemName, ...h }));
    }
    if (sys.securityBulletins) {
      sys.securityBulletins.forEach(sb => allSecurityAdvisories.push({ systemName: sys.systemName, ...sb }));
    }
    if (sys.supportCases) {
      sys.supportCases.forEach(sc => allSupportCases.push({ systemName: sys.systemName, ...sc }));
    }
  });

  const switchAlerts = [];
  targetSystems.forEach(sys => {
    const sws = getSystemSwitches(sys);
    sws.forEach(sw => {
      if (sw.status !== "Optimal") {
        switchAlerts.push({ systemName: sys.systemName, ...sw });
      }
    });
  });

  // 8. Compile Executable Deliverables (Draft Email, Upgrade Proposal, and Internal Dispatch Ticket)
  const emailRisksList = allRisks.map(r => ` - System: ${r.systemName} | Category: ${r.category} | Issue: ${r.description}`).join("\n");
  const emailCasesList = allSupportCases.map(c => ` - Case ID: ${c.id} | Subject: ${c.title} | Status: ${c.status}`).join("\n");
  
  const upgradeTargetsList = allUpgrades.map(u => {
    const origSys = targetSystems.find(s => s.systemName === u.systemName);
    const origVer = origSys ? origSys.ontapVersion : "unknown";
    return ` - System: ${u.systemName} | Current OS: ${origVer} | Target OS: ${u.targetVersion}`;
  }).join("\n");
  
  const contractExpiryList = expiringContracts.map(e => ` - System: ${e.systemName} | Support Level: ${e.supportLevel} | Expiry Date: ${e.endDate} (${e.daysRemaining} days remaining)`).join("\n");

  const draftEmailText = `Subject: NetApp Operational Health & Risk Advisory Alert - ${scopeTitle}

Dear Storage Operations Team,

This is a proactive advisory update from your NetApp Account Team regarding the health, stability, and operational risk metrics of your storage systems. Active IQ Digital Advisor has analyzed your configurations and identified items requiring your review:

${allRisks.length > 0 ? `CRITICAL/HIGH TECHNICAL RISKS:\n${emailRisksList}` : "✓ No critical or high technical configuration risks detected."}

${allSupportCases.length > 0 ? `OPEN SUPPORT TICKETS:\n${emailCasesList}` : "✓ No active open technical support cases detected."}

RECOMMENDED ACTION ITEMS:
1. Review the step-by-step remediation plans in our attached Operations Plan.
2. Schedule a maintenance window to apply critical firmware upgrades or replace degraded SAS cabling if applicable.
3. Verify logistics shipping details with site contacts before part dispatch.

If you have any questions or require assistance, please contact your account support leads.

Best Regards,
[Your Name / NetApp TAM Team]`;

  const draftProposalText = `MEMORANDUM OF PROPOSAL: STORAGE OS UPGRADE & PLATFORM REFRESH

CUSTOMER BASE: ${scopeTitle}
PREPARED BY: NetApp Technical Account Management (TAM)

1. RECOMMENDED OPERATING SYSTEM UPGRADES
To align your systems with NetApp's Interoperability Matrix Tool (IMT) and apply critical security/performance microcode updates, we recommend the following target version updates:
${allUpgrades.length > 0 ? upgradeTargetsList : "✓ All systems in scope are currently running recommended stable releases."}

2. SUPPORT CONTRACT RENEWALS & PLATFORM REFRESH
The following storage controllers are approaching contract expiration or end-of-support deadlines and require immediate renewal or node swap planning:
${expiringContracts.length > 0 ? contractExpiryList : "✓ All active contracts have > 90 days remaining."}

3. HARDWARE EXPANSION OPPORTUNITIES
To maintain performance headroom and address storage growth runway targets, we propose expanding:
 - FabricPool cloud tiering to offload cold blocks to Object Storage.
 - Target tech refresh timelines matching upcoming windows.`;

  const internalTicketText = `TICKET TITLE: NetApp Dispatch & Parts Coordination - ${scopeTitle}

TICKET CLASSIFICATION: Infrastructure Operations -> NetApp Storage Maintenance
TICKET SEVERITY: S2 - Major (Logistics & Maintenance Window Required)

DESCRIPTION:
Please initiate change control and stage parts coordination for the following NetApp systems:

${targetSystems.map(s => {
  const l = s.logistics || { deliveryAddress: "Not Set", accessRestrictions: "Not Set" };
  const c = s.contacts || { name: "Not Set", phone: "Not Set" };
  return `SYSTEM: ${s.systemName} (S/N: ${s.serialNumber})
- Delivery Address: ${l.deliveryAddress}
- Access Rules: ${l.accessRestrictions}
- Site Contact: ${c.name} (${c.phone})
- Required Action: Coordinate parts delivery and schedule on-site technician.`;
}).join("\n\n")}

LOGISTICS COMPLIANCE INSTRUCTIONS:
- Verify active Secret/Biometric clearance criteria with site contacts prior to dispatch.
- Cross-reference active shipment codes against tracking APIs.`;

  let html = `
    <div class="plan-section active" data-section-index="1">
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
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">
          <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">1. Executive Summary</h2>
          <div style="display: flex; gap: 8px;">
            <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadPlanSection(1)" data-tooltip="Download Section 1 text report as a TXT file.">Download Summary (TXT)</button>
            <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('CSV')" data-tooltip="Download full filtered systems inventory list as a CSV spreadsheet.">Export Inventory (CSV)</button>
          </div>
        </div>
        <p style="font-size: 0.9rem; line-height: 1.5; color: var(--text-secondary); margin-bottom: 12px;">
          This document represents the consolidated operational action plan generated from telemetry data analyzed by NetApp Active IQ Digital Advisor. 
          A total of <strong>${targetSystems.length}</strong> storage configuration(s) were audited.
        </p>
        <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin: 20px 0;">
          <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: var(--radius-sm); text-align: center; border: 1px solid var(--border-color);">
            <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Total Risks</div>
            <div style="font-size: 1.3rem; font-weight: 700; color: ${allRisks.length > 0 ? "var(--status-critical)" : "var(--status-normal)"}">${allRisks.length}</div>
          </div>
          <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: var(--radius-sm); text-align: center; border: 1px solid var(--border-color);">
            <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Security Advisories</div>
            <div style="font-size: 1.3rem; font-weight: 700; color: ${allSecurityAdvisories.length > 0 ? "var(--status-critical)" : "var(--status-normal)"}">${allSecurityAdvisories.length}</div>
          </div>
          <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: var(--radius-sm); text-align: center; border: 1px solid var(--border-color);">
            <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Open Support Cases</div>
            <div style="font-size: 1.3rem; font-weight: 700; color: ${allSupportCases.length > 0 ? "var(--status-warning)" : "var(--status-normal)"}">${allSupportCases.length}</div>
          </div>
          <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: var(--radius-sm); text-align: center; border: 1px solid var(--border-color);">
            <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Support Expiring</div>
            <div style="font-size: 1.3rem; font-weight: 700; color: ${expiringContracts.length > 0 ? "var(--status-critical)" : "var(--status-normal)"}">${expiringContracts.length}</div>
          </div>
          <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: var(--radius-sm); text-align: center; border: 1px solid var(--border-color);">
            <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Active Field Actions</div>
            <div style="font-size: 1.3rem; font-weight: 700; color: ${activeFAs.length > 0 ? "var(--status-warning)" : "var(--status-normal)"}">${activeFAs.length}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Technical Risks Section -->
    <div class="plan-section" data-section-index="2" style="display: none; margin-top: 32px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">
        <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">2. Prioritized Technical Risks & Remediation Steps</h2>
        <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadPlanSection(2)" data-tooltip="Download Section 2 prioritized risks report as a TXT file.">Download Risks (TXT)</button>
      </div>
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
            <strong>Root Cause Analysis:</strong><br>${r.remediationPlan ? r.remediationPlan.cause : "Undetermined"}
          </div>
          <div style="font-size: 0.85rem; color: var(--status-critical); margin-bottom: 12px; background: rgba(255, 51, 102, 0.03); padding: 10px; border-radius: var(--radius-sm); border: 1px solid rgba(255, 51, 102, 0.15); margin-top: 8px;">
            <strong>Operations Impact:</strong><br>${r.remediationPlan ? r.remediationPlan.impact : "Undetermined"}
          </div>
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 12px;">
            <strong>Step-by-Step Remediation Plan:</strong>
            <ol style="margin-left: 20px; margin-top: 6px; font-family: monospace; line-height: 1.4;">
              ${r.remediationPlan ? r.remediationPlan.steps.map(s => `<li>${s}</li>`).join("") : "<li>Review standard operating guidelines.</li>"}
            </ol>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-muted);">
            <strong>Options & Trade-offs:</strong>
            <ul style="margin-left: 20px; margin-top: 4px; line-height: 1.4;">
              ${r.remediationPlan ? r.remediationPlan.options.map(o => `<li>${o}</li>`).join("") : "<li>Contact NetApp Support.</li>"}
            </ul>
          </div>
        </div>
      `;
    });
  }

  html += `
    </div>

    <!-- Security & Technical Bulletins Section -->
    <div class="plan-section" data-section-index="3" style="display: none; margin-top: 32px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">
        <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">3. Security Bulletins & Vulnerability Mitigations</h2>
        <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadPlanSection(3)" data-tooltip="Download Section 3 security advisories report as a TXT file.">Download Advisories (TXT)</button>
      </div>
  `;

  if (allSecurityAdvisories.length === 0) {
    html += `<p style="font-size: 0.85rem; color: var(--text-muted);">✓ No security vulnerabilities mapped against the target system release baselines.</p>`;
  } else {
    allSecurityAdvisories.forEach((s, idx) => {
      let badgeClass = "badge info";
      if (s.severity === "critical" || s.severity === "high") badgeClass = "badge critical";
      
      html += `
        <div style="background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 16px; border-radius: var(--radius-sm); margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <strong>Bulletin: ${s.id} - ${s.systemName}</strong>
            <span class="${badgeClass}" style="font-size: 0.7rem;">${s.severity}</span>
          </div>
          <div style="font-size: 0.85rem; font-weight: 600; color: #fff; margin-bottom: 4px;">${s.title}</div>
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 6px;">
            <strong>Mitigation Steps:</strong> ${s.mitigation}
          </div>
          <div style="font-size: 0.8rem; color: var(--status-warning);">Status: <strong>${s.status}</strong></div>
        </div>
      `;
    });
  }

  html += `
    </div>

    <!-- Open Support Cases Section -->
    <div class="plan-section" data-section-index="4" style="display: none; margin-top: 32px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">
        <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">4. Active Support Cases & Milestones</h2>
        <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadPlanSection(4)" data-tooltip="Download Section 4 open support cases report as a TXT file.">Download Cases (TXT)</button>
      </div>
  `;

  if (allSupportCases.length === 0) {
    html += `<p style="font-size: 0.85rem; color: var(--text-muted);">✓ No active technical support cases open in the NetApp Support portal.</p>`;
  } else {
    allSupportCases.forEach((c, idx) => {
      let badgeClass = "badge info";
      if (c.severity.includes("S1")) badgeClass = "badge critical";
      else if (c.severity.includes("S2")) badgeClass = "badge warning";

      html += `
        <div style="background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 16px; border-radius: var(--radius-sm); margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <strong>Case ID: ${c.id} - ${c.systemName}</strong>
            <span class="${badgeClass}" style="font-size: 0.7rem;">${c.severity}</span>
          </div>
          <div style="font-size: 0.85rem; font-weight: 600; color: #fff; margin-bottom: 4px;">${c.title}</div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 4px;">
            <strong>Criticality Assessment:</strong> ${c.criticality || "Normal"}
          </div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 6px;">
            <strong>Next Action Owner:</strong> <span style="color: var(--status-warning); font-weight: 600;">${c.nextActionBy || "Under Review"}</span>
          </div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 8px; font-style: italic; background: rgba(0,0,0,0.2); padding: 6px 10px; border-radius: 4px; border-left: 3px solid var(--accent-cyan);">
            <strong>Latest Notes:</strong> ${c.ownerNotes}
          </div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">
            Status: <code style="color: var(--status-info);">${c.status}</code> | Opened: <strong>${c.createdDate}</strong> | Last Updated: <strong>${c.lastUpdated}</strong>
          </div>
        </div>
      `;
    });
  }

  html += `
    </div>

    <!-- OS/Firmware Upgrades Section -->
    <div class="plan-section" data-section-index="5" style="display: none; margin-top: 32px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">
        <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">5. Recommended OS Upgrade Roadmaps</h2>
        <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadPlanSection(5)" data-tooltip="Download Section 5 OS upgrade roadmap as a TXT file.">Download Roadmaps (TXT)</button>
      </div>
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
          <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;">
            Min. Required OS Version (To Fix): <strong style="color: var(--accent-cyan);">${u.targetVersion}</strong> | Latest Supported OS Version: <strong style="color: var(--status-normal);">${getLatestSupportedVersion(u.platform)}</strong>
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

    <!-- Network Switch & Fabric Infrastructure Remediation Section -->
    <div class="plan-section" data-section-index="6" style="display: none; margin-top: 32px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">
        <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">6. Network Switch & Fabric Infrastructure Remediation</h2>
        <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadPlanSection(6)" data-tooltip="Download Section 6 switch validation roadmap as a TXT file.">Download Switch Report (TXT)</button>
      </div>
  `;

  if (switchAlerts.length === 0) {
    html += `<p style="font-size: 0.85rem; color: var(--text-muted);">✓ All interconnect and storage network fabric switches match validated firmware baselines.</p>`;
  } else {
    switchAlerts.forEach(sw => {
      let badgeClass = "badge warning";
      if (sw.status === "Critical") badgeClass = "badge critical";
      
      let stepGuide = "";
      if (sw.model.toLowerCase().includes("nexus")) {
        stepGuide = `
          <strong>ISSU (In-Service Software Upgrade) Action Steps:</strong>
          <ol style="margin-left: 20px; margin-top: 4px; font-family: monospace; font-size: 0.78rem; line-height: 1.4;">
            <li>1. Copy NX-OS system image to switch bootflash: via SCP/SFTP.</li>
            <li>2. Verify file checksum: <code>show file bootflash:${sw.targetFirmware}.bin md5sum</code></li>
            <li>3. Perform pre-upgrade impact checks: <code>show install all impact nxos bootflash:${sw.targetFirmware}.bin</code></li>
            <li>4. Initiate non-disruptive installation: <code>install all nxos bootflash:${sw.targetFirmware}.bin</code></li>
            <li>5. Verify switch status after reload: <code>show version</code> and check link integrity.</li>
          </ol>
        `;
      } else if (sw.model.toLowerCase().includes("brocade")) {
        stepGuide = `
          <strong>Hot Code Load Upgrade Action Steps:</strong>
          <ol style="margin-left: 20px; margin-top: 4px; font-family: monospace; font-size: 0.78rem; line-height: 1.4;">
            <li>1. Upload Fabric OS (FOS) firmware package to switch via FTP/SFTP.</li>
            <li>2. Run pre-install validations: <code>firmwaredownload -p sftp -u admin -d ...</code></li>
            <li>3. Initiate non-disruptive download: <code>firmwaredownload</code></li>
            <li>4. Confirm active partition status: <code>firmwareshow</code></li>
            <li>5. Verify fabric sync status: <code>switchshow</code></li>
          </ol>
        `;
      } else {
        stepGuide = `
          <strong>Firmware Upgrade Steps:</strong>
          <ol style="margin-left: 20px; margin-top: 4px; font-family: monospace; font-size: 0.78rem; line-height: 1.4;">
            <li>1. Back up switch running configuration: <code>copy running-config tftp://...</code></li>
            <li>2. Download target firmware package matching validated version ${sw.targetFirmware}.</li>
            <li>3. Run system flash upgrade check and reboot switch during maintenance window.</li>
          </ol>
        `;
      }

      html += `
        <div style="background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm); margin-bottom: 16px; font-size: 0.85rem; line-height: 1.4;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <strong style="font-size: 0.95rem; color: #fff;">System: ${sw.systemName} | ${sw.model} (${sw.type})</strong>
            <span class="${badgeClass}" style="font-size: 0.7rem;">${sw.status}</span>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-primary); margin-bottom: 8px;">
            Switch S/N: <code style="color: var(--accent-cyan);">${sw.serialNumber}</code> | IP: <code>${sw.ipAddress}</code>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.4;">
            Current Firmware: <code style="color: var(--text-muted);">${sw.firmware}</code> | Min. Required (To Fix): <strong style="color: var(--accent-cyan);">${sw.targetFirmware}</strong> | Latest Supported: <strong style="color: var(--status-normal);">${getLatestSupportedVersion(sw.model)}</strong>
          </div>
          <div style="font-size: 0.85rem; color: var(--status-warning); margin-bottom: 12px; background: rgba(255, 170, 0, 0.03); padding: 10px; border-radius: var(--radius-sm); border: 1px solid rgba(255, 170, 0, 0.1);">
            <strong>Validation Drift:</strong> ${sw.validationDetails}
          </div>
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 8px;">
            ${stepGuide}
          </div>
        </div>
      `;
    });
  }

  html += `
    </div>

    <!-- Site Logistics, Contacts & Health Details Section -->
    <div class="plan-section" data-section-index="7" style="display: none; margin-top: 32px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">
        <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">7. Site Logistics, Contacts, & Customer Health</h2>
        <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadPlanSection(7)" data-tooltip="Download Section 7 logistics and contacts catalog as a TXT file.">Download Logistics (TXT)</button>
      </div>
  `;

  targetSystems.forEach(sys => {
    const l = sys.logistics || { deliveryAddress: "Not Set", accessRestrictions: "Not Set", shippingAlert: "None" };
    const c = sys.contacts || { name: "Not Set", phone: "Not Set", email: "Not Set", nssUsername: "Not Set" };
    const h = sys.salesHealth || { accountManager: "Not Set", supportTam: "Not Set", sentimentScore: 7.0, healthStatus: "Stable", upsellPotential: "None", refreshWindow: "Under Review" };
    const p = sys.projections || { growthRateGBPerDay: 100, daysToLimit: 120, limitDate: "Under Review" };
    
    html += `
      <div style="background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm); margin-bottom: 16px; font-size: 0.85rem; line-height: 1.4;">
        <div style="font-weight: 700; font-size: 0.95rem; border-bottom: 1px dashed var(--border-color); padding-bottom: 6px; margin-bottom: 10px; color: var(--accent-cyan);">${sys.systemName} (S/N: ${sys.serialNumber})</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
          <div>
            <div><strong>Delivery Address:</strong><br><span style="color: var(--text-secondary); font-style: italic;">${l.deliveryAddress}</span></div>
            <div style="margin-top: 8px;"><strong>Access Rules:</strong><br><span style="color: var(--text-secondary);">${l.accessRestrictions}</span></div>
            <div style="margin-top: 8px;"><strong>Logistics Alerts:</strong><br><span style="color: ${l.shippingAlert.toLowerCase() !== 'none' ? 'var(--status-critical)' : 'var(--status-normal)'}; font-weight: 500;">${l.shippingAlert}</span></div>
            <div style="margin-top: 8px;"><strong>Storage Growth Runway:</strong><br><span style="color: ${p.daysToLimit < 90 ? 'var(--status-critical)' : 'var(--status-normal)'}; font-weight: 600;">${p.daysToLimit} Days remaining</span> (Est. limit date: ${p.limitDate})</div>
          </div>
          <div>
            <div><strong>Primary Site Contact:</strong><br><span style="color: var(--text-secondary);">${c.name} (${c.phone} / ${c.email})</span></div>
            <div style="margin-top: 8px;"><strong>Sales Lead & Support TAM:</strong><br><span style="color: var(--text-secondary);">AM: ${h.accountManager} | TAM: ${h.supportTam}</span></div>
            <div style="margin-top: 8px; display: flex; gap: 20px;">
              <div><strong>CSAT Score:</strong> <span style="font-weight: 700; color: var(--accent-cyan);">${h.sentimentScore.toFixed(1)}/10</span></div>
              <div><strong>Tech Refresh window:</strong> <span style="font-weight: 700; color: var(--status-warning);">${h.refreshWindow}</span></div>
            </div>
          </div>
        </div>
      </div>
    `;
  });

  html += `
    </div>

    <!-- Guidelines and Proceeding Steps Section -->
    <div class="plan-section" data-section-index="8" style="display: none; margin-top: 32px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">
        <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">8. Operational Guidelines & Proceeding Steps</h2>
        <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadPlanSection(8)" data-tooltip="Download Section 8 change control guidelines as a TXT file.">Download Guidelines (TXT)</button>
      </div>
      
      <div style="margin-bottom: 18px;">
        <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin-bottom: 6px;">A. Implementing Changes via NetApp Change Control</h4>
        <p style="font-size: 0.85rem; line-height: 1.4; color: var(--text-secondary);">
          To minimize risk when applying technical fixes (e.g., replacing hardware spare parts, updating shelf SAS cabling, or performing software/switch firmware upgrades), ensure you adhere to NetApp change control guidelines:
        </p>
        <ul style="margin-left: 20px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4; margin-top: 6px;">
          <li><strong>Upgrade Advisor</strong>: Always run the 'Upgrade Advisor' script inside Active IQ Digital Advisor to generate a customized configuration checklist before performing any ONTAP updates.</li>
          <li><strong>Pre-upgrade Checklists</strong>: Run cluster health checks: 'system health alert show' and verify that replication paths are stable.</li>
          <li><strong>Switch Upgrades</strong>: For cluster switch ISSU, verify port redundancy using <code>show interface status</code> and ensure peer interconnect links are online. For MetroCluster systems, upgrade switch firmware strictly one switch at a time, validating fabric sync via <code>switchshow</code> before proceeding to the partner site.</li>
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
          <li><strong>Coordinate support renewal quotes</strong> for all systems identified in support reports.</li>
          <li><strong>Create internal IT ticket instances</strong> for the high-priority technical items in Section 2, attaching the generated remediation steps.</li>
          <li><strong>Verify delivery credentials</strong> and clearance permissions with site contacts listed in Section 6 before shipping parts.</li>
          <li><strong>Review the Security advisories</strong> in Section 3 and schedule OS micro-patches or workaround applications to block exposures.</li>
        </ol>
      </div>
    </div>

    <!-- Deliverables and Drafts Section -->
    <div class="plan-section" data-section-index="9" style="display: none; margin-top: 32px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">
        <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">9. Executable Account Deliverables</h2>
      </div>
      
      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">A. Draft Customer Alert Email Notification</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('EMAIL')">Download Email Draft (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Copy and customize this email to notify the customer's operations team regarding active risks and support cases.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${draftEmailText}</textarea>
      </div>

      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">B. Storage Upgrade & Hardware Refresh Proposal Draft</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('PROPOSAL')">Download Proposal Draft (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">A formal proposal draft to request funding or approvals for target OS updates and hardware contract renewals.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${draftProposalText}</textarea>
      </div>

      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">C. Internal Operations Coordination Ticket Template</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('TICKET')">Download Ticket Template (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Create an internal IT ticket to dispatch technicians or coordinate parts delivery based on logistics rules.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${internalTicketText}</textarea>
      </div>
    </div>
  `;

  planBody.innerHTML = html;
  
  // Render plan sub-tabs bar dynamically
  const planTabsHeader = document.getElementById("planTabsHeader");
  if (planTabsHeader) {
    planTabsHeader.style.display = "flex";
    planTabsHeader.innerHTML = `
      <button class="plan-tab-btn active" data-tab-index="1" onclick="switchPlanTab(1)">1. Summary</button>
      <button class="plan-tab-btn" data-tab-index="2" onclick="switchPlanTab(2)">2. Technical Risks ${allRisks.length > 0 ? `(${allRisks.length})` : ''}</button>
      <button class="plan-tab-btn" data-tab-index="3" onclick="switchPlanTab(3)">3. Security advisories ${allSecurityAdvisories.length > 0 ? `(${allSecurityAdvisories.length})` : ''}</button>
      <button class="plan-tab-btn" data-tab-index="4" onclick="switchPlanTab(4)">4. Support Cases ${allSupportCases.length > 0 ? `(${allSupportCases.length})` : ''}</button>
      <button class="plan-tab-btn" data-tab-index="5" onclick="switchPlanTab(5)">5. OS Upgrades ${allUpgrades.length > 0 ? `(${allUpgrades.length})` : ''}</button>
      <button class="plan-tab-btn" data-tab-index="6" onclick="switchPlanTab(6)">6. Switch Validation ${switchAlerts.length > 0 ? `(${switchAlerts.length})` : ''}</button>
      <button class="plan-tab-btn" data-tab-index="7" onclick="switchPlanTab(7)">7. Logistics & Health</button>
      <button class="plan-tab-btn" data-tab-index="8" onclick="switchPlanTab(8)">8. Guidelines</button>
      <button class="plan-tab-btn" data-tab-index="9" onclick="switchPlanTab(9)">9. Deliverables Drafts</button>
    `;
  }

  document.getElementById("planControlsPanel").style.display = "flex";
}

// Global section switcher inside generated plan
function switchPlanTab(index) {
  const sections = document.querySelectorAll(".plan-section");
  const buttons = document.querySelectorAll(".plan-tab-btn");
  
  sections.forEach(sec => {
    const secIdx = parseInt(sec.getAttribute("data-section-index"));
    if (secIdx === index) {
      sec.style.display = "block";
      sec.classList.add("active");
    } else {
      sec.style.display = "none";
      sec.classList.remove("active");
    }
  });
  
  buttons.forEach(btn => {
    const btnIdx = parseInt(btn.getAttribute("data-tab-index"));
    if (btnIdx === index) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

// Download report of a specific Action Plan section as plain text
function downloadPlanSection(index) {
  const selectValue = document.getElementById("planTargetSelect").value;
  let targetSystems = [];
  let scopeTitle = "";
  
  if (selectValue === "ALL") {
    targetSystems = getFilteredSystems();
    scopeTitle = "Total Portfolio";
  } else if (selectValue.startsWith("CUST:")) {
    const custName = selectValue.substring(5);
    targetSystems = state.systems.filter(s => s.customerName === custName);
    scopeTitle = `Customer: ${custName}`;
  } else if (selectValue.startsWith("GRP:")) {
    const groupId = selectValue.substring(4);
    const grp = state.groups.find(g => g.id === groupId);
    if (grp) {
      targetSystems = state.systems.filter(s => grp.systemSerials.includes(s.serialNumber));
      scopeTitle = `Group: ${grp.name}`;
    }
  } else if (selectValue.startsWith("WL:")) {
    const wlId = selectValue.substring(3);
    const wl = state.watchlists.find(w => w.id === wlId);
    if (wl) {
      targetSystems = state.systems.filter(s => wl.systemSerials.includes(s.serialNumber));
      scopeTitle = `Watchlist: ${wl.name}`;
    }
  } else if (selectValue.startsWith("SYS:")) {
    const serial = selectValue.substring(4);
    const found = state.systems.find(s => s.serialNumber === serial);
    if (found) targetSystems = [found];
    scopeTitle = `System: ${found ? found.systemName : serial}`;
  }
  
  const cleanScope = scopeTitle.replace(/[^a-z0-9]/gi, '_');
  
  let filename = "";
  let text = "";
  
  const allRisks = [];
  const allUpgrades = [];
  const expiringContracts = [];
  const activeFAs = [];
  const allSecurityAdvisories = [];
  const allSupportCases = [];
  const switchAlerts = [];
  
  targetSystems.forEach(sys => {
    sys.risks.forEach(r => allRisks.push({ systemName: sys.systemName, ...r }));
    if (sys.upgrades.targetVersion !== "Up to Date") {
      allUpgrades.push({ systemName: sys.systemName, platform: sys.platform, ...sys.upgrades });
    }
    if (sys.contracts.daysRemaining <= 90) {
      expiringContracts.push({ systemName: sys.systemName, ...sys.contracts });
    }
    sys.fieldActions.forEach(fa => activeFAs.push({ systemName: sys.systemName, ...fa }));
    if (sys.securityBulletins) {
      sys.securityBulletins.forEach(sb => allSecurityAdvisories.push({ systemName: sys.systemName, ...sb }));
    }
    if (sys.supportCases) {
      sys.supportCases.forEach(sc => allSupportCases.push({ systemName: sys.systemName, ...sc }));
    }
    const sws = getSystemSwitches(sys);
    sws.forEach(sw => {
      if (sw.status !== "Optimal") {
        switchAlerts.push({ systemName: sys.systemName, ...sw });
      }
    });
  });

  if (index === 1) {
    filename = `executive_summary_${cleanScope}.txt`;
    text = `NETAPP EXECUTIVE SUMMARY REPORT
Scope: ${scopeTitle}
Date Generated: ${new Date().toISOString().split('T')[0]}
Total Systems Audited: ${targetSystems.length}

METRICS SUMMARY:
- Technical Risks: ${allRisks.length}
- Security Advisories: ${allSecurityAdvisories.length}
- Open Support Cases: ${allSupportCases.length}
- Expiring Contracts: ${expiringContracts.length}
- Active Field Actions: ${activeFAs.length}

This document compiles the high-level metrics generated from telemetry data analyzed by NetApp Active IQ Digital Advisor.`;
  } else if (index === 2) {
    filename = `prioritized_risks_${cleanScope}.txt`;
    text = `NETAPP PRIORITIZED TECHNICAL RISKS REPORT
Scope: ${scopeTitle}

${allRisks.length === 0 ? "✓ No technical risk signatures identified across the monitored scope." : 
  allRisks.map((r, idx) => `Item 2.${idx + 1}: ${r.category} Risk - ${r.systemName} [Severity: ${r.severity.toUpperCase()}]
- Issue: ${r.description}
- Root Cause: ${r.remediationPlan ? r.remediationPlan.cause : "Undetermined"}
- Operations Impact: ${r.remediationPlan ? r.remediationPlan.impact : "Undetermined"}
- Remediation steps:
${r.remediationPlan ? r.remediationPlan.steps.map((s, i) => `   ${i+1}. ${s}`).join("\n") : "   1. Review standard operating guidelines."}
- Trade-offs:
${r.remediationPlan ? r.remediationPlan.options.map(o => `   * ${o}`).join("\n") : "   * Contact NetApp Support."}
`).join("\n\n")}`;
  } else if (index === 3) {
    filename = `security_advisories_${cleanScope}.txt`;
    text = `NETAPP SECURITY ADVISORIES REPORT
Scope: ${scopeTitle}

${allSecurityAdvisories.length === 0 ? "✓ No security vulnerabilities mapped against release baselines." :
  allSecurityAdvisories.map((s, idx) => `SA-ID: ${s.id} - ${s.systemName} [Severity: ${s.severity.toUpperCase()}]
- Title: ${s.title}
- Mitigation: ${s.mitigation}
- Status: ${s.status}
`).join("\n\n")}`;
  } else if (index === 4) {
    filename = `support_cases_${cleanScope}.txt`;
    text = `NETAPP ACTIVE SUPPORT CASES REPORT
Scope: ${scopeTitle}

${allSupportCases.length === 0 ? "✓ No active support cases open in the NetApp Support portal." :
  allSupportCases.map((c, idx) => `Case ID: ${c.id} - ${c.systemName} [Severity: ${c.severity}]
- Title: ${c.title}
- Criticality: ${c.criticality || "Normal"}
- Next Action Owner: ${c.nextActionBy || "Under Review"}
- Latest TAM Notes: ${c.ownerNotes}
- Status: ${c.status} | Opened: ${c.createdDate} | Updated: ${c.lastUpdated}
`).join("\n\n")}`;
  } else if (index === 5) {
    filename = `os_upgrades_${cleanScope}.txt`;
    text = `NETAPP RECOMMENDED OS UPGRADES ROADMAP
Scope: ${scopeTitle}

${allUpgrades.length === 0 ? "✓ All systems are running target version baselines." :
  allUpgrades.map(u => `System: ${u.systemName} [Urgency: ${u.urgency}]
- Current OS: ${targetSystems.find(s => s.systemName === u.systemName)?.ontapVersion || "unknown"}
- Recommended OS Target Version: ${u.targetVersion}
- Platform Model: ${u.platform}
- Latest Supported OS Version: ${getLatestSupportedVersion(u.platform)}
- Expected Upgrade Benefits: ${u.benefits}
`).join("\n\n")}`;
  } else if (index === 6) {
    filename = `switch_validation_${cleanScope}.txt`;
    text = `NETAPP NETWORK SWITCH & FABRIC VALIDATION CHECKLIST
Scope: ${scopeTitle}

${switchAlerts.length === 0 ? "✓ All interconnect and storage network fabric switches match validated firmware baselines." :
  switchAlerts.map(sw => `System: ${sw.systemName} | Switch: ${sw.model} (${sw.type}) [Status: ${sw.status}]
- Switch S/N: ${sw.serialNumber} | IP: ${sw.ipAddress}
- Current Firmware: ${sw.firmware} | Target Firmware: ${sw.targetFirmware} | Latest Supported: ${getLatestSupportedVersion(sw.model)}
- Validation Drift Details: ${sw.validationDetails}
`).join("\n\n")}`;
  } else if (index === 7) {
    filename = `site_logistics_${cleanScope}.txt`;
    text = `NETAPP SITE LOGISTICS & CUSTOMER HEALTH REPORT
Scope: ${scopeTitle}

${targetSystems.map(sys => {
  const l = sys.logistics || { deliveryAddress: "Not Set", accessRestrictions: "Not Set", shippingAlert: "None" };
  const c = sys.contacts || { name: "Not Set", phone: "Not Set", email: "Not Set" };
  const h = sys.salesHealth || { accountManager: "Not Set", supportTam: "Not Set", sentimentScore: 7.0, healthStatus: "Stable" };
  return `SYSTEM: ${sys.systemName} (S/N: ${sys.serialNumber})
- Delivery Address: ${l.deliveryAddress}
- Access restrictions: ${l.accessRestrictions}
- Primary Contact: ${c.name} (${c.phone} / ${c.email})
- Sales Rep: AM: ${h.accountManager} | TAM: ${h.supportTam}
- CSAT Score: ${h.sentimentScore.toFixed(1)}/10 [Status: ${h.healthStatus}]
`;
}).join("\n\n")}`;
  } else if (index === 8) {
    filename = `operational_guidelines_${cleanScope}.txt`;
    text = `NETAPP OPERATIONAL GUIDELINES & CHANGE CONTROL
Scope: ${scopeTitle}

A. CHANGE CONTROL PROCEDURES
- GENERATE UPGRADE ADVISOR: Always run the Upgrade Advisor script inside Active IQ Digital Advisor.
- PRE-UPGRADE CHECKLISTS: Run 'system health alert show' and verify replication path stability.
- SWITCH FIRMWARE: Upgrade switch firmware strictly one switch at a time, validating fabric sync via 'switchshow' before upgrading the partner.

B. 3RD-PARTY VIRTUALIZATION COMPLIANCE
- VMware Multipathing: Confirm ESXi hosts utilize round robin policies with IOPS limit=1.
- Astra Trident: Coordinate Trident upgrades alongside Kubernetes API migrations to avoid CSI mount failures.`;
  }
  
  if (filename && text) {
    triggerFileDownload(filename, text);
  }
}

// Download deliverables helper by type and active environment scope
function downloadDeliverable(type) {
  let targetSystems = [];
  let scopeTitle = "";
  
  if (state.activeFilterType === "ALL") {
    targetSystems = getFilteredSystems();
    const query = (state.activeSearchQuery || "").trim();
    scopeTitle = query !== "" ? "Filtered_Portfolio" : "All_Systems";
  } else if (state.activeFilterType === "CUSTOMER") {
    const custName = state.activeFilterValue;
    targetSystems = state.systems.filter(s => s.customerName === custName);
    scopeTitle = `Customer_${custName}`;
  } else if (state.activeFilterType === "GROUP") {
    const groupId = state.activeFilterValue;
    const grp = state.groups.find(g => g.id === groupId);
    if (grp) {
      targetSystems = state.systems.filter(s => grp.systemSerials.includes(s.serialNumber));
      scopeTitle = `Group_${grp.name}`;
    }
  } else if (state.activeFilterType === "WATCHLIST") {
    const wlId = state.activeFilterValue;
    const wl = state.watchlists.find(w => w.id === wlId);
    if (wl) {
      targetSystems = state.systems.filter(s => wl.systemSerials.includes(s.serialNumber));
      scopeTitle = `Watchlist_${wl.name}`;
    }
  }

  if (targetSystems.length === 0) {
    alert("No active systems found in the current scope to compile this deliverable. Please adjust your Account Filters.");
    return;
  }

  // Sanitize filename scope string
  const cleanScope = scopeTitle.replace(/[^a-z0-9_]/gi, '_');

  const allRisks = [];
  const allUpgrades = [];
  const expiringContracts = [];
  const allSupportCases = [];

  targetSystems.forEach(sys => {
    sys.risks.forEach(r => allRisks.push({ systemName: sys.systemName, ...r }));
    if (sys.upgrades.targetVersion !== "Up to Date") {
      allUpgrades.push({ systemName: sys.systemName, platform: sys.platform, ...sys.upgrades });
    }
    if (sys.contracts.daysRemaining <= 90) {
      expiringContracts.push({ systemName: sys.systemName, ...sys.contracts });
    }
    if (sys.supportCases) {
      sys.supportCases.forEach(sc => allSupportCases.push({ systemName: sys.systemName, ...sc }));
    }
  });

  if (type === 'EMAIL') {
    const emailRisksList = allRisks.map(r => ` - System: ${r.systemName} | Category: ${r.category} | Issue: ${r.description}`).join("\n");
    const emailCasesList = allSupportCases.map(c => ` - Case ID: ${c.id} | Subject: ${c.title} | Status: ${c.status}`).join("\n");
    const text = `Subject: NetApp Operational Health & Risk Advisory Alert - ${scopeTitle.replace(/_/g, ' ')}

Dear Storage Operations Team,

This is a proactive advisory update from your NetApp Account Team regarding the health, stability, and operational risk metrics of your storage systems. Active IQ Digital Advisor has analyzed your configurations and identified items requiring your review:

${allRisks.length > 0 ? `CRITICAL/HIGH TECHNICAL RISKS:\n${emailRisksList}` : "✓ No critical or high technical configuration risks detected."}

${allSupportCases.length > 0 ? `OPEN SUPPORT TICKETS:\n${emailCasesList}` : "✓ No active open technical support cases detected."}

RECOMMENDED ACTION ITEMS:
1. Review the step-by-step remediation plans in our attached Operations Plan.
2. Schedule a maintenance window to apply critical firmware upgrades or replace degraded SAS cabling if applicable.
3. Verify logistics shipping details with site contacts before part dispatch.

If you have any questions or require assistance, please contact your account support leads.

Best Regards,
[Your Name / NetApp TAM Team]`;

    triggerFileDownload(`advisory_email_${cleanScope}.txt`, text);

  } else if (type === 'PROPOSAL') {
    const upgradeTargetsList = allUpgrades.map(u => {
      const origSys = targetSystems.find(s => s.systemName === u.systemName);
      const origVer = origSys ? origSys.ontapVersion : "unknown";
      return ` - System: ${u.systemName} | Current OS: ${origVer} | Target OS: ${u.targetVersion}`;
    }).join("\n");
    const contractExpiryList = expiringContracts.map(e => ` - System: ${e.systemName} | Support Level: ${e.supportLevel} | Expiry Date: ${e.endDate} (${e.daysRemaining} days remaining)`).join("\n");

    const text = `MEMORANDUM OF PROPOSAL: STORAGE OS UPGRADE & PLATFORM REFRESH

CUSTOMER BASE: ${scopeTitle.replace(/_/g, ' ')}
PREPARED BY: NetApp Technical Account Management (TAM)

1. RECOMMENDED OPERATING SYSTEM UPGRADES
To align your systems with NetApp's Interoperability Matrix Tool (IMT) and apply critical security/performance microcode updates, we recommend the following target version updates:
${allUpgrades.length > 0 ? upgradeTargetsList : "✓ All systems in scope are currently running recommended stable releases."}

2. SUPPORT CONTRACT RENEWALS & PLATFORM REFRESH
The following storage controllers are approaching contract expiration or end-of-support deadlines and require immediate renewal or node swap planning:
${expiringContracts.length > 0 ? contractExpiryList : "✓ All active contracts have > 90 days remaining."}

3. HARDWARE EXPANSION OPPORTUNITIES
To maintain performance headroom and address storage growth runway targets, we propose expanding:
 - FabricPool cloud tiering to offload cold blocks to Object Storage.
 - Target tech refresh timelines matching upcoming windows.`;

    triggerFileDownload(`upgrade_proposal_${cleanScope}.txt`, text);

  } else if (type === 'TICKET') {
    const text = `TICKET TITLE: NetApp Dispatch & Parts Coordination - ${scopeTitle.replace(/_/g, ' ')}

TICKET CLASSIFICATION: Infrastructure Operations -> NetApp Storage Maintenance
TICKET SEVERITY: S2 - Major (Logistics & Maintenance Window Required)

DESCRIPTION:
Please initiate change control and stage parts coordination for the following NetApp systems:

${targetSystems.map(s => {
  const l = s.logistics || { deliveryAddress: "Not Set", accessRestrictions: "Not Set" };
  const c = s.contacts || { name: "Not Set", phone: "Not Set" };
  return `SYSTEM: ${s.systemName} (S/N: ${s.serialNumber})
- Delivery Address: ${l.deliveryAddress}
- Access Rules: ${l.accessRestrictions}
- Site Contact: ${c.name} (${c.phone})`;
}).join("\n\n")}

LOGISTICS COMPLIANCE INSTRUCTIONS:
- Verify active Secret/Biometric clearance criteria with site contacts prior to dispatch.
- Cross-reference active shipment codes against tracking APIs.`;

    triggerFileDownload(`dispatch_ticket_${cleanScope}.txt`, text);

  } else if (type === 'CSV') {
    const headers = ["Customer Name", "System Name", "Cluster Name", "Serial Number", "Platform Model", "ONTAP Version", "Status", "Risks Count", "Contract End Date", "TAM Owner"];
    const rows = targetSystems.map(sys => [
      sys.customerName,
      sys.systemName,
      sys.clusterName,
      sys.serialNumber,
      sys.platform,
      sys.ontapVersion,
      sys.status,
      sys.risks.length,
      sys.contracts.endDate,
      sys.salesHealth ? sys.salesHealth.supportTam : "Not Set"
    ]);
    const csvContent = [headers.join(","), ...rows.map(r => r.map(val => `"${String(val).replace(/"/g, '""')}"`).join(","))].join("\n");
    
    triggerFileDownload(`systems_audit_${cleanScope}.csv`, csvContent);
  }
}

function triggerFileDownload(filename, text) {
  const element = document.createElement('a');
  element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
  element.setAttribute('download', filename);
  element.style.display = 'none';
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
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
        <\/script>
      </body>
    </html>
  `);
  printWindow.document.close();
}

// 8. Collapsible Sidebar Groups Tree Builders
function loadSavedFilters() {
  const saved = safeGetItem("aiq_saved_filters");
  return saved ? JSON.parse(saved) : [];
}

function starCurrentSearch() {
  const query = (document.getElementById("searchInput").value || "").trim();
  if (!query) {
    alert("Please type a search query first to star it.");
    return;
  }
  const name = prompt("Enter a name for this starred filter:", query);
  if (!name) return;

  const savedFilters = loadSavedFilters();
  if (savedFilters.some(f => f.query === query)) {
    alert("This exact search query is already starred.");
    return;
  }

  savedFilters.push({
    id: "filter_" + Date.now(),
    name: name.trim(),
    query: query
  });
  safeSetItem("aiq_saved_filters", JSON.stringify(savedFilters));
  
  renderSidebarGroups();
  alert(`Starred filter "${name}" saved!`);
}

function deleteSavedFilter(event, id) {
  event.stopPropagation();
  let savedFilters = loadSavedFilters();
  savedFilters = savedFilters.filter(f => f.id !== id);
  safeSetItem("aiq_saved_filters", JSON.stringify(savedFilters));
  renderSidebarGroups();
}

function renderSidebarGroups() {
  const container = document.getElementById("sidebarGroupsList");
  if (!container) return;
  container.innerHTML = "";

  // 1. Watchlists (Fetched from Active IQ API or Mocked)
  if (state.watchlists && state.watchlists.length > 0) {
    const wlHeader = document.createElement("div");
    wlHeader.className = "tree-section-header";
    wlHeader.innerText = "Active IQ Watchlists";
    container.appendChild(wlHeader);

    state.watchlists.forEach(wl => {
      const item = document.createElement("div");
      item.className = "tree-item";
      if (state.activeFilterType === "WATCHLIST" && state.activeFilterValue === wl.id) {
        item.classList.add("active");
      }
      item.onclick = (e) => {
        e.stopPropagation();
        setFilter("WATCHLIST", wl.id);
      };

      const wlSystems = state.systems.filter(s => wl.systemSerials.includes(s.serialNumber));
      const riskCount = wlSystems.reduce((acc, s) => acc + s.risks.length, 0);
      const badge = riskCount > 0 ? `<span class="tree-badge ${wlSystems.some(s => s.status === 'critical') ? 'critical' : 'warning'}">${riskCount}</span>` : '';

      item.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
        <span class="tree-text">${wl.name}</span>
        <div style="display: flex; gap: 4px; align-items: center; flex-shrink: 0; position: relative; z-index: 10;">
          ${badge}
        </div>
      `;
      container.appendChild(item);
    });
  }

  // 2. Group by Customers (calculated dynamically)
  const customers = [...new Set(state.systems.map(s => s.customerName))];
  
  if (customers.length > 0) {
    const custHeader = document.createElement("div");
    custHeader.className = "tree-section-header";
    custHeader.style.marginTop = "16px";
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
      
      const caseCount = custSystems.reduce((acc, s) => acc + (s.supportCases ? s.supportCases.length : 0), 0);
      const caseBadge = caseCount > 0 ? `<span class="tree-badge info" style="background: var(--status-info); cursor: pointer;" onclick="navigateToSupportCases('CUSTOMER', '${cust}', event)" data-tooltip="Click to view all ${caseCount} open support cases">✉ ${caseCount}</span>` : '';

      item.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
        <span class="tree-text">${cust}</span>
        <div style="display: flex; gap: 4px; align-items: center; flex-shrink: 0; position: relative; z-index: 10;">
          ${caseBadge}
          ${badge}
        </div>
      `;
      container.appendChild(item);
    });
  }

  // 3. Custom User Defined Groups
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

      const caseCount = groupSystems.reduce((acc, s) => acc + (s.supportCases ? s.supportCases.length : 0), 0);
      const caseBadge = caseCount > 0 ? `<span class="tree-badge info" style="background: var(--status-info); cursor: pointer;" onclick="navigateToSupportCases('GROUP', '${grp.id}', event)" data-tooltip="Click to view all ${caseCount} open support cases">✉ ${caseCount}</span>` : '';

      item.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
        <span class="tree-text">${grp.name}</span>
        <div style="display: flex; gap: 4px; align-items: center; flex-shrink: 0; position: relative; z-index: 10;">
          ${caseBadge}
          ${badge}
        </div>
      `;
      container.appendChild(item);
    });
  }

  // 4. Starred & Dynamic Filters
  const savedFilters = loadSavedFilters();
  if (savedFilters.length > 0) {
    const filterHeader = document.createElement("div");
    filterHeader.className = "tree-section-header";
    filterHeader.style.marginTop = "16px";
    filterHeader.innerText = "Starred Filters (Dynamic)";
    container.appendChild(filterHeader);

    savedFilters.forEach(f => {
      const item = document.createElement("div");
      item.className = "tree-item";
      if (state.activeSearchQuery === f.query) {
        item.classList.add("active");
      }
      
      item.innerHTML = `
        <span style="color: var(--status-warning); margin-right: 8px; font-size: 0.85rem;">★</span>
        <span class="tree-text" title="Query: ${f.query}">${f.name}</span>
        <button class="action-btn secondary delete-filter-btn" style="opacity: 0.6; padding: 2px 6px; font-size: 0.65rem; border-color: transparent; margin-left: auto; background: transparent; color: var(--status-critical);" onclick="deleteSavedFilter(event, '${f.id}')" data-tooltip="Delete this starred filter shortcut.">×</button>
      `;
      
      item.onclick = (e) => {
        document.getElementById("searchInput").value = f.query;
        state.activeSearchQuery = f.query;
        renderOverviewTable();
        renderSidebarGroups();
        renderCharts();
      };
      container.appendChild(item);
    });
  }
}

function copyToClipboard(text, event) {
  if (event) event.stopPropagation();
  navigator.clipboard.writeText(text).then(() => {
    showToast("Copied to clipboard: " + text);
  }).catch(err => {
    console.error("Failed to copy: ", err);
  });
}

function showToast(message) {
  let toast = document.getElementById("toastNotification");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toastNotification";
    toast.style.position = "fixed";
    toast.style.bottom = "20px";
    toast.style.right = "20px";
    toast.style.backgroundColor = "rgba(0, 230, 118, 0.95)";
    toast.style.color = "#000";
    toast.style.padding = "10px 20px";
    toast.style.borderRadius = "4px";
    toast.style.fontWeight = "600";
    toast.style.fontSize = "0.85rem";
    toast.style.zIndex = "9999";
    toast.style.transition = "opacity 0.3s ease";
    toast.style.boxShadow = "0 4px 12px rgba(0,230,118,0.2)";
    document.body.appendChild(toast);
  }
  toast.innerText = message;
  toast.style.opacity = "1";
  toast.style.display = "block";
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => { toast.style.display = "none"; }, 300);
  }, 2000);
}

function setFilter(type, value) {
  state.activeFilterType = type;
  state.activeFilterValue = value;
  state.selectedSAMSystemSerial = "ALL";
  state.selectedCSMSystemSerial = "ALL";
  
  // Context-aware update: stay on the current tab but refresh system list scope
  switchTab(state.currentTab);
  
  renderSidebarGroups();
}

function navigateToSupportCases(type, value, event) {
  if (event) {
    event.stopPropagation();
    event.preventDefault();
  }
  
  if (type === "SYSTEM") {
    const sys = state.systems.find(s => s.serialNumber === value);
    if (sys) {
      state.currentTab = "sam";
      setFilter("CUSTOMER", sys.customerName);
      state.selectedSAMSystemSerial = value;
      switchTab("sam");
    }
  } else if (type === "CUSTOMER") {
    state.currentTab = "sam";
    setFilter("CUSTOMER", value);
    switchTab("sam");
  } else if (type === "GROUP") {
    state.currentTab = "sam";
    setFilter("GROUP", value);
    switchTab("sam");
  }
}

function resetFilter() {
  state.activeFilterType = "ALL";
  state.activeFilterValue = "";
  state.activeSearchQuery = "";
  state.activeKpiFilter = "NONE";
  state.selectedSAMSystemSerial = "ALL";
  state.selectedCSMSystemSerial = "ALL";
  
  // Clear KPI card active classes
  const cards = ["kpiCardAll", "kpiCardCritical", "kpiCardWarning", "kpiCardContract"];
  cards.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove("active");
  });

  const searchInput = document.getElementById("searchInput");
  if (searchInput) searchInput.value = "";
  switchTab(state.currentTab);
  renderSidebarGroups();
}

function resetFilterAndGoToOverview() {
  state.activeFilterType = "ALL";
  state.activeFilterValue = "";
  state.activeSearchQuery = "";
  state.activeKpiFilter = "NONE";
  state.selectedSAMSystemSerial = "ALL";
  state.selectedCSMSystemSerial = "ALL";
  
  const cards = ["kpiCardAll", "kpiCardCritical", "kpiCardWarning", "kpiCardContract"];
  cards.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove("active");
  });

  const searchInput = document.getElementById("searchInput");
  if (searchInput) searchInput.value = "";
  switchTab("overview");
  renderSidebarGroups();
}

// 9. Custom Group & Metadata Editor Logic (in Settings panel)
// 9. Custom Group & Metadata Editor Logic (in Settings panel)
function editCustomGroup(groupId) {
  const grp = state.groups.find(g => g.id === groupId);
  if (!grp) return;
  
  state.editingGroupId = groupId;
  document.getElementById("subgroupFormTitle").innerText = "Edit Custom Subgroup";
  document.getElementById("newGroupNameInput").value = grp.name;
  
  document.querySelectorAll(".group-system-checkbox").forEach(chk => {
    chk.checked = grp.systemSerials.includes(chk.value);
  });
  
  document.getElementById("saveSubgroupBtn").innerText = "Update Subgroup";
  document.getElementById("cancelSubgroupEditBtn").style.display = "inline-block";
}

function cancelSubgroupEdit() {
  state.editingGroupId = null;
  document.getElementById("subgroupFormTitle").innerText = "Create Custom Subgroup";
  document.getElementById("newGroupNameInput").value = "";
  document.querySelectorAll(".group-system-checkbox").forEach(chk => chk.checked = false);
  document.getElementById("saveSubgroupBtn").innerText = "Create Subgroup";
  document.getElementById("cancelSubgroupEditBtn").style.display = "none";
}

function createNewSystemPrompt() {
  const serial = prompt("Enter Serial Number for New System:");
  if (!serial) return;
  const serialClean = serial.trim();
  if (state.systems.some(s => s.serialNumber === serialClean)) {
    alert("A system with this serial number already exists!");
    return;
  }
  const name = prompt("Enter System Name:", "new-system-" + serialClean);
  if (!name) return;
  const customer = prompt("Enter Customer Account Name:", "Default Customer");
  if (!customer) return;

  const newSys = {
    serialNumber: serialClean,
    systemName: name.trim(),
    customerName: customer.trim(),
    clusterName: "cluster-" + name.trim(),
    platform: "FAS2750",
    ontapVersion: "ONTAP 9.12.1",
    status: "normal",
    risks: [],
    upgrades: { targetVersion: "Up to Date", urgency: "none", benefits: "Running recommended release." },
    contracts: { endDate: "2027-12-31", daysRemaining: 500, status: "normal", supportLevel: "Core Support" },
    fieldActions: [],
    hypervisors: [],
    securityBulletins: [],
    supportCases: [],
    logistics: { deliveryAddress: "Site HQ", accessRestrictions: "Standard Business Hours", shippingAlert: "None" },
    contacts: { name: "John Doe", phone: "555-0100", email: "johndoe@example.com", nssUsername: "jdoe" },
    salesHealth: { accountManager: "Account Rep", supportTam: "TAM Rep", sentimentScore: 9.0, healthStatus: "Stable", upsellPotential: "None", refreshWindow: "Q4 2027" },
    projections: { growthRateGBPerDay: 50, daysToLimit: 365, limitDate: "2027-07-06" },
    efficiency: { ratio: "2.4:1" }
  };

  state.systems.push(newSys);
  saveSystems();
  populateSystemSelectors();
  updateSearchSuggestions();
  
  document.getElementById("editorSystemSelect").value = serialClean;
  loadSelectedSystemMetadataForEdit();
  
  switchTab(state.currentTab);
  alert(`System "${name.trim()}" (S/N: ${serialClean}) created successfully! Additional specifications can be edited below.`);
}

function deleteCurrentSystem() {
  const select = document.getElementById("editorSystemSelect");
  if (!select || !select.value) return;
  const serial = select.value;
  const found = state.systems.find(s => s.serialNumber === serial);
  if (!found) return;

  if (!confirm(`Are you sure you want to delete system "${found.systemName}" (S/N: ${serial})?`)) {
    return;
  }

  state.systems = state.systems.filter(s => s.serialNumber !== serial);
  state.groups.forEach(g => {
    g.systemSerials = g.systemSerials.filter(sn => sn !== serial);
  });
  
  saveSystems();
  populateSystemSelectors();
  updateSearchSuggestions();
  
  if (state.systems.length > 0) {
    state.selectedSystem = state.systems[0];
    select.value = state.selectedSystem.serialNumber;
    loadSelectedSystemMetadataForEdit();
  } else {
    state.selectedSystem = null;
  }
  
  switchTab(state.currentTab);
  alert("System deleted successfully!");
}

function updateSearchSuggestions() {
  // Legacy - dynamic custom autocomplete dropdown handles this now
}

function updateCustomSearchSuggestions(query) {
  const container = document.getElementById("searchSuggestionsContainer");
  if (!container) return;
  
  const val = query.trim().toLowerCase();
  if (!val) {
    container.style.display = "none";
    return;
  }
  
  const matches = [];
  const seen = new Set();
  
  state.systems.forEach(sys => {
    // Customer
    if (sys.customerName.toLowerCase().includes(val) && !seen.has(`CUST:${sys.customerName}`)) {
      seen.add(`CUST:${sys.customerName}`);
      matches.push({ text: sys.customerName, type: "Customer", value: sys.customerName });
    }
    // System Name
    if (sys.systemName.toLowerCase().includes(val) && !seen.has(`SYS:${sys.systemName}`)) {
      seen.add(`SYS:${sys.systemName}`);
      matches.push({ text: sys.systemName, type: "System", value: sys.systemName });
    }
    // Cluster
    if (sys.clusterName.toLowerCase().includes(val) && !seen.has(`CLUS:${sys.clusterName}`)) {
      seen.add(`CLUS:${sys.clusterName}`);
      matches.push({ text: sys.clusterName, type: "Cluster", value: sys.clusterName });
    }
    // Serial
    if (sys.serialNumber.toLowerCase().includes(val) && !seen.has(`SER:${sys.serialNumber}`)) {
      seen.add(`SER:${sys.serialNumber}`);
      matches.push({ text: sys.serialNumber, type: "Serial Number", value: sys.serialNumber });
    }
  });
  
  if (matches.length === 0) {
    container.style.display = "none";
    return;
  }
  
  container.innerHTML = "";
  matches.slice(0, 8).forEach(match => {
    const div = document.createElement("div");
    div.className = "custom-autocomplete-item";
    div.innerHTML = `
      <span>${match.text}</span>
      <span class="type-badge">${match.type}</span>
    `;
    div.onclick = (e) => {
      e.stopPropagation();
      const searchInput = document.getElementById("searchInput");
      if (searchInput) {
        searchInput.value = match.value;
        state.activeSearchQuery = match.value;
      }
      container.style.display = "none";
      executeSearchGo();
    };
    container.appendChild(div);
  });
  
  container.style.display = "block";
}

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
  
  // Render existing groups list in settings for deletion & edit
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
      <div style="display: flex; gap: 8px;">
        <button class="action-btn" style="font-size: 0.7rem; padding: 4px 8px; border-color: rgba(0,229,255,0.2);" onclick="editCustomGroup('${grp.id}')" title="Edit this subgroup's name and system assignments.">Edit</button>
        <button class="action-btn secondary" style="font-size: 0.7rem; padding: 4px 8px; color: var(--status-critical); border-color: rgba(255,51,102,0.2);" onclick="deleteCustomGroup('${grp.id}')" title="Delete this subgroup completely (does not delete member systems).">Delete</button>
      </div>
    `;
    listContainer.appendChild(item);
  });
}

function populateLogisticsEditor() {
  const select = document.getElementById("editorSystemSelect");
  if (!select) return;
  
  const originalVal = select.value;
  select.innerHTML = "";
  
  state.systems.forEach(sys => {
    const opt = document.createElement("option");
    opt.value = sys.serialNumber;
    opt.innerText = sys.systemName;
    select.appendChild(opt);
  });
  
  if (originalVal && state.systems.some(s => s.serialNumber === originalVal)) {
    select.value = originalVal;
  }
  
  loadSelectedSystemMetadataForEdit();
}

function loadSelectedSystemMetadataForEdit() {
  const serial = document.getElementById("editorSystemSelect").value;
  const sys = state.systems.find(s => s.serialNumber === serial);
  if (!sys) return;

  const logistics = sys.logistics || { deliveryAddress: "", accessRestrictions: "", shippingAlert: "None" };
  const contacts = sys.contacts || { name: "", phone: "", email: "", nssUsername: "" };
  const health = sys.salesHealth || { accountManager: "", supportTam: "", sentimentScore: 7.0, healthStatus: "Stable", upsellPotential: "", refreshWindow: "Under Review" };
  const proj = sys.projections || { growthRateGBPerDay: 100, daysToLimit: 120, limitDate: "Under Review", peakIops: 10000, avgLatencyMs: 2.5, historicalCapacityMonths: [10, 12, 14, 16, 18, 20], projectedCapacityMonths: [22, 24, 26] };
  const bulletins = sys.securityBulletins || [];
  const cases = sys.supportCases || [];

  document.getElementById("editSystemName").value = sys.systemName || "";
  document.getElementById("editSerialNumber").value = sys.serialNumber || "";
  document.getElementById("editCustomerName").value = sys.customerName || "";
  document.getElementById("editClusterName").value = sys.clusterName || "";
  document.getElementById("editPlatform").value = sys.platform || "";
  document.getElementById("editOntapVersion").value = sys.ontapVersion || "";

  document.getElementById("editDeliveryAddress").value = logistics.deliveryAddress;
  document.getElementById("editAccessRestrictions").value = logistics.accessRestrictions;
  document.getElementById("editShippingAlert").value = logistics.shippingAlert;

  document.getElementById("editContactName").value = contacts.name;
  document.getElementById("editContactPhone").value = contacts.phone;
  document.getElementById("editContactEmail").value = contacts.email;
  document.getElementById("editNssUsername").value = contacts.nssUsername;

  document.getElementById("editAccountManager").value = health.accountManager;
  document.getElementById("editSupportTam").value = health.supportTam;
  document.getElementById("editSentimentScore").value = health.sentimentScore;
  document.getElementById("editHealthStatus").value = health.healthStatus;
  document.getElementById("editUpsellPotential").value = health.upsellPotential;
  document.getElementById("editRefreshWindow").value = health.refreshWindow;

  // Set projections fields inside edit panel
  document.getElementById("editGrowthRate").value = proj.growthRateGBPerDay;
  document.getElementById("editDaysToLimit").value = proj.daysToLimit;
  document.getElementById("editLimitDate").value = proj.limitDate;
  document.getElementById("editPeakIops").value = proj.peakIops;
  document.getElementById("editAvgLatency").value = proj.avgLatencyMs;
  document.getElementById("editHistCapacityCSV").value = proj.historicalCapacityMonths.join(",");
  document.getElementById("editProjCapacityCSV").value = proj.projectedCapacityMonths.join(",");

  // Set Security Bulletins JSON
  document.getElementById("editSecurityBulletinsJSON").value = JSON.stringify(bulletins, null, 2);

  // Set Open Support Cases JSON
  document.getElementById("editSupportCasesJSON").value = JSON.stringify(cases, null, 2);
}

function saveSystemMetadata() {
  const serial = document.getElementById("editorSystemSelect").value;
  const idx = state.systems.findIndex(s => s.serialNumber === serial);
  if (idx === -1) return;

  const newSerial = document.getElementById("editSerialNumber").value.trim();
  const newSysName = document.getElementById("editSystemName").value.trim();
  const newCustName = document.getElementById("editCustomerName").value.trim();
  const newClusterName = document.getElementById("editClusterName").value.trim();
  const newPlatform = document.getElementById("editPlatform").value.trim();
  const newOntap = document.getElementById("editOntapVersion").value.trim();

  if (!newSerial || !newSysName || !newCustName) {
    alert("System Name, Serial Number, and Customer Name are required core fields.");
    return;
  }

  // Handle serial number change
  if (newSerial !== serial) {
    if (state.systems.some(s => s.serialNumber === newSerial)) {
      alert(`A system with serial number "${newSerial}" already exists!`);
      return;
    }
    // Update subgroup assignments
    state.groups.forEach(g => {
      g.systemSerials = g.systemSerials.map(sn => sn === serial ? newSerial : sn);
    });
  }

  state.systems[idx].serialNumber = newSerial;
  state.systems[idx].systemName = newSysName;
  state.systems[idx].customerName = newCustName;
  state.systems[idx].clusterName = newClusterName;
  state.systems[idx].platform = newPlatform;
  state.systems[idx].ontapVersion = newOntap;

  state.systems[idx].logistics = {
    deliveryAddress: document.getElementById("editDeliveryAddress").value.trim(),
    accessRestrictions: document.getElementById("editAccessRestrictions").value.trim(),
    shippingAlert: document.getElementById("editShippingAlert").value.trim()
  };

  state.systems[idx].contacts = {
    name: document.getElementById("editContactName").value.trim(),
    phone: document.getElementById("editContactPhone").value.trim(),
    email: document.getElementById("editContactEmail").value.trim(),
    nssUsername: document.getElementById("editNssUsername").value.trim()
  };

  state.systems[idx].salesHealth = {
    accountManager: document.getElementById("editAccountManager").value.trim(),
    supportTam: document.getElementById("editSupportTam").value.trim(),
    sentimentScore: parseFloat(document.getElementById("editSentimentScore").value || "7.0"),
    healthStatus: document.getElementById("editHealthStatus").value.trim(),
    upsellPotential: document.getElementById("editUpsellPotential").value.trim(),
    refreshWindow: document.getElementById("editRefreshWindow").value.trim()
  };

  // Save projections numbers
  const histCSV = document.getElementById("editHistCapacityCSV").value.trim();
  const projCSV = document.getElementById("editProjCapacityCSV").value.trim();

  state.systems[idx].projections = {
    growthRateGBPerDay: parseInt(document.getElementById("editGrowthRate").value || "100"),
    daysToLimit: parseInt(document.getElementById("editDaysToLimit").value || "120"),
    limitDate: document.getElementById("editLimitDate").value.trim(),
    peakIops: parseInt(document.getElementById("editPeakIops").value || "10000"),
    avgLatencyMs: parseFloat(document.getElementById("editAvgLatency").value || "2.5"),
    historicalCapacityMonths: histCSV ? histCSV.split(",").map(v => parseFloat(v.trim())) : [10, 11, 12, 13, 14, 15],
    projectedCapacityMonths: projCSV ? projCSV.split(",").map(v => parseFloat(v.trim())) : [16, 17, 18]
  };

  // Parse and save security bulletins JSON
  try {
    const rawJSON = document.getElementById("editSecurityBulletinsJSON").value.trim();
    state.systems[idx].securityBulletins = JSON.parse(rawJSON || "[]");
  } catch (err) {
    alert("Invalid Security Bulletins JSON format. Please verify syntax.");
    return;
  }

  // Parse and save open support cases JSON
  try {
    const rawCasesJSON = document.getElementById("editSupportCasesJSON").value.trim();
    state.systems[idx].supportCases = JSON.parse(rawCasesJSON || "[]");
  } catch (err) {
    alert("Invalid Support Cases JSON format. Please verify syntax.");
    return;
  }

  saveSystems();
  populateSystemSelectors();
  updateSearchSuggestions();

  // If the edited system was the currently selected system, update state.selectedSystem
  if (!state.selectedSystem || state.selectedSystem.serialNumber === serial) {
    state.selectedSystem = state.systems[idx];
  }

  // Re-select in the editor selector
  document.getElementById("editorSystemSelect").value = newSerial;

  // Refresh active tab views
  switchTab(state.currentTab);
  alert(`Metadata & specifications for "${newSysName}" updated successfully!`);
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

  if (state.editingGroupId) {
    const idx = state.groups.findIndex(g => g.id === state.editingGroupId);
    if (idx !== -1) {
      state.groups[idx].name = name;
      state.groups[idx].systemSerials = selectedSerials;
      saveGroups();
      cancelSubgroupEdit();
      alert("Subgroup updated successfully!");
    }
  } else {
    const newGroup = {
      id: "group_" + Date.now(),
      name: name,
      systemSerials: selectedSerials
    };

    state.groups.push(newGroup);
    saveGroups();
    nameInput.value = "";
    document.querySelectorAll(".group-system-checkbox").forEach(chk => chk.checked = false);
    alert("Group created successfully!");
  }

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

// 10. Global active status visual indicators & Settings Saves
async function saveSettings() {
  const mockToggle = document.getElementById("settingsMockModeToggle").checked;
  const refresh = document.getElementById("settingsRefreshToken").value.trim();
  const oldMockMode = state.mockMode;
  
  setMockMode(mockToggle);
  saveConfig(refresh, safeGetItem("aiq_access_token") || "", safeGetItem("aiq_token_expiry") || "");
  
  if (!mockToggle && (oldMockMode || refresh)) {
    // User enabled API mode or updated token - let's fetch!
    await loadProductionData();
  } else if (mockToggle) {
    // Reset to mock systems database
    state.systems = [...MOCK_SYSTEMS];
    saveSystems();
    if (state.systems.length > 0) {
      state.selectedSystem = state.systems[0];
    }
  }
  
  alert("Settings saved successfully.");
  switchTab("settings");
}

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

async function loadProductionData() {
  const textLabel = document.getElementById("connectionStatusText");
  const indicator = document.querySelector(".indicator");
  
  if (textLabel) textLabel.innerText = "Connecting & Loading Telemetry...";
  if (indicator) {
    indicator.className = "indicator warning"; // Amber indicator while loading
  }

  try {
    const apiSystems = await callActiveIQAPI("/systems");
    if (apiSystems && (Array.isArray(apiSystems) || (typeof apiSystems === 'object' && apiSystems !== null))) {
      const systemsList = Array.isArray(apiSystems) ? apiSystems : (apiSystems.systems || [apiSystems]);
      if (systemsList.length > 0) {
        state.systems = systemsList.map(s => {
          return {
            serialNumber: s.serialNumber || s.serial_number || "unknown",
            systemName: s.systemName || s.system_name || "unknown",
            clusterName: s.clusterName || s.cluster_name || "unknown",
            customerName: s.customerName || s.customer_name || "customer",
            ontapVersion: s.ontapVersion || s.ontap_version || s.osVersion || "9.12.1",
            platform: s.platform || s.model || "AFF A400",
            status: s.status || "normal",
            risks: s.risks || [],
            upgrades: s.upgrades || { targetVersion: "Up to Date", urgency: "None", benefits: "" },
            contracts: s.contracts || { status: "normal", endDate: "2027-01-01", daysRemaining: 180, supportLevel: "SupportEdge Premium" },
            lifecycle: s.lifecycle || { eoaDate: "2026-01-01", eosDate: "2031-01-01", isNearEos: false },
            fieldActions: s.fieldActions || [],
            efficiency: s.efficiency || { ratio: "1.0:1", logicalUsedTB: 10.0, physicalUsedTB: 10.0, spaceSavedTB: 0.0, fabricPoolTieredTB: 0.0 },
            snapmirror: s.snapmirror || { enabled: false, relationships: [] },
            hypervisors: s.hypervisors || [],
            logistics: s.logistics || { deliveryAddress: "Not Configured", accessRestrictions: "Not Configured", shippingAlert: "None" },
            contacts: s.contacts || { name: "Not Configured", phone: "Not Configured", email: "Not Configured", nssUsername: "Not Configured" },
            salesHealth: s.salesHealth || { accountManager: "Not Configured", supportTam: "Not Configured", sentimentScore: 7.0, healthStatus: "Stable", upsellPotential: "None", refreshWindow: "Under Review" },
            projections: s.projections || { growthRateGBPerDay: 100, daysToLimit: 365, limitDate: "2027-07-06", peakIops: 5000, avgLatencyMs: 2.0, historicalCapacityMonths: [10, 10, 10, 10, 10, 10], projectedCapacityMonths: [10, 10, 10] },
            securityBulletins: s.securityBulletins || [],
            supportCases: s.supportCases || []
          };
        });
        saveSystems();

        // Try fetching active watchlists from Active IQ API
        try {
          const apiWatchlists = await callActiveIQAPI("/watchlists");
          if (apiWatchlists) {
            const wlList = Array.isArray(apiWatchlists) ? apiWatchlists : (apiWatchlists.watchlists || []);
            state.watchlists = wlList.map(wl => ({
              id: wl.watchlistId || wl.id || "wl_" + Date.now(),
              name: wl.watchListName || wl.name || "Watchlist",
              systemSerials: wl.serialNumbers || wl.systemSerials || []
            }));
            saveWatchlists();
          }
        } catch (wlErr) {
          console.warn("Failed to retrieve Active IQ watchlists:", wlErr);
        }
        
        if (state.systems.length > 0) {
          state.selectedSystem = state.systems[0];
        }
        updateStatusIndicators();
        return;
      }
    }
    
    console.warn("Active IQ API returned no clusters or systems.");
    alert("Warning: The Active IQ API endpoint connected successfully, but returned an empty system listing. Falling back to cached data.");
  } catch (error) {
    console.error("Failed to fetch from Active IQ API:", error);
    alert(`Failed to load data from Active IQ API.
Reason: ${error.message}

⚠️ CORS / ORIGIN RESTRICTION:
Even though the dashboard is served via a local web server (http://localhost:8080), browser CORS (Cross-Origin Resource Sharing) security policies will block direct API calls from localhost/file origins to NetApp's API servers.

To resolve this:
1. Re-enable "Offline Demo Mode (Mock Data)" in Settings to load the demo database.
2. Install a developer browser extension (e.g., search the Chrome Web Store for "CORS Unblock" or "Allow CORS") and toggle it ON to bypass browser CORS origin checks.
3. Or launch Chrome with disabled web security.

See the README.md file for detailed CORS bypass guidelines.`);
  }

  updateStatusIndicators();
}

function handleSearch(e) {
  state.activeSearchQuery = e.target.value;
  switchTab(state.currentTab);
  renderSidebarGroups();
  updateCustomSearchSuggestions(e.target.value);
}

function executeSearchGo() {
  const query = (state.activeSearchQuery || "").trim().toLowerCase();
  if (!query) return;

  // 1. Check if query matches a customer name exactly
  const matchedCustomer = state.systems.find(s => s.customerName.toLowerCase() === query);
  if (matchedCustomer) {
    state.activeFilterType = "CUSTOMER";
    state.activeFilterValue = matchedCustomer.customerName;
    state.activeSearchQuery = "";
    state.selectedSAMSystemSerial = "ALL";
    state.selectedCSMSystemSerial = "ALL";
    const searchInput = document.getElementById("searchInput");
    if (searchInput) searchInput.value = "";
    switchTab("overview");
    renderSidebarGroups();
    return;
  }

  // 2. Check if query matches a system name, serial number, or cluster name exactly
  const matchedSystem = state.systems.find(s => 
    s.systemName.toLowerCase() === query || 
    s.serialNumber.toLowerCase() === query ||
    s.clusterName.toLowerCase() === query
  );
  if (matchedSystem) {
    selectSystem(matchedSystem.serialNumber);
    state.activeSearchQuery = "";
    const searchInput = document.getElementById("searchInput");
    if (searchInput) searchInput.value = "";
    renderSidebarGroups();
    return;
  }
}

// Sidebar switches tabs
function switchTab(tabId) {
  state.currentTab = tabId;
  
  // Update sidebar active highlights
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.remove("active");
    if (item.getAttribute("data-tab") === tabId) {
      item.classList.add("active");
    }
  });
  
  // Hide all views
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  
  // Show active view
  const target = document.getElementById(`${tabId}Tab`);
  if (target) target.classList.add("active");

  // Render specific tab scopes
  if (tabId === "overview") {
    updateOverviewKpis();
    renderOverviewTable();
    renderCharts();
  } else if (tabId === "tam") {
    renderTAMTab();
  } else if (tabId === "sam") {
    renderSAMTab();
  } else if (tabId === "csm") {
    renderCSMTab();
  } else if (tabId === "plan") {
    populateActionPlanSelector();
    generateActionPlan();
  } else if (tabId === "settings") {
    populateGroupManagerSystems();
    populateLogisticsEditor();
    
    // Load auth token input
    document.getElementById("settingsMockModeToggle").checked = state.mockMode;
    document.getElementById("settingsRefreshToken").value = safeGetItem("aiq_refresh_token") || "";
  }
}

function exportCSV() {
  let csvContent = "data:text/csv;charset=utf-8,";
  csvContent += "System Name,Serial Number,Cluster Name,Customer Name,Platform,Status,ONTAP Version,Efficiency Ratio,Contracts Expiry,Risks Count,Delivery Address,Primary Contact,CSAT Sentiment,Daily Growth (GB),Days to Limit\n";

  state.systems.forEach(s => {
    const risksCount = s.risks.length;
    const l = s.logistics || { deliveryAddress: "Not Set" };
    const c = s.contacts || { name: "Not Set" };
    const h = s.salesHealth || { sentimentScore: 7.0 };
    const p = s.projections || { growthRateGBPerDay: 100, daysToLimit: 120 };
    
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
      risksCount,
      l.deliveryAddress,
      c.name,
      h.sentimentScore,
      p.growthRateGBPerDay,
      p.daysToLimit
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
  const input = document.getElementById("importFileInput");
  if (input) input.click();
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
          saveSystems();
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

// 11. Initialization on Load
window.onload = async function() {
  // Create global tooltip element
  const tEl = document.createElement("div");
  tEl.id = "globalTooltip";
  tEl.className = "premium-tooltip-popup";
  document.body.appendChild(tEl);

  // Global event delegation for premium tooltips
  document.addEventListener("mouseover", (e) => {
    const target = e.target.closest("[data-tooltip]");
    if (!target) return;
    
    if (e.relatedTarget && target.contains(e.relatedTarget)) {
      return;
    }
    
    const text = target.getAttribute("data-tooltip");
    if (!text) return;
    
    const tooltip = document.getElementById("globalTooltip");
    if (!tooltip) return;
    
    tooltip.innerText = text;
    tooltip.style.visibility = "visible";
    tooltip.style.opacity = "1";
    
    const rect = target.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    
    let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
    let top = rect.top - tooltipRect.height - 8;
    
    // Safety viewport boundaries
    if (left < 10) left = 10;
    if (left + tooltipRect.width > window.innerWidth - 10) {
      left = window.innerWidth - tooltipRect.width - 10;
    }
    if (top < 10) {
      top = rect.bottom + 8;
    }
    
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  });
  
  document.addEventListener("mouseout", (e) => {
    const target = e.target.closest("[data-tooltip]");
    if (target) {
      if (e.relatedTarget && target.contains(e.relatedTarget)) {
        return;
      }
      const tooltip = document.getElementById("globalTooltip");
      if (tooltip) {
        tooltip.style.opacity = "0";
        tooltip.style.visibility = "hidden";
      }
    }
  });

  loadConfig();
  updateStatusIndicators();
  
  if (!state.mockMode) {
    await loadProductionData();
  }
  
  updateSearchSuggestions();
  switchTab("overview");

  // Initialize GraphQL Sandbox default query and variables
  const sandboxQuery = document.getElementById("sandboxGraphQLQuery");
  const sandboxVars = document.getElementById("sandboxGraphQLVariables");
  if (sandboxQuery && sandboxVars) {
    sandboxQuery.value = `query GetCustomerTelemetry($customerName: String!) {
  systems(customerName: $customerName) {
    serialNumber
    systemName
    clusterName
    platform
    status
    contracts {
      endDate
      daysRemaining
    }
  }
}`;
    sandboxVars.value = JSON.stringify({ customerName: "RetailGiant Corp" }, null, 2);
  }
  renderSidebarGroups();

  document.getElementById("searchInput").addEventListener("input", handleSearch);
  document.getElementById("searchInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      executeSearchGo();
    }
  });
  document.getElementById("searchInput").addEventListener("focus", (e) => {
    updateCustomSearchSuggestions(e.target.value);
  });
  
  // Close custom multi-select and autocomplete dropdowns when clicking outside
  window.addEventListener('click', (e) => {
    const dropdown = document.getElementById("tamMultiSelectDropdown");
    const container = document.getElementById("tamSystemSelectContainer");
    if (dropdown && container && !container.contains(e.target)) {
      dropdown.style.display = "none";
    }
    
    const searchDropdown = document.getElementById("searchSuggestionsContainer");
    const searchInput = document.getElementById("searchInput");
    if (searchDropdown && searchInput && !searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
      searchDropdown.style.display = "none";
    }
  });
  
  window.addEventListener('resize', () => {
    if (state.currentTab === "overview") {
      renderCharts();
    }
  });
};

// GraphQL Query Sandbox Execution handler
async function runSandboxGraphQLQuery() {
  const queryArea = document.getElementById("sandboxGraphQLQuery");
  const variablesArea = document.getElementById("sandboxGraphQLVariables");
  const outputDiv = document.getElementById("sandboxGraphQLOutput");
  const statusLabel = document.getElementById("sandboxQueryStatus");
  const latencyLabel = document.getElementById("sandboxQueryLatency");
  
  if (!queryArea || !outputDiv) return;
  
  const query = queryArea.value.trim();
  let variables = {};
  
  if (variablesArea && variablesArea.value.trim()) {
    try {
      variables = JSON.parse(variablesArea.value.trim());
    } catch (err) {
      if (statusLabel) {
        statusLabel.innerText = "Error";
        statusLabel.style.color = "var(--status-critical)";
      }
      outputDiv.innerText = `Invalid Variables JSON: ${err.message}`;
      return;
    }
  }
  
  if (statusLabel) {
    statusLabel.innerText = "Executing...";
    statusLabel.style.color = "var(--accent-cyan)";
  }
  if (latencyLabel) {
    latencyLabel.innerText = "-";
  }
  outputDiv.innerText = "// Executing query against NetApp Active IQ GraphQL gateway...";
  
  const startTime = performance.now();
  try {
    const data = await callActiveIQGraphQL(query, variables);
    const endTime = performance.now();
    const duration = (endTime - startTime).toFixed(0);
    
    if (statusLabel) {
      statusLabel.innerText = "Success";
      statusLabel.style.color = "var(--status-normal)";
    }
    if (latencyLabel) {
      latencyLabel.innerText = `${duration} ms`;
    }
    outputDiv.innerText = JSON.stringify(data, null, 2);
  } catch (error) {
    const endTime = performance.now();
    const duration = (endTime - startTime).toFixed(0);
    
    outputDiv.innerText = `Query Execution Failed:\n${error.message}`;
  }
}

// 12. Visual Port Mapping & L1 Topology Representation Helpers
function getSystemPortMappings(sys) {
  // Check if system has specific risks to dynamically fail/degrade ports
  const hasSasFailure = sys.risks && sys.risks.some(r => r.description.toLowerCase().includes("path failure") || r.description.toLowerCase().includes("sas"));
  const hasClusterFailure = sys.risks && sys.risks.some(r => r.description.toLowerCase().includes("cluster interconnect") || r.description.toLowerCase().includes("cluster network"));
  const hasMgmtFailure = sys.risks && sys.risks.some(r => r.description.toLowerCase().includes("management") || r.description.toLowerCase().includes("mgmt"));
  
  return [
    {
      name: "e0M",
      type: "mgmt",
      status: hasMgmtFailure ? "offline" : "online",
      partnerType: "mgmt_switch",
      partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-mgmt-sw-01`,
      partnerPort: "Fa0/24",
      cablingStatus: hasMgmtFailure ? "disconnected" : "optimal",
      details: { speed: "1 Gbps", mtu: 1500, ip: `10.250.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.5` }
    },
    {
      name: "e0a",
      type: "cluster",
      status: "online",
      partnerType: "cluster_switch",
      partnerName: `${sys.clusterName.toLowerCase()}-clus-sw-01`,
      partnerPort: "Eth1/1",
      cablingStatus: "optimal",
      details: { speed: "40 Gbps", mtu: 9000, ip: "169.254.1.10" }
    },
    {
      name: "e0b",
      type: "cluster",
      status: hasClusterFailure ? "offline" : "online",
      partnerType: "cluster_switch",
      partnerName: `${sys.clusterName.toLowerCase()}-clus-sw-02`,
      partnerPort: "Eth1/1",
      cablingStatus: hasClusterFailure ? "disconnected" : "optimal",
      details: { speed: "40 Gbps", mtu: 9000, ip: "169.254.2.10" }
    },
    {
      name: "e0c",
      type: "data",
      status: "online",
      partnerType: "core_switch",
      partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-core-sw-01`,
      partnerPort: "Eth1/41",
      cablingStatus: "optimal",
      details: { speed: "10 Gbps", mtu: 9000, ip: `10.100.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.11` }
    },
    {
      name: "e0d",
      type: "data",
      status: "online",
      partnerType: "core_switch",
      partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-core-sw-02`,
      partnerPort: "Eth1/41",
      cablingStatus: "optimal",
      details: { speed: "10 Gbps", mtu: 9000, ip: `10.100.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.12` }
    },
    {
      name: "0a",
      type: "fc",
      status: "online",
      partnerType: "san_switch",
      partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-san-sw-A`,
      partnerPort: "fc1/5",
      cablingStatus: "optimal",
      details: { speed: "32 Gbps", wwpn: `50:0a:09:80:30:1a:2b:${sys.serialNumber.slice(-2)}` }
    },
    {
      name: "0b",
      type: "fc",
      status: "online",
      partnerType: "san_switch",
      partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-san-sw-B`,
      partnerPort: "fc1/5",
      cablingStatus: "optimal",
      details: { speed: "32 Gbps", wwpn: `50:0a:09:80:30:1a:2c:${sys.serialNumber.slice(-2)}` }
    },
    {
      name: "0c",
      type: "sas",
      status: "online",
      partnerType: "disk_shelf",
      partnerName: `shelf-ds224c-stack-1`,
      partnerPort: "IOM-A-IN",
      cablingStatus: "optimal",
      details: { speed: "12 Gbps SAS", shelfStack: "Stack 1 Module A" }
    },
    {
      name: "0d",
      type: "sas",
      status: hasSasFailure ? "offline" : "online",
      partnerType: "disk_shelf",
      partnerName: `shelf-ds224c-stack-1`,
      partnerPort: "IOM-B-IN",
      cablingStatus: hasSasFailure ? "disconnected" : "optimal",
      details: { speed: "12 Gbps SAS", shelfStack: "Stack 1 Module B" }
    }
  ];
}

function renderNodeVisualLayout(selectedSystems, sys) {
  const container = document.getElementById("tamNodeVisualContainer");
  if (!container) return;

  const ports = getSystemPortMappings(sys);
  
  let portsHtml = "";
  let tableRowsHtml = "";
  
  // Render tabs row if multiple systems/nodes are selected
  let tabsHtml = "";
  if (selectedSystems && selectedSystems.length > 1) {
    tabsHtml = `<div class="node-tabs-row" style="display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; overflow-x: auto;">`;
    selectedSystems.forEach(s => {
      const isActive = s.serialNumber === sys.serialNumber;
      const btnStyle = isActive 
        ? "background: var(--accent-cyan); color: #0b0f19; border-color: var(--accent-cyan); font-weight: 600; box-shadow: 0 0 8px rgba(0, 229, 255, 0.35);"
        : "background: rgba(255,255,255,0.04); color: var(--text-secondary); border-color: var(--border-color);";
      
      tabsHtml += `
        <button class="action-btn" style="${btnStyle} padding: 5px 12px; font-size: 0.72rem; border-radius: var(--radius-sm); transition: all 0.2s;"
                onclick="selectVisualNode('${s.serialNumber}')">
          Node: ${s.systemName}
        </button>
      `;
    });
    tabsHtml += `</div>`;
  }

  ports.forEach(port => {
    let portColor = "#10b981"; // Green (mgmt)
    let typeLabel = "Management";
    if (port.type === "cluster") { portColor = "#3b82f6"; typeLabel = "Cluster Interconnect"; }
    if (port.type === "data") { portColor = "#f59e0b"; typeLabel = "Data Network"; }
    if (port.type === "fc") { portColor = "#eab308"; typeLabel = "FC / SAN"; }
    if (port.type === "sas") { portColor = "#a855f7"; typeLabel = "Storage SAS"; }

    const statusLedColor = port.status === "online" ? "#10b981" : "#ef4444";
    const statusLedShadow = port.status === "online" ? "0 0 8px #10b981" : "0 0 8px #ef4444";
    
    // Physical Port Slot
    portsHtml += `
      <div id="port-slot-${port.name}" class="physical-port-slot" 
           style="background: rgba(0,0,0,0.4); border: 2px solid ${portColor}; padding: 8px 4px; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.25s ease;"
           onmouseenter="hoverCablingPort('${port.name}')" 
           onmouseleave="unhoverCablingPort('${port.name}')">
        <div style="font-size: 0.65rem; color: #fff; margin-bottom: 2px; text-align: center; font-weight: 600;">${port.name}</div>
        <div style="width: 16px; height: 16px; background: rgba(0, 229, 255, 0.1); border: 1px solid rgba(0, 229, 255, 0.3); border-radius: 2px; display: flex; align-items: center; justify-content: center; margin: 0 auto; position: relative;">
          <div style="width: 4px; height: 4px; border-radius: 50%; background: ${statusLedColor}; box-shadow: ${statusLedShadow}; position: absolute; top: 1px; right: 1px;"></div>
          <div style="width: 8px; height: 6px; background: #fff; opacity: 0.1;"></div>
        </div>
      </div>
    `;

    // Table Row details
    let configDetail = "";
    if (port.type === "fc") {
      configDetail = `<code style="font-size: 0.72rem; color: var(--text-secondary);">${port.details.speed} | WWPN: ${port.details.wwpn}</code>`;
    } else if (port.type === "sas") {
      configDetail = `<span style="font-size: 0.75rem; color: var(--text-secondary);">${port.details.speed} (${port.details.shelfStack})</span>`;
    } else {
      configDetail = `<span style="font-size: 0.75rem; color: var(--text-secondary);">${port.details.speed} (MTU: ${port.details.mtu}) | IP: ${port.details.ip}</span>`;
    }

    const statusBadge = port.status === "online" 
      ? `<span style="display: inline-flex; align-items: center; gap: 4px; color: var(--status-normal); border: 1px solid rgba(0, 230, 118, 0.25); background: rgba(0, 230, 118, 0.05); padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 600;">✓ Optimal</span>`
      : `<span style="display: inline-flex; align-items: center; gap: 4px; color: var(--status-critical); border: 1px solid rgba(255, 51, 102, 0.25); background: rgba(255, 51, 102, 0.05); padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 700; box-shadow: 0 0 6px rgba(255,51,102,0.1);">✗ Link Down</span>`;

    tableRowsHtml += `
      <tr id="port-row-${port.name}" style="border-bottom: 1px solid var(--border-color); transition: all 0.2s ease; cursor: pointer;"
          onmouseenter="hoverCablingPort('${port.name}')" 
          onmouseleave="unhoverCablingPort('${port.name}')">
        <td style="padding: 10px; font-weight: 700; color: #fff;"><code>${port.name}</code></td>
        <td style="padding: 10px;">
          <span style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.75rem;">
            <span style="width: 8px; height: 8px; border-radius: 50%; background: ${portColor};"></span>
            ${typeLabel}
          </span>
        </td>
        <td style="padding: 10px;">${configDetail}</td>
        <td style="padding: 10px; font-weight: 500;">${port.partnerName}</td>
        <td style="padding: 10px;"><code>${port.partnerPort}</code></td>
        <td style="padding: 10px;">${statusBadge}</td>
      </tr>
    `;
  });

  container.innerHTML = `
    ${tabsHtml}
    <div style="display: grid; grid-template-columns: 280px 1fr; gap: 24px; align-items: start;">
      <!-- Controller Node rear backplate layout -->
      <div style="background: linear-gradient(135deg, #1f2937, #111827); border: 3px solid #374151; border-radius: var(--radius-md); padding: 18px 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); border-left: 8px solid var(--accent-cyan); position: sticky; top: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #4b5563; padding-bottom: 8px; margin-bottom: 14px;">
          <div style="font-size: 0.68rem; font-weight: 700; color: #fff; letter-spacing: 0.5px;">NETAPP CHASSIS REAR VIEW</div>
          <div style="font-size: 0.58rem; color: var(--accent-cyan); font-family: monospace;">${sys.platform.split(' ')[0]}</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; background: rgba(0,0,0,0.3); padding: 10px; border-radius: var(--radius-sm);">
          ${portsHtml}
        </div>
        <div style="margin-top: 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; border-top: 1px solid #4b5563; padding-top: 10px;">
          <div style="background: #2e353f; height: 18px; border-radius: var(--radius-sm); font-size: 0.55rem; text-align: center; color: var(--text-muted); font-weight: 700; line-height: 18px; border: 1px solid rgba(255,255,255,0.05);">PSU-1</div>
          <div style="background: #2e353f; height: 18px; border-radius: var(--radius-sm); font-size: 0.55rem; text-align: center; color: var(--text-muted); font-weight: 700; line-height: 18px; border: 1px solid rgba(255,255,255,0.05);">PSU-2</div>
        </div>
        <div style="margin-top: 12px; font-size: 0.62rem; color: var(--text-muted); line-height: 1.35; text-align: center;">
          Hover over ports or table rows to highlight individual layer-1 link cabling pathways.
        </div>
      </div>
      
      <!-- Detailed Cabling Audit Table -->
      <div class="data-table-container" style="border: 1px solid var(--border-color); border-radius: var(--radius-sm); overflow-x: auto; background: rgba(15,22,38,0.3);">
        <table class="data-table" style="width: 100%; border-collapse: collapse; font-size: 0.8rem;">
          <thead>
            <tr style="background: rgba(255, 255, 255, 0.015); border-bottom: 1px solid var(--border-color); text-align: left;">
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">Port</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">Type</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">Speed / Configuration</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">Link Partner Device</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">Target Port</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">Link Status</th>
            </tr>
          </thead>
          <tbody>
            ${tableRowsHtml}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function selectVisualNode(serial) {
  state.activeVisualizerNodeSerial = serial;
  const activeSerials = state.selectedTAMSerials || [];
  const selectedSystems = state.systems.filter(s => activeSerials.includes(s.serialNumber));
  const activeSys = selectedSystems.find(s => s.serialNumber === serial) || selectedSystems[0];
  if (activeSys) {
    renderNodeVisualLayout(selectedSystems, activeSys);
  }
}

function hoverCablingPort(portName) {
  const slot = document.getElementById(`port-slot-${portName}`);
  const row = document.getElementById(`port-row-${portName}`);
  
  if (slot) {
    slot.style.boxShadow = "0 0 12px rgba(0, 229, 255, 0.6)";
    slot.style.borderColor = "#ffffff";
    slot.style.transform = "scale(1.04)";
    slot.style.background = "rgba(0, 229, 255, 0.1)";
  }
  
  if (row) {
    row.style.background = "rgba(0, 229, 255, 0.04)";
    row.style.borderLeft = "3px solid var(--accent-cyan)";
  }
}

function unhoverCablingPort(portName) {
  const slot = document.getElementById(`port-slot-${portName}`);
  const row = document.getElementById(`port-row-${portName}`);
  
  if (slot) {
    slot.style.boxShadow = "";
    slot.style.borderColor = "";
    slot.style.transform = "";
    slot.style.background = "rgba(0,0,0,0.4)";
  }
  
  if (row) {
    row.style.background = "";
    row.style.borderLeft = "";
  }
}
