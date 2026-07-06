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
const API_BASE = window.location.origin.startsWith("http") ? "/api" : "https://api.activeiq.netapp.com/v1";

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
        createdDate: "2026-06-28",
        lastUpdated: "2026-07-05",
        ownerNotes: "Replacement drive sent to site. Estimated delivery tomorrow morning. Site contact notified."
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
        createdDate: "2026-07-04",
        lastUpdated: "2026-07-06",
        ownerNotes: "Advised customer to inspect fan module 2 immediately to prevent hardware speed throttling."
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
  mockMode: false,
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
  state.mockMode = mockModeVal === null ? false : mockModeVal === "true";
  
  const refresh = localStorage.getItem("aiq_refresh_token") || "";
  const access = localStorage.getItem("aiq_access_token") || "";
  const expiry = localStorage.getItem("aiq_token_expiry") || "";
  
  // Load systems db if exists in local storage
  const savedSystems = localStorage.getItem("aiq_systems_db");
  if (savedSystems) {
    state.systems = JSON.parse(savedSystems);
  } else {
    state.systems = [...MOCK_SYSTEMS];
  }

  // Pick first system as selected
  if (state.systems.length > 0) {
    state.selectedSystem = state.systems[0];
  }

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

function saveSystems() {
  localStorage.setItem("aiq_systems_db", JSON.stringify(state.systems));
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
  
  document.getElementById("kpiTotalSystems").style.color = "var(--text-primary)";
  document.getElementById("kpiCriticalRisks").style.color = criticalRisksCount > 0 ? "var(--status-critical)" : "var(--status-normal)";
  document.getElementById("kpiWarningRisks").style.color = warningRisksCount > 0 ? "var(--status-warning)" : "var(--status-normal)";
  document.getElementById("kpiContracts").style.color = expiringContracts > 0 ? "var(--status-warning)" : "var(--status-normal)";
}

function renderOverviewTable() {
  const tbody = document.getElementById("overviewTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const query = state.activeSearchQuery.toLowerCase().trim();
  const baseSystems = getFilteredSystems();
  
  let filteredSystems = baseSystems;
  if (query) {
    const terms = query.split(",").map(t => t.trim()).filter(t => t.length > 0);
    filteredSystems = baseSystems.filter(sys => {
      return terms.some(term => 
        sys.systemName.toLowerCase().includes(term) || 
        sys.serialNumber.toLowerCase().includes(term) ||
        sys.clusterName.toLowerCase().includes(term) ||
        sys.customerName.toLowerCase().includes(term) ||
        sys.platform.toLowerCase().includes(term)
      );
    });
  }

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
    switchTab("tam"); // Switch to Technical Audit details on system click
  }
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
    document.getElementById("tamSecurityBulletinsBody").innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No bulletins.</td></tr>`;
    return;
  }

  document.getElementById("tamActiveSystem").innerHTML = `
    <strong>System</strong>: ${sys.systemName} (S/N: <code class="copyable-code" onclick="copyToClipboard('${sys.serialNumber}', event)" title="Click to copy Serial Number">${sys.serialNumber} <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></code>) | <strong>ONTAP</strong>: ${sys.ontapVersion}
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
  document.getElementById("tamRisksTableBody").innerHTML = riskRows;

  // OS Upgrade
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

  // Render Security & Technical Bulletins
  const bulletins = sys.securityBulletins || [];
  let bulletinRows = "";
  if (bulletins.length === 0) {
    bulletinRows = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No active security advisories mapped.</td></tr>`;
  } else {
    bulletins.forEach(b => {
      let bBadge = `<span class="badge warning">${b.severity}</span>`;
      if (b.severity === "critical") bBadge = `<span class="badge critical">Critical</span>`;
      else if (b.severity === "high") bBadge = `<span class="badge critical">High</span>`;
      
      bulletinRows += `
        <tr>
          <td><strong style="color: var(--accent-cyan); font-family: monospace;">${b.id}</strong></td>
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
}

function renderSAMTab() {
  populateSystemSelectors();
  const sys = state.selectedSystem;
  if (!sys) {
    document.getElementById("samContractCard").innerHTML = "";
    document.getElementById("samLifecycleCard").innerHTML = "";
    document.getElementById("samHypervisorCard").innerHTML = "";
    document.getElementById("samLogisticsCard").innerHTML = "";
    document.getElementById("samSalesHealthCard").innerHTML = "";
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

  // Render Open Support Cases Table
  const cases = sys.supportCases || [];
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
            <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-primary); margin-bottom: 3px;">${c.title}</div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.3;">${c.ownerNotes}</div>
          </td>
          <td>${sevBadge}</td>
          <td><code style="color: var(--status-warning); font-size: 0.78rem;">${c.status}</code></td>
          <td style="font-size: 0.78rem; color: var(--text-muted);">
            Opened: ${c.createdDate}<br>Updated: ${c.lastUpdated}
          </td>
        </tr>
      `;
    });
  }
  document.getElementById("samSupportCasesBody").innerHTML = caseRows;
}

function renderCSMTab() {
  populateSystemSelectors();
  const sys = state.selectedSystem;
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
      allUpgrades.push({ systemName: sys.systemName, ...sys.upgrades });
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
            <strong>Root Cause Analysis:</strong><br>${r.remediationPlan ? r.remediationPlan.cause : "Undetermined"}
          </div>
          <div style="font-size: 0.85rem; color: var(--status-critical); margin-bottom: 12px; background: rgba(255, 51, 102, 0.03); padding: 10px; border-radius: var(--radius-sm); border: 1px solid rgba(255, 51, 102, 0.1);">
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
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">3. Security Bulletins & Vulnerability Mitigations</h2>
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
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">4. Active Support Cases & Milestones</h2>
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
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px; font-style: italic;">
            <strong>Latest Action Notes:</strong> ${c.ownerNotes}
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
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">5. Recommended OS Upgrade Roadmaps</h2>
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

    <!-- Site Logistics, Contacts & Health Details Section -->
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">6. Site Logistics, Contacts, & Customer Health</h2>
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
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">7. Operational Guidelines & Proceeding Steps</h2>
      
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
          <li><strong>Coordinate support renewal quotes</strong> for all systems identified in support reports.</li>
          <li><strong>Create internal IT ticket instances</strong> for the high-priority technical items in Section 2, attaching the generated remediation steps.</li>
          <li><strong>Verify delivery credentials</strong> and clearance permissions with site contacts listed in Section 6 before shipping parts.</li>
          <li><strong>Review the Security advisories</strong> in Section 3 and schedule OS micro-patches or workaround applications to block exposures.</li>
        </ol>
      </div>
    </div>

    <!-- Deliverables and Drafts Section -->
    <div style="margin-top: 32px;">
      <h2 style="font-size: 1.15rem; border-bottom: 2px solid var(--accent-cyan); padding-bottom: 8px; margin-bottom: 16px;">8. Executable Account Deliverables</h2>
      
      <div style="margin-bottom: 20px;">
        <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin-bottom: 6px;">A. Draft Customer Alert Email Notification</h4>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Copy and customize this email to notify the customer's operations team regarding active risks and support cases.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${draftEmailText}</textarea>
      </div>

      <div style="margin-bottom: 20px;">
        <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin-bottom: 6px;">B. Storage Upgrade & Hardware Refresh Proposal Draft</h4>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">A formal proposal draft to request funding or approvals for target OS updates and hardware contract renewals.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${draftProposalText}</textarea>
      </div>

      <div>
        <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin-bottom: 6px;">C. Internal Operations Coordination Ticket Template</h4>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Create an internal IT ticket to dispatch technicians or coordinate parts delivery based on logistics rules.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${internalTicketText}</textarea>
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
function loadSavedFilters() {
  const saved = localStorage.getItem("aiq_saved_filters");
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
  localStorage.setItem("aiq_saved_filters", JSON.stringify(savedFilters));
  
  renderSidebarGroups();
  alert(`Starred filter "${name}" saved!`);
}

function deleteSavedFilter(event, id) {
  event.stopPropagation();
  let savedFilters = loadSavedFilters();
  savedFilters = savedFilters.filter(f => f.id !== id);
  localStorage.setItem("aiq_saved_filters", JSON.stringify(savedFilters));
  renderSidebarGroups();
}

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

  // 3. Starred & Dynamic Filters
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
        <button class="action-btn secondary delete-filter-btn" style="opacity: 0.6; padding: 2px 6px; font-size: 0.65rem; border-color: transparent; margin-left: auto; background: transparent; color: var(--status-critical);" onclick="deleteSavedFilter(event, '${f.id}')">×</button>
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
  
  // Context-aware update: stay on the current tab but refresh system list scope
  switchTab(state.currentTab);
  
  renderSidebarGroups();
}

function resetFilter() {
  state.activeFilterType = "ALL";
  state.activeFilterValue = "";
  state.activeSearchQuery = "";
  const searchInput = document.getElementById("searchInput");
  if (searchInput) searchInput.value = "";
  switchTab(state.currentTab);
  renderSidebarGroups();
}

// 9. Custom Group & Metadata Editor Logic (in Settings panel)
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
  alert(`Metadata & specifications for "${state.systems[idx].systemName}" updated successfully!`);
  
  if (state.selectedSystem.serialNumber === serial) {
    state.selectedSystem = state.systems[idx];
  }
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
  
  alert("Group created successfully!");
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
  saveConfig(refresh, localStorage.getItem("aiq_access_token") || "", localStorage.getItem("aiq_token_expiry") || "");
  
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
  renderOverviewTable();
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
    document.getElementById("settingsRefreshToken").value = localStorage.getItem("aiq_refresh_token") || "";
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

// 11. Initialization on Load
window.onload = async function() {
  loadConfig();
  updateStatusIndicators();
  
  if (!state.mockMode) {
    await loadProductionData();
  }
  
  switchTab("overview");
  renderSidebarGroups();

  document.getElementById("searchInput").addEventListener("input", handleSearch);
  
  window.addEventListener('resize', () => {
    if (state.currentTab === "overview") {
      renderCharts();
    }
  });
};
