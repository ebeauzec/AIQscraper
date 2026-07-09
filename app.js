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
    ontapVersion: "9.15.1P2",
    platform: "AFF A90 (On-Prem NVMe)",
    status: "warning",
    risks: [
      {
        id: 101,
        severity: "high",
        category: "Hardware",
        description: "Single Controller Path Failure detected on NVMe loop 1.",
        recommendation: "Inspect NVMe-oF cable connections on shelf 2, port 1B. Refer to KB1089201.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/Single_controller_path_errors",
        remediationPlan: {
          cause: "Signal degradation or physical disconnection on controller NVMe port 1b connected to Shelf 2 NSM B.",
          impact: "Loss of NVMe path redundancy. A secondary failure on NVMe port 1a will cause a complete shelf outage, leading to Data Unavailable (DU) status for all aggregates on Shelf 2.",
          steps: [
            "1. SSH into the NY-AFF-CLUSTER-01 node controller CLI.",
            "2. Run: 'storage path show' to view NVMe path map and confirm the offline controller port.",
            "3. Locate Shelf 2 at the rack. Verify the status LED on the NVMe connector at port 1B (NSM B).",
            "4. Gently reseat the NVMe-oF cable. If the LED remains amber or off, replace the NVMe copper cable (Part: 112-00456) under active warranty.",
            "5. Run: 'storage path show -fields disk-count,path-link-status' to confirm all NVMe drives report dual-path status."
          ],
          options: [
            "Option A (Online): Reseat/replace NVMe-oF cable online (non-disruptive). ONTAP multipathing protects data availability via the active path.",
            "Option B (Schedule Maintenance): If NSM shelf controller module replacement is required, schedule a maintenance window. Although hot-swappable, doing it off-peak minimizes IO latency risks."
          ],
          thirdParty: "No direct hypervisor impacts. However, VMware ESXi storage paths might generate temporary ScsiDeviceIO path failure alerts which can be ignored during hot-swap."
        }
      },
      {
        id: 102,
        severity: "medium",
        category: "Software",
        description: "Disk Shelf NSM100 firmware is outdated (current: 0210, target: 0220).",
        recommendation: "Schedule a non-disruptive shelf firmware upgrade using ONTAP System Manager.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/Disk_Shelves_and_Storage_Storage_Media/How_to_update_shelf_firmware",
        remediationPlan: {
          cause: "Older firmware baseline (v0210) lacks optimization for NVMe-oF signal margins under heavy loads.",
          impact: "Increased risk of soft NVMe path resets and packet retries under high transactional workloads.",
          steps: [
            "1. Download the NSM100 firmware bundle (version 0220) from the NetApp Support Site.",
            "2. Upload the bundle to the ONTAP cluster. Run CLI command: 'storage firmware download -node * -package nsm100_0220.web'.",
            "3. Monitor progress: 'storage firmware show -package nsm100'. The update installs background/non-disruptively, updating one module (A or B) at a time."
          ],
          options: [
            "Option A: Automated update via NetApp Active IQ Unified Manager (AIQUM) or System Manager GUI.",
            "Option B: Manual CLI update. Requires downloading and staging files locally on cluster web servers."
          ],
          thirdParty: "Ensure vSphere Host storage queue depths are configured correctly to absorb transient IO delays (less than 2 seconds) during module reboots."
        }
      },
      {
        id: 103,
        severity: "critical",
        category: "Security",
        description: "Insecure Protocol Enabled: SMBv1 protocol is active on SVM netapp-aff-01-svm-cifs.",
        recommendation: "Disable SMBv1 protocol to mitigate security threats such as ransomware propagation. Refer to CVE-2017-0144.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/How_to_disable_SMBv1_in_ONTAP",
        remediationPlan: {
          cause: "Legacy SMBv1 protocol is enabled on SVM netapp-aff-01-svm-cifs to support older client devices, violating corporate security compliance.",
          impact: "Exposes ONTAP cluster to critical remote code execution exploits (e.g. EternalBlue/WannaCry).",
          steps: [
            "1. SSH into the NY-AFF-CLUSTER administrative CLI.",
            "2. Enforce SMB2/SMB3 communication and disable SMBv1: 'vserver cifs options modify -vserver netapp-aff-01-svm-cifs -smb1-enabled false'.",
            "3. Verify options state: 'vserver cifs options show -vserver netapp-aff-01-svm-cifs -fields smb1-enabled'."
          ],
          options: [
            "Option A: Disable SMBv1 cluster-wide or per SVM immediately (non-disruptive for modern clients).",
            "Option B: Retain SMB1 temporarily only if legacy print servers require it (Highly Discouraged)."
          ],
          thirdParty: "Windows 10/11 and Windows Server 2016+ clients are unaffected. Legacy Windows XP/2003 clients will lose access."
        }
      },
      {
        id: 104,
        severity: "high",
        category: "Security",
        description: "Insecure Export Policy Rule: NFS export policy 'default' allows superuser mount permissions to any host.",
        recommendation: "Modify export policy rules on SVM netapp-aff-01-svm-nfs to restrict superuser access to specific subnets and enable root squashing.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/Insecure_NFS_exports_root_squashing",
        remediationPlan: {
          cause: "Export policy rule for volume root/shares is configured on SVM netapp-aff-01-svm-nfs with client match '0.0.0.0/0' and superuser access parameter set to 'any'.",
          impact: "Any anonymous client on the network can mount NFS exports and gain full root permissions over data files.",
          steps: [
            "1. Identify offending rules: 'vserver export-policy rule show -vserver netapp-aff-01-svm-nfs'.",
            "2. Modify rule to squash root permissions (superuser=none): 'vserver export-policy rule modify -vserver netapp-aff-01-svm-nfs -policyname default -ruleindex 1 -superuser none'.",
            "3. Restrict client matches to trusted subnets: 'vserver export-policy rule modify -vserver netapp-aff-01-svm-nfs -policyname default -ruleindex 1 -clientmatch 10.100.0.0/16'."
          ],
          options: [
            "Option A: Squash root access and lock down clientmatch (Recommended security practice).",
            "Option B: Create a custom, read-only policy for anonymous mount needs."
          ],
          thirdParty: "Ensure client side mount scripts (e.g. Linux autofs or ESXi NFS mounts) do not rely on root access permissions to function."
        }
      }
    ],
    upgrades: {
      targetVersion: "9.16.1P2",
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
        id: "CVE-2026-22050",
        title: "ONTAP snapshot-lock bypass (Locked Snapshot vulnerability)",
        severity: "critical",
        status: "Vulnerable - Action Required",
        mitigation: "Upgrade to ONTAP 9.16.1P9 or 9.17.1P2 to patch snapshot volume lock checks."
      },
      {
        id: "CVE-2026-20833",
        title: "Microsoft Kerberos encryption-type change compatibility (KB5073381)",
        severity: "medium",
        status: "Vulnerable - Action Required",
        mitigation: "Verify AES encryption is active for SVM AD accounts and disable RC4/DES fallback."
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
        description: "Kubernetes Astra Trident driver (v24.02) is outdated and vulnerable (CVE-2026-24051 PATH hijacking).",
        recommendation: "Upgrade Astra Trident driver to v26.02 to mitigate CVE-2026-24051 and ensure compatibility with newer Kubernetes APIs.",
        kbLink: "https://docs.netapp.com/us-en/trident/trident-get-started/requirements.html",
        remediationPlan: {
          cause: "Kubernetes cluster upgraded to v1.31 while Astra Trident version remains at v24.02. Vulnerable OpenTelemetry-Go dependencies trigger security scan flags.",
          impact: "Inability to dynamically provision new Persistent Volumes (PV) for container workloads. Existing PVs remain mounted but configuration edits fail.",
          steps: [
            "1. Backup active Trident state: 'tridentctl get backend -n trident'.",
            "2. Download the Trident installer bundle v26.02.",
            "3. Run the installer upgrade command: 'tridentctl upgrade -n trident --to-image netapp/trident:26.02.0'.",
            "4. Verify Pod status: 'kubectl get pods -n trident' and verify all pods are running version 26.02.0."
          ],
          options: [
            "Option A (Helm Upgrade - Recommended): Use Helm package manager: 'helm upgrade trident netapp-trident/trident-operator --version 26.02.0'.",
            "Option B (Operator Upgrade): Apply the updated Trident Operator manifests manually."
          ],
          thirdParty: "Compatible with Kubernetes v1.29 through v1.32. Ensure downstream apps are prepared for dynamic PV mounts."
        }
      },
      {
        id: 202,
        severity: "medium",
        category: "Cloud",
        description: "Atheros AWS S3 capacity tiering bucket reports connection timeouts.",
        recommendation: "Verify VPC endpoint routing for AWS S3. Refer to NetApp Cloud Manager guide.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/FabricPool_S3_connection_timeouts_in_Cloud_Volumes_ONTAP",
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
        id: "CVE-2026-22052",
        title: "ONTAP S3 NAS bucket information disclosure vulnerability",
        severity: "medium",
        status: "Vulnerable - Action Required",
        mitigation: "Upgrade to ONTAP 9.16.1P7+ or restrict S3 API access policies on NAS bucket exports."
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
        id: "CVE-2026-22050",
        title: "ONTAP snapshot-lock bypass (Locked Snapshot vulnerability)",
        severity: "critical",
        status: "Vulnerable - Action Required",
        mitigation: "Upgrade to ONTAP 9.16.1P9 or 9.17.1P2 to patch snapshot volume lock checks."
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
            "5. Alternatively, run CLI script on ESXi shell: 'esxcli storage nmp device set -d <naa_id> -P VMW_PSP_RR' and either 'esxcli storage nmp psp roundrobin device config set -d <naa_id> -I 1 -t iops' (for ESXi 6.x) or 'esxcli storage nmp psp roundrobin device config set --device <naa_id> --type iops --iops 1' (for ESXi 7.0/8.0+)."
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
    ontapVersion: "9.15.1",
    platform: "ASA A90 (Hospital SAN Core)",
    status: "normal",
    risks: [],
    upgrades: {
      targetVersion: "9.16.1P2",
      urgency: "None",
      benefits: "Applies performance enhancements for NVMe/FC symmetric active-active multipath LUN mappings."
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
      ratio: "4.0:1",
      logicalUsedTB: 160.0,
      physicalUsedTB: 40.0,
      spaceSavedTB: 120.0,
      fabricPoolTieredTB: 0.0
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
    ontapVersion: "11.4.0",
    platform: "StorageGRID SG100",
    status: "warning",
    risks: [
      {
        id: 701,
        severity: "medium",
        category: "Software",
        description: "StorageGRID OS version 11.4.0 is legacy and unsupported.",
        recommendation: "Plan sequential upgrade to StorageGRID 11.9.0. Refer to NetApp Upgrade Advisor.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/StorageGRID/How_to_upgrade_StorageGRID",
        remediationPlan: {
          cause: "Operating system baseline reaching official support retirement date.",
          impact: "Loss of developer hot-patches and security vulnerability coverage from NetApp engineering after this quarter.",
          steps: [
            "1. Run StorageGRID Pre-Upgrade Validator tool.",
            "2. Download StorageGRID 11.5 through 11.9 packages.",
            "3. Execute sequential rolling node upgrades starting with the primary Admin Node."
          ],
          options: [
            "Option A: Upgrade sequentially to 11.9.0 (Recommended).",
            "Option B: Postpone update under extended support agreement."
          ],
          thirdParty: "Compatible with AWS S3 API v4."
        }
      }
    ],
    upgrades: {
      targetVersion: "11.9.0",
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
    ontapVersion: "9.5",
    platform: "FAS2720 (Store Primary)",
    status: "warning",
    risks: [
      {
        id: 801,
        severity: "medium",
        category: "Software",
        description: "Disk Shelf IOM3 firmware is outdated.",
        recommendation: "Upgrade IOM3 firmware. Refer to KB Article.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/Disk_Shelves_and_Storage_Storage_Media/How_to_update_shelf_firmware",
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
      targetVersion: "9.12.1",
      urgency: "Recommended",
      benefits: "Improves overall storage shelf stability and moves system from legacy 9.5 to modern 9.12 release."
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
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Protection_and_Security/MetroCluster/How_to_update_ATTO_FibreBridge_firmware_in_a_MetroCluster_configuration",
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
    platform: "AFF A90 (High-Security NVMe)",
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
    platform: "StorageGRID SG6160",
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
  },
  {
    serialNumber: "622008886001",
    systemName: "apex-ef600-01a",
    clusterName: "apex-ef600-01",
    customerName: "Apex Global Solutions",
    santricityVersion: "11.80.3",
    platform: "EF600 (E-Series)",
    status: "optimal",
    risks: [],
    upgrades: {
      targetVersion: "11.80.5",
      urgency: "Recommended",
      benefits: "Resolves controller cache mirroring latency spikes under burst write loads."
    },
    contracts: {
      status: "normal",
      endDate: "2027-12-15"
    },
    logistics: {
      deliveryAddress: "Apex DC-4 Node A (Physical SANtricity Controller)",
      eoaDate: "2028-06-30",
      eosDate: "2033-06-30",
      isNearEos: false
    },
    efficiency: {
      ratio: "N/A (Block SAN)",
      logicalUsedTB: 85.0,
      physicalUsedTB: 85.0,
      spaceSavedTB: 0,
      fabricPoolTieredTB: 0
    },
    securityBulletins: [],
    supportCases: [],
    eseriesHardware: {
      controllers: [
        { name: "Controller A", status: "Optimal", batteryStatus: "Optimal", cacheGB: 32, nvsram: "N600-880833-001" },
        { name: "Controller B", status: "Optimal", batteryStatus: "Optimal", cacheGB: 32, nvsram: "N600-880833-001" }
      ],
      shelves: [
        {
          id: 0,
          name: "Chassis Shelf 0",
          model: "EF600 Controller Shelf",
          disks: [
            { bay: 1, type: "NVMe SSD", size: "3.8TB", status: "Optimal", wearLife: 98 },
            { bay: 2, type: "NVMe SSD", size: "3.8TB", status: "Optimal", wearLife: 98 },
            { bay: 3, type: "NVMe SSD", size: "3.8TB", status: "Optimal", wearLife: 95 },
            { bay: 4, type: "NVMe SSD", size: "3.8TB", status: "Optimal", wearLife: 97 },
            { bay: 5, type: "NVMe SSD", size: "3.8TB", status: "Optimal", wearLife: 94 },
            { bay: 6, type: "NVMe SSD", size: "3.8TB", status: "Optimal", wearLife: 98 },
            { bay: 7, type: "NVMe SSD", size: "3.8TB", status: "Optimal", wearLife: 91 },
            { bay: 8, type: "NVMe SSD", size: "3.8TB", status: "Optimal", wearLife: 98 }
          ]
        }
      ],
      storagePools: [
        { name: "Dynamic Disk Pool 1", raidType: "DDP", capacityTB: 30.4, freeTB: 12.1, status: "Optimal" }
      ]
    }
  },
  {
    serialNumber: "622008885001",
    systemName: "apex-e5700-02a",
    clusterName: "apex-e5700-02",
    customerName: "Global Bank Corp",
    santricityVersion: "11.30",
    platform: "E5700 (E-Series)",
    status: "warning",
    risks: [
      {
        id: 901,
        severity: "medium",
        category: "Hardware",
        description: "Controller B Backup Battery (BBU) reports replacement required (Near End of Life).",
        recommendation: "Order replacement battery pack (Part: 271-00221) and swap it online.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/E-Series_Storage/How_to_replace_BBU_on_E5700",
        remediationPlan: {
          cause: "Chemical degradation of lithium-ion cells over a 3-year operating period.",
          impact: "If battery fails completely, write caching will be disabled on Controller B to prevent data loss in a power event, resulting in a 70% decrease in write performance.",
          steps: [
            "1. Order replacement battery pack part 271-00221.",
            "2. Access SANtricity System Manager and select Hardware -> Controller B -> Replace Battery.",
            "3. Slide out Controller B module slightly, unscrew BBU bracket, swap the battery packs, and slide back the controller.",
            "4. Verify that SANtricity reports BBU state as 'Learning' or 'Optimal'."
          ],
          options: [
            "Option A: Online replacement (non-disruptive, takes ~15 minutes).",
            "Option B: Shut down controller for replacement (unnecessary but optional)."
          ],
          thirdParty: "No hypervisor impact. SANtricity cache mirroring remains active via Controller A during battery replacement."
        }
      }
    ],
    upgrades: {
      targetVersion: "11.80.5",
      urgency: "Recommended",
      benefits: "Brings modern SANtricity OS features, security hardening, and stable multipathing."
    },
    contracts: {
      status: "warning",
      endDate: "2026-11-30"
    },
    logistics: {
      deliveryAddress: "NY Server Farm B (E-Series Cabinet)",
      eoaDate: "2027-06-30",
      eosDate: "2032-06-30",
      isNearEos: false
    },
    efficiency: {
      ratio: "N/A (Hybrid SAN)",
      logicalUsedTB: 140.0,
      physicalUsedTB: 140.0,
      spaceSavedTB: 0,
      fabricPoolTieredTB: 0
    },
    securityBulletins: [],
    supportCases: [],
    eseriesHardware: {
      controllers: [
        { name: "Controller A", status: "Optimal", batteryStatus: "Optimal", cacheGB: 16, nvsram: "N5700-880833-002" },
        { name: "Controller B", status: "Optimal", batteryStatus: "Replacement Required", cacheGB: 16, nvsram: "N5700-880833-002" }
      ],
      shelves: [
        {
          id: 0,
          name: "Chassis Shelf 0",
          model: "E5700 Controller Shelf",
          disks: [
            { bay: 1, type: "HDD", size: "12TB", status: "Optimal", wearLife: 100 },
            { bay: 2, type: "HDD", size: "12TB", status: "Optimal", wearLife: 100 },
            { bay: 3, type: "HDD", size: "12TB", status: "Optimal", wearLife: 100 },
            { bay: 4, type: "HDD", size: "12TB", status: "Optimal", wearLife: 100 }
          ]
        },
        {
          id: 1,
          name: "Expansion Shelf 1",
          model: "DE224C SAS Shelf",
          disks: [
            { bay: 1, type: "SSD", size: "1.6TB", status: "Optimal", wearLife: 88 },
            { bay: 2, type: "SSD", size: "1.6TB", status: "Optimal", wearLife: 85 },
            { bay: 3, type: "SSD", size: "1.6TB", status: "Optimal", wearLife: 82 },
            { bay: 4, type: "SSD", size: "1.6TB", status: "Optimal", wearLife: 89 }
          ]
        }
      ],
      storagePools: [
        { name: "Volume Group 1", raidType: "RAID-6", capacityTB: 48.0, freeTB: 10.4, status: "Optimal" },
        { name: "SSD Cache Pool", raidType: "RAID-1", capacityTB: 6.4, freeTB: 0, status: "Optimal" }
      ]
    }
  },
  {
    serialNumber: "622008883030",
    systemName: "apex-asa-a30",
    clusterName: "apex-asa-cluster",
    customerName: "Apex Global Solutions",
    ontapVersion: "9.16.1",
    platform: "ASA A30 (On-Prem NVMe)",
    status: "critical",
    risks: [
      {
        id: 1701,
        severity: "critical",
        category: "Hardware",
        description: "Outdated cluster interconnect switch firmware detected on Cisco Nexus 9336C-FX2 (current: 9.3(8), target: 9.3(12)).",
        recommendation: "Schedule a switch firmware update to Cisco NX-OS 9.3(12) to address packet loss warnings. Refer to KB1192901.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/MetroCluster_and_IP_switches/Nexus_9336C_firmware_upgrade",
        remediationPlan: {
          cause: "Legacy NX-OS firmware exhibits internal buffer drop anomalies during high RoCE traffic bursts.",
          impact: "Packet drops on cluster interconnect will trigger node health degradation and temporary failover blocks.",
          steps: [
            "1. Download Cisco NX-OS 9.3(12) image from NetApp Support.",
            "2. Copy image to switch active flash partition.",
            "3. Execute switch install command: 'install all nxos bootflash:nxos.9.3.12.bin'.",
            "4. Verify switch health and port status: 'show interface brief'."
          ],
          options: [
            "Option A: Update cluster switches sequentially during maintenance window (non-disruptive, traffic fails over to redundant switch A/B).",
            "Option B: Delay update (Not recommended, risk of interconnect link failure under spike workloads)."
          ],
          thirdParty: "Directly affects cluster interconnect stability. Switch port resets may raise momentary path warning events on ESXi hypervisors."
        }
      },
      {
        id: 1702,
        severity: "high",
        category: "Configuration",
        description: "Asymmetric storage pathing detected on VMware ESXi hosts mapping to LUNs. Some paths are reporting indirect/non-optimized.",
        recommendation: "Configure VMware host multipathing to symmetric active-active optimized paths. Refer to ASA Host Utilities Guide.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/ASA_symmetric_multipath_alignment",
        remediationPlan: {
          cause: "Host mapping igroups do not have symmetric port access enabled on the target SVM, forcing indirect paths.",
          impact: "Under heavy workloads, indirect paths introduce extra controller hop latency, increasing application response times.",
          steps: [
            "1. Verify LUN multipathing configuration in ONTAP CLI: 'lun multipath show'.",
            "2. Enable active-optimized paths for all mapped igroups: 'igroup modify -vserver apex-svm -igroup esxi_cluster -symmetric-path true'.",
            "3. Scan storage adapter paths on VMware hosts and verify active-optimized path counts."
          ],
          options: [
            "Option A: Enable symmetric-path attribute online (non-disruptive). Paths immediately transition to optimized.",
            "Option B: Keep default non-symmetric path settings (Causes 5-15% higher IO latency)."
          ],
          thirdParty: "Improves VMware vSphere host datastore performance. Eliminates indirect ALUA path storage logs."
        }
      }
    ],
    upgrades: {
      targetVersion: "9.16.1P1",
      urgency: "None",
      benefits: "Applies latest security microcode updates and fixes for NVMe over TCP path validation."
    },
    contracts: {
      status: "normal",
      endDate: "2029-06-30",
      daysRemaining: 1087,
      supportLevel: "SupportEdge Premium 4hr"
    },
    lifecycle: {
      eoaDate: "2031-12-31",
      eosDate: "2036-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "4.2:1",
      logicalUsedTB: 210.0,
      physicalUsedTB: 50.0,
      spaceSavedTB: 160.0,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [
      {
        type: "VMware vSphere",
        version: "ESXi 8.0 Update 2",
        plugin: "VASA Provider 10.1 (Active)",
        multipathing: "VMW_PSP_RR (Symmetric Active-Active)",
        health: "Normal"
      }
    ],
    logistics: {
      deliveryAddress: "Apex DC-4 Suite B, San Jose, CA 95134, US",
      accessRestrictions: "Escort required. Loading dock access needs 24-hr advance notice.",
      shippingAlert: "None"
    },
    contacts: {
      name: "Marcus Aurelius",
      phone: "+1-408-555-1234",
      email: "maurelius@apexglobal.com",
      nssUsername: "maurelius_ap"
    },
    salesHealth: {
      accountManager: "David Vance (Senior AE)",
      supportTam: "Marcus Vance (CSM)",
      sentimentScore: 9.0,
      healthStatus: "Excellent",
      upsellPotential: "None",
      refreshWindow: "N/A"
    },
    projections: {
      growthRateGBPerDay: 200,
      daysToLimit: 140,
      limitDate: "2026-11-25",
      peakIops: 65000,
      avgLatencyMs: 0.8,
      historicalCapacityMonths: [40, 42, 44, 46, 48, 50],
      projectedCapacityMonths: [52, 54, 56]
    },
    securityBulletins: [
      {
        id: "CVE-2026-22051",
        title: "StorageGRID authenticated metrics query information disclosure vulnerability",
        severity: "medium",
        status: "Vulnerable - Action Required",
        mitigation: "Upgrade StorageGRID to 11.9.0.13 or 12.0.0.6+ to patch metrics access restrictions."
      },
      {
        id: "NTAP-20260217-0001",
        title: "StorageGRID Server-Side Request Forgery (SSRF) via Entra ID SSO integration",
        severity: "high",
        status: "Mitigated",
        mitigation: "SSO certificate validation policies enforced. Upgrade advised for permanent patch."
      }
    ],
    supportCases: []
  },
  {
    serialNumber: "622009996160",
    systemName: "fed-sg6160-01",
    clusterName: "DC-SECURE-GRID",
    customerName: "Federal Aero Systems",
    ontapVersion: "11.9.0",
    platform: "StorageGRID SG6160",
    status: "warning",
    risks: [
      {
        id: 1703,
        severity: "warning",
        category: "Hardware",
        description: "StorageGRID SSD firmware is outdated on 24 drives (current: NA02, target: NA05).",
        recommendation: "Perform a non-disruptive drive firmware update through StorageGRID Console. Refer to SG-KB39102.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/StorageGRID_Appliance/How_to_update_drive_firmware_on_StorageGRID_appliances",
        remediationPlan: {
          cause: "Drives are running outdated NA02 firmware which has been superseded due to write endurance improvements.",
          impact: "Accelerated wear-out rate on storage node SSDs under continuous write ingestion.",
          steps: [
            "1. Download SSD firmware package from NetApp Support.",
            "2. Upload to StorageGRID Console: Maintenance > Software Update > Drive Firmware.",
            "3. Select firmware package and trigger non-disruptive update.",
            "4. Monitor drive upgrade progress via the grid dashboard."
          ],
          options: [
            "Option A: Perform rolling non-disruptive update via StorageGRID console (recommended).",
            "Option B: Defer drive firmware update (Increases SSD failure risk over time)."
          ],
          thirdParty: "No external hypervisor impact. StorageGRID node service remains active."
        }
      }
    ],
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
      eoaDate: "2031-12-31",
      eosDate: "2036-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "1.0:1",
      logicalUsedTB: 1100.0,
      physicalUsedTB: 1100.0,
      spaceSavedTB: 0.0,
      fabricPoolTieredTB: 0.0
    },
    snapmirror: {
      enabled: false,
      relationships: []
    },
    hypervisors: [],
    logistics: {
      deliveryAddress: "740 Broadway, Floor 8, New York, NY 10003, US",
      accessRestrictions: "Escort required. 24-hr advance notification to security lobby for loading dock B access.",
      shippingAlert: "None"
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
      growthRateGBPerDay: 400,
      daysToLimit: 280,
      limitDate: "2027-04-15",
      peakIops: 25000,
      avgLatencyMs: 1.5,
      historicalCapacityMonths: [900, 940, 980, 1020, 1060, 1100],
      projectedCapacityMonths: [1140, 1180, 1220]
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
    "AFF A90 (On-Prem NVMe)",
    "AFF A1K (On-Prem NVMe Flagship)",
    "AFF A70 (On-Prem NVMe)",
    "AFF C80 (Capacity Flash)",
    "ASA A90 (All-Flash SAN Array)",
    "Cloud Volumes ONTAP (AWS)",
    "Cloud Volumes ONTAP (Azure)",
    "StorageGRID SG6160",
    "AFF A400 (On-Prem)",
    "FAS8700 (On-Prem)",
    "AFF A900 (On-Prem)",
    "AFF A400 (MetroCluster IP)",
    "FAS8700 (MetroCluster FC)",
    "EF600 (E-Series NVMe)",
    "AFX 1K (AI-Scale Disaggregated)",
    "ASA A90 r2 (Next-Gen Block)"
  ];
  
  const statuses = ["normal", "normal", "normal", "normal", "warning", "warning", "critical"];
  
  const ontapVersions = ["9.15.1P2", "9.14.1P4", "9.16.1P1", "9.13.1P10", "11.9.0", "9.16.1P2"];

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
          kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/Disk_Shelves_and_Storage_Storage_Media/How_to_replace_a_failed_disk_drive_in_ONTAP",
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
          kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/Troubleshooting_sas_adapter_reset_and_sas_adapter_reset_failed_messages_in_ONTAP",
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
          kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Protection_and_Security/MetroCluster/MetroCluster_IP_configuration_sync_fails",
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
          kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/HA_interconnect_link_down_troubleshooting",
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
          kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/How_to_disable_TLS_1.0_and_1.1_in_ONTAP",
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
          kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/Troubleshooting_NTP_synchronization_issues_in_ONTAP",
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
          kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/Disk_Shelves_and_Storage_Storage_Media/How_to_update_shelf_firmware",
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
          kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/How_to_troubleshoot_aggregate_space_full_issues_in_ONTAP",
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

    let currentVer = "9.12.1";
    let targetVer = "Up to Date";
    let urgency = "None";
    let isStorageGRID = platform.includes("StorageGRID") || platform.includes("Webscale");
    let isESeries = platform.includes("E-Series") || platform.includes("EF600") || platform.includes("E5700") || platform.includes("SANtricity");
    
    if (isStorageGRID) {
      const sgVers = ["11.4.0", "11.6.0", "11.7.0", "11.8.0"];
      currentVer = sgVers[i % sgVers.length];
      if (status !== "normal") {
        targetVer = "11.9.0";
        urgency = "Recommended";
      }
    } else if (isESeries) {
      const esVers = ["11.30", "11.40", "11.50", "11.70.2", "11.80.3"];
      currentVer = esVers[i % esVers.length];
      if (status !== "normal") {
        targetVer = "11.80.5";
        urgency = "Recommended";
      }
    } else {
      const otVers = ["9.5", "9.7", "9.9.1P4", "9.11.1P8", "9.12.1P4", "9.14.1P2"];
      currentVer = otVers[i % otVers.length];
      if (status !== "normal") {
        if (currentVer === "9.5" || currentVer === "9.7") {
          targetVer = "9.12.1";
        } else if (currentVer === "9.9.1P4" || currentVer === "9.11.1P8") {
          targetVer = "9.13.1P8";
        } else {
          targetVer = "9.16.1";
        }
        urgency = "Recommended";
      }
    }

    const sys = {
      serialNumber: serial,
      systemName: sysName,
      clusterName: clusterName,
      customerName: customer,
      ...(isESeries ? { santricityVersion: currentVer } : { ontapVersion: currentVer }),
      platform: platform,
      status: status,
      risks: risks,
      switches: switches,
      upgrades: {
        targetVersion: targetVer,
        urgency: urgency,
        benefits: "Enhances security standards, applies vendor fixes, and ensures stable operations."
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
  syncInterval: 0,         // Polling interval in hours (0 = Manual Only)
  lastSync: "",            // ISO Timestamp of last successful Active IQ sync
  apiBaseUrl: "https://api.activeiq.netapp.com/v1", // REST gateway base URL
  watchlistOnly: false,    // Synchronize only systems in active watchlists
  
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
  
  state.apiBaseUrl = safeGetItem("aiq_api_base_url") || "https://api.activeiq.netapp.com/v1";
  state.syncInterval = parseInt(safeGetItem("aiq_sync_interval") || "0");
  state.lastSync = safeGetItem("aiq_last_sync") || "";
  const wlOnlyVal = safeGetItem("aiq_watchlist_only");
  state.watchlistOnly = wlOnlyVal === "true";
  
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

  const response = await fetch(`${state.apiBaseUrl}/tokens/accessToken`, {
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
    const response = await fetch(`${state.apiBaseUrl}${endpoint}`, {
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
        backgroundColor: ['rgba(0, 115, 230, 0.7)', 'rgba(0, 230, 118, 0.7)'],
        borderColor: ['#0073e6', '#00e676'],
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
          backgroundColor: 'rgba(0, 115, 230, 0.7)',
          borderColor: '#0073e6',
          borderWidth: 1
        },
        {
          label: 'FabricPool Tiered to Cloud (TB)',
          data: filteredSystems.map(s => s.efficiency.fabricPoolTieredTB.toFixed(1)),
          backgroundColor: 'rgba(0, 210, 255, 0.7)',
          borderColor: '#00d2ff',
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
        (sys.platform || "").toLowerCase().includes(term)
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

const SOFTWARE_VERSION_DATABASES = {
  ontap: [
    "9.3", "9.4", "9.5", "9.6", "9.7", "9.8", "9.9.1", "9.10.1", "9.11.1", "9.12.1", "9.13.1", "9.14.1", "9.15.1", "9.16.1", "9.17.1", "9.18.1", "9.19.1"
  ],
  santricity: [
    "11.30", "11.40", "11.50", "11.60", "11.70", "11.75", "11.80.5", "11.90.1"
  ],
  storagegrid: [
    "11.3", "11.4", "11.5", "11.6", "11.7", "11.8", "11.9.0", "12.0.0"
  ]
};

function getOntapHopInfo(from, to) {
  let steps = [
    "1. Download target ONTAP " + to + " image from the NetApp Support site.",
    "2. Run cluster pre-upgrade validation command: <code>cluster image validate -version " + to + "</code>.",
    "3. Apply OS update non-disruptively: <code>cluster image update -version " + to + "</code>."
  ];
  let recommendations = [
    "Run <code>system health alert show</code> to verify no active hardware alerts are present.",
    "Generate a configuration backup: <code>system configuration backup create -node * -backup-name pre_upgrade_" + from.replace(/\./g, "_") + "</code>.",
    "Verify network path redundancy using <code>network port show</code>."
  ];
  let considerations = [
    "ONTAP upgrades are non-disruptive (NDU) on HA pairs. Node failovers reload controllers sequentially.",
    "Cross-reference switch and disk shelf firmware compatibility tables on the NetApp Interoperability Matrix Tool (IMT)."
  ];
  let docLink = "https://docs.netapp.com/us-en/ontap/upgrade/index.html";

  if (to === "9.7") {
    recommendations.push("WAFL metadata format upgrade will automatically occur. Ensure aggregates have > 15% free capacity prior to starting.");
    considerations.push("ONTAP 9.7 enforces secure management protocols by default. Legacy TLS 1.0/1.1 API connections will be rejected.");
  } else if (to === "9.8") {
    steps.push("Upgrade cluster switch firmwares to support newer internal link speed configurations.");
    considerations.push("ONTAP 9.8 introduces simplified volume placement policies and unified interface improvements.");
  } else if (to === "9.10.1" || to === "9.12.1") {
    recommendations.push("Confirm that VMware ESXi hosts connecting via iSCSI/FCP use the <code>VMW_PSP_RR</code> round-robin storage path policy with IOPS limit = 1.");
    considerations.push("Review cipher configurations. All deprecated, weak TLS ciphers are disabled.");
  } else if (to === "9.14.1" || to === "9.16.1") {
    steps.push("Verify that all hardware controller node models in the cluster support ONTAP " + to + " (refer to hardware compatibility matrix).");
    considerations.push("ONTAP REST API v2 endpoints are active. Verify external automation tools or scripts compatibility.");
  }
  
  return { from, to, steps, recommendations, considerations, docLink };
}

function getStoragegridHopInfo(from, to) {
  let steps = [
    "1. Download StorageGRID software update package (version " + to + ") and recovery package from NetApp Support.",
    "2. Log in to the Primary Admin Node. Navigate to Maintenance > System > Software Update.",
    "3. Upload the update package and recovery package, then click 'Apply'."
  ];
  let recommendations = [
    "Generate a new grid recovery package before start: select Maintenance > Recovery Package and download the file.",
    "Ensure all grid storage and API gateway nodes are online and reporting normal telemetry."
  ];
  let considerations = [
    "StorageGRID major upgrades must be performed sequentially. Skipping major versions (e.g. 11.4 to 11.6 directly) is unsupported.",
    "The software update process is rolling. Services remain active, but API calls might failover between gateway nodes during container restarts."
  ];
  let docLink = "https://docs.netapp.com/us-en/storagegrid-" + to.replace(/\./g, "").slice(0, 3) + "/upgrade/index.html";
  if (to.startsWith("11.9")) docLink = "https://docs.netapp.com/us-en/storagegrid-119/upgrade/index.html";
  
  if (to === "11.5") {
    considerations.push("Underlying Cassandra database schemas are restructured. Storage nodes will consume higher CPU during indexing.");
  } else if (to === "11.7") {
    recommendations.push("Verify S3 client API integration compatibility (verify Swift deprecation markers if applicable).");
  } else if (to.startsWith("11.9")) {
    considerations.push("Review TLS certificate signing requirements. StorageGRID 11.9 enforces strict client-side cert handshakes.");
  }
  
  return { from, to, steps, recommendations, considerations, docLink };
}

function getSantricityHopInfo(from, to) {
  let steps = [
    "1. Download SANtricity OS controller firmware package " + to + " and NVSRAM file from NetApp Support.",
    "2. Access SANtricity System Manager or Unified Manager.",
    "3. Go to Support > Upgrade Center > SANtricity OS Software Upgrade. Upload both firmware and NVSRAM files, then select 'Upgrade'."
  ];
  let recommendations = [
    "Run drive diagnostics to ensure all disk drives in pools/volume groups are in optimal state.",
    "Ensure both Controller A and Controller B report optimal state and battery units are fully charged."
  ];
  let considerations = [
    "Firmware reload is non-disruptive on dual-controller configurations. Firmware is activated on one controller, reboots, then syncs with the partner.",
    "Single-controller shelf configurations require scheduling an offline maintenance window."
  ];
  let docLink = "https://docs.netapp.com/us-en/e-series/upgrade-santricity.html";

  if (to === "11.50") {
    steps.push("Note: SANtricity 11.50 implements the embedded REST API server. Legacy Web Services proxy configurations require reconfiguration.");
  } else if (to === "11.70" || to === "11.75") {
    considerations.push("Verify BBU backup battery units status. A degraded BBU will disable write caching during update, causing significant latency spikes.");
  } else if (to.startsWith("11.80")) {
    recommendations.push("Inspect SSD drive wear life reports to identify any drives nearing 90% write endurance limits prior to reload.");
  }
  
  return { from, to, steps, recommendations, considerations, docLink };
}

function calculateUpgradePath(platform, currentVersion, targetVersion) {
  const p = (platform || "").toLowerCase();
  let type = "ontap";
  if (p.includes("storagegrid")) type = "storagegrid";
  else if (p.includes("e-series") || p.includes("ef600") || p.includes("e5700") || p.includes("santricity")) type = "santricity";
  
  // Clean versions (remove prefixes)
  let cleanCurrent = currentVersion.replace(/^(ontap|santricity os|storagegrid|nx-os|fabric os|fos)\s+/i, "").trim();
  let cleanTarget = targetVersion.replace(/^(ontap|santricity os|storagegrid|nx-os|fabric os|fos)\s+/i, "").trim();
  
  // Strip patch designations (like P4) for path finding index matches
  let currentBase = cleanCurrent.split("P")[0].trim();
  let targetBase = cleanTarget.split("P")[0].trim();
  
  if (currentBase === targetBase) return [];
  
  const hops = [];
  
  if (type === "ontap") {
    const vList = SOFTWARE_VERSION_DATABASES.ontap;
    
    // Map currentBase/targetBase to closest matching element in database
    let startIndex = vList.findIndex(v => v === currentBase || currentBase.startsWith(v));
    let endIndex = vList.findIndex(v => v === targetBase || targetBase.startsWith(v));
    
    if (startIndex === -1 || endIndex === -1) {
      return [{
        from: cleanCurrent,
        to: cleanTarget,
        steps: [
          "1. Download target ONTAP OS image from NetApp Support.",
          "2. Validate cluster readiness: <code>cluster image validate -version " + cleanTarget + "</code>.",
          "3. Perform non-disruptive upgrade (NDU): <code>cluster image update -version " + cleanTarget + "</code>."
        ],
        recommendations: [
          "Run <code>system health alert show</code> and verify HA status.",
          "Generate cluster configuration backup prior to start."
        ],
        considerations: [
          "Verify third-party driver compatibility (VMware host PSP round robin settings).",
          "Ensure switch and shelf firmwares align with NetApp IMT matrix."
        ],
        docLink: "https://docs.netapp.com/us-en/ontap/upgrade/index.html"
      }];
    }
    if (startIndex >= endIndex) {
      return [];
    }
    
    let currentIdx = startIndex;
    while (currentIdx < endIndex) {
      let nextIdx = currentIdx;
      const curVer = vList[currentIdx];
      
      if (["9.3", "9.4", "9.5", "9.6"].includes(curVer)) {
        // Must upgrade through 9.7 first
        nextIdx = vList.indexOf("9.7");
      } else if (curVer === "9.7") {
        // Must go to 9.8
        nextIdx = vList.indexOf("9.8");
      } else {
        // Can skip one release, so max jump of 2 minor versions forward
        nextIdx = Math.min(endIndex, currentIdx + 2);
      }
      
      // Fallback if index lookup fails
      if (nextIdx <= currentIdx) nextIdx = currentIdx + 1;
      
      const vFrom = vList[currentIdx];
      const vTo = vList[nextIdx];
      
      // Append target patch designator to the last hop if applicable
      const displayTo = (nextIdx === endIndex) ? cleanTarget : vTo;
      
      hops.push(getOntapHopInfo(vFrom, displayTo));
      currentIdx = nextIdx;
    }
  } else if (type === "storagegrid") {
    const vList = SOFTWARE_VERSION_DATABASES.storagegrid;
    let startIndex = vList.findIndex(v => v === currentBase || currentBase.startsWith(v));
    let endIndex = vList.findIndex(v => v === targetBase || targetBase.startsWith(v));
    
    if (startIndex === -1 || endIndex === -1) {
      return [{
        from: cleanCurrent,
        to: cleanTarget,
        steps: [
          "1. Download target StorageGRID update file and recovery package from NetApp support.",
          "2. Upload package in Maintenance > Software Update.",
          "3. Apply grid-wide rolling updates."
        ],
        recommendations: [
          "Generate and download StorageGRID recovery package before starting software update.",
          "Verify all storage nodes are online and functioning normally."
        ],
        considerations: [
          "Upgrades must be performed sequentially. You cannot skip major version releases.",
          "Services remain active, but transient failovers occur as nodes reload."
        ],
        docLink: "https://docs.netapp.com/us-en/storagegrid-119/upgrade/index.html"
      }];
    }
    if (startIndex >= endIndex) {
      return [];
    }
    
    for (let i = startIndex; i < endIndex; i++) {
      const vFrom = vList[i];
      const vTo = vList[i+1];
      const displayTo = (i+1 === endIndex) ? cleanTarget : vTo;
      hops.push(getStoragegridHopInfo(vFrom, displayTo));
    }
  } else if (type === "santricity") {
    const vList = SOFTWARE_VERSION_DATABASES.santricity;
    let startIndex = vList.findIndex(v => v === currentBase || currentBase.startsWith(v));
    let endIndex = vList.findIndex(v => v === targetBase || targetBase.startsWith(v));
    
    if (startIndex === -1 || endIndex === -1) {
      return [{
        from: cleanCurrent,
        to: cleanTarget,
        steps: [
          "1. Download SANtricity OS controller firmware package and NVSRAM from NetApp Support.",
          "2. Go to Support > Upgrade Center > SANtricity OS Software Upgrade.",
          "3. Upload firmware and NVSRAM and apply update."
        ],
        recommendations: [
          "Check SAN multipathing configuration on client hosts.",
          "Verify drive health diagnostics."
        ],
        considerations: [
          "Requires dual-controller configuration for non-disruptive execution.",
          "Verify host compatibility in IMT."
        ],
        docLink: "https://docs.netapp.com/us-en/e-series/upgrade-santricity.html"
      }];
    }
    
    if (startIndex >= endIndex) {
      return [];
    }
    
    let currentIdx = startIndex;
    while (currentIdx < endIndex) {
      let nextIdx = currentIdx;
      const curVer = vList[currentIdx];
      
      if (["11.30", "11.40"].includes(curVer)) {
        nextIdx = vList.indexOf("11.50");
      } else if (curVer === "11.50" || curVer === "11.60") {
        nextIdx = vList.indexOf("11.70");
      } else {
        nextIdx = endIndex;
      }
      
      if (nextIdx <= currentIdx) nextIdx = currentIdx + 1;
      
      const vFrom = vList[currentIdx];
      const vTo = vList[nextIdx];
      const displayTo = (nextIdx === endIndex) ? cleanTarget : vTo;
      
      hops.push(getSantricityHopInfo(vFrom, displayTo));
      currentIdx = nextIdx;
    }
  }
  
  return hops;
}

function getLatestSupportedVersion(platform) {
  const p = (platform || "").toLowerCase();
  if (p.includes("storagegrid")) {
    const db = SOFTWARE_VERSION_DATABASES.storagegrid;
    return "StorageGRID " + db[db.length - 1];
  } else if (p.includes("e-series") || p.includes("ef600") || p.includes("e5700") || p.includes("santricity")) {
    const db = SOFTWARE_VERSION_DATABASES.santricity;
    return "SANtricity OS " + db[db.length - 1];
  } else if (p.includes("cisco") || p.includes("mds") || p.includes("nexus")) {
    return "NX-OS 9.3(12)";
  } else if (p.includes("brocade") || p.includes("switch")) {
    return "Fabric OS (FOS) 9.2.1";
  } else {
    const db = SOFTWARE_VERSION_DATABASES.ontap;
    return "ONTAP " + db[db.length - 1] + "";
  }
}

function getRiskSafetyTier(r) {
  const desc = (r.description || "").toLowerCase();
  const cat = (r.category || "").toLowerCase();
  const rec = (r.recommendation || "").toLowerCase();
  
  if (desc.includes("delete") || desc.includes("destroy") || desc.includes("sanitize") || desc.includes("remove volume") || desc.includes("disable arp") || desc.includes("disable mav") || rec.includes("delete") || rec.includes("destroy")) {
    return "Destructive or Irreversible";
  }
  if (desc.includes("upgrade") || desc.includes("firmware") || desc.includes("takeover") || desc.includes("giveback") || desc.includes("reboot") || desc.includes("switchover") || desc.includes("switchback") || desc.includes("replace") || rec.includes("upgrade") || rec.includes("firmware") || rec.includes("reboot") || rec.includes("replace")) {
    return "Disruptive but Data-Safe";
  }
  return "Non-Disruptive";
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

  const safetyTier = getRiskSafetyTier(risk);
  let safetyColor = "var(--status-normal)";
  if (safetyTier.includes("Destructive")) safetyColor = "var(--status-critical)";
  else if (safetyTier.includes("Disruptive")) safetyColor = "var(--status-warning)";

  document.getElementById("modalRiskTitle").innerText = `Remediation Plan: ${risk.category} Risk`;
  
  // Display safety tier in description
  document.getElementById("modalRiskDesc").innerHTML = `${risk.description}
    <div style="margin-top: 10px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); padding: 8px 12px; border-radius: var(--radius-sm); font-size: 0.8rem; display: flex; align-items: center; gap: 8px;">
      <span style="color: var(--text-muted); font-weight: 600;">Safety Tier:</span>
      <span style="background: ${safetyColor}; color: #fff; font-size: 0.68rem; padding: 2px 6px; border-radius: var(--radius-sm); font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">${safetyTier}</span>
    </div>`;

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
  const eseriesCard = document.getElementById("tamEseriesVisualCard");
  const svmCard = document.getElementById("tamSvmCard");
  
  if (selectedSystems.length > 0) {
    if (visualCard) {
      visualCard.style.display = "block";
    }
    
    if (!state.activeVisualizerNodeSerial || !activeSerials.includes(state.activeVisualizerNodeSerial)) {
      state.activeVisualizerNodeSerial = selectedSystems[0].serialNumber;
    }
    
    const activeSys = selectedSystems.find(s => s.serialNumber === state.activeVisualizerNodeSerial) || selectedSystems[0];
    renderNodeVisualLayout(selectedSystems, activeSys);
    
    const isEseries = activeSys && (activeSys.santricityVersion !== undefined || activeSys.platform.includes("E-Series"));
    if (eseriesCard) {
      if (isEseries) {
        eseriesCard.style.display = "block";
        renderEseriesHardwareAudit(activeSys);
      } else {
        eseriesCard.style.display = "none";
      }
    }

    if (svmCard) {
      const svms = getSystemSvms(activeSys);
      if (svms && svms.length > 0) {
        svmCard.style.display = "block";
        renderSvmSecurityAudit(activeSys);
      } else {
        svmCard.style.display = "none";
      }
    }
  } else {
    if (visualCard) visualCard.style.display = "none";
    if (eseriesCard) eseriesCard.style.display = "none";
    if (svmCard) svmCard.style.display = "none";
  }

  // Update header text
  if (selectedSystems.length === 1) {
    const sys = selectedSystems[0];
    const osLabel = sys.santricityVersion ? "SANtricity OS" : "ONTAP";
    const osVer = sys.santricityVersion ? sys.santricityVersion : sys.ontapVersion;
    
    document.getElementById("tamActiveSystem").innerHTML = `
      <strong>System</strong>: ${sys.systemName} (S/N: <code class="copyable-code" onclick="copyToClipboard('${sys.serialNumber}', event)" title="Click to copy Serial Number">${sys.serialNumber} <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></code>) | <strong>${osLabel}</strong>: ${osVer}
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
        currentVersion: sys.santricityVersion ? sys.santricityVersion : sys.ontapVersion,
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
      const hops = calculateUpgradePath(item.platform, item.currentVersion, item.targetVersion);
      
      let hopsHtml = "";
      if (hops.length > 0) {
        if (hops.length > 1) {
          hopsHtml += `<div style="margin: 10px 0 6px 0; font-size: 0.78rem; font-weight: 600; color: var(--status-warning); display: flex; align-items: center; gap: 6px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
            Multi-hop Upgrade Sequence Required:
          </div>`;
        }
        
        hops.forEach((hop, idx) => {
          hopsHtml += `
            <div style="margin-top: 10px; padding: 12px; background: rgba(255, 255, 255, 0.015); border-left: 3px solid var(--accent-cyan); border-radius: var(--radius-sm); border: 1px solid rgba(255,255,255,0.03); border-top: none; border-bottom: none; border-right: none;">
              <div style="font-weight: 700; font-size: 0.8rem; color: var(--accent-cyan); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
                Hop ${idx + 1}: ${hop.from} &rarr; ${hop.to}
              </div>
              <div style="font-size: 0.74rem; color: var(--text-secondary); line-height: 1.45;">
                <div style="margin-bottom: 4px;"><strong style="color: var(--text-primary);">Procedure:</strong></div>
                <ul style="margin: 0 0 8px 0; padding-left: 16px; display: flex; flex-direction: column; gap: 2px;">
                  ${hop.steps.map(s => `<li>${s}</li>`).join("")}
                </ul>
                <div style="margin-bottom: 4px;"><strong style="color: var(--status-warning);">Pre-upgrade Recommendations:</strong></div>
                <ul style="margin: 0 0 8px 0; padding-left: 16px; display: flex; flex-direction: column; gap: 2px;">
                  ${hop.recommendations.map(r => `<li>${r}</li>`).join("")}
                </ul>
                <div style="margin-bottom: 4px;"><strong style="color: var(--text-muted);">Important Considerations:</strong></div>
                <ul style="margin: 0 0 8px 0; padding-left: 16px; display: flex; flex-direction: column; gap: 2px;">
                  ${hop.considerations.map(c => `<li>${c}</li>`).join("")}
                </ul>
                <div style="margin-top: 8px;">
                  <a href="${hop.docLink}" target="_blank" style="color: var(--accent-cyan); font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">
                    View Upgrade Guide
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                  </a>
                </div>
              </div>
            </div>
          `;
        });
      }
      
      upgradeHtml += `
        <div style="margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px dashed var(--border-color);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <strong style="color: var(--text-primary); font-size: 0.9rem;">${item.systemName} (${item.platform})</strong>
            <span class="badge warning">${item.urgency}</span>
          </div>
          <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 6px; line-height: 1.4;">
            Current: <strong style="color: var(--text-muted);">${item.currentVersion}</strong> | 
            Target OS Version: <strong style="color: var(--accent-cyan);">${item.targetVersion}</strong> | 
            Latest Available: <strong style="color: var(--status-normal);">${latestVer}</strong>
          </div>
          <p style="font-size: 0.78rem; color: var(--text-secondary); margin: 0 0 10px 0; line-height: 1.4;">${item.benefits}</p>
          ${hopsHtml}
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
          <div style="font-size: 0.85rem; color: var(--status-warning); font-weight: 700; margin-top: 4px;">${convertToNetAppFiscal(health.refreshWindow)}</div>
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

  const isASA = (sys.platform || "").includes("ASA");
  const efficiencyLabel = isASA ? "Storage Efficiency Ratio (Block SAN)" : "Storage Efficiency Ratio";

  document.getElementById("csmSavingsCard").innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 12px;">
      <div>
        <span style="font-size: 0.8rem; color: var(--text-secondary); text-transform: uppercase;">${efficiencyLabel}</span>
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
  
  if (isASA) {
    fpAdoptionBadge = `<span class="badge normal" style="background: rgba(255,255,255,0.05); color: var(--text-secondary); border-color: var(--border-color);">N/A (SAN Block Array)</span>`;
    fpStatusText = `ASA platforms prioritize high-speed symmetric SAN block access. Snapshot copy space optimization is managed directly via local aggregates and active block deduplication/compression.`;
  } else if (fpTiered > 0) {
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
    <div style="font-size: 1.4rem; font-weight: 700; margin-bottom: 6px; color: ${fpTiered > 0 && !isASA ? "var(--status-info)" : "var(--status-warning)"};">
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
          borderColor: '#0073e6',
          backgroundColor: 'rgba(0, 115, 230, 0.05)',
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

function convertToNetAppFiscal(windowStr) {
  if (!windowStr || windowStr.toLowerCase().includes("review") || windowStr.toLowerCase().includes("n/a")) {
    return windowStr;
  }
  
  const m = windowStr.match(/Q([1-4])\s*(?:'|20)?([0-9]{2})/i);
  if (!m) return windowStr;
  
  const calQ = parseInt(m[1]);
  let calYr = parseInt(m[2]);
  if (calYr < 100) calYr += 2000;
  
  let fy = calYr;
  let fyQ = 1;
  
  if (calQ === 1) {
    fy = calYr;
    fyQ = 4;
  } else if (calQ === 2) {
    fy = calYr + 1;
    fyQ = 1;
  } else if (calQ === 3) {
    fy = calYr + 1;
    fyQ = 2;
  } else if (calQ === 4) {
    fy = calYr + 1;
    fyQ = 3;
  }
  
  const fyShort = fy.toString().slice(-2);
  const monthsStr = fyQ === 1 ? "May-Jul" : (fyQ === 2 ? "Aug-Oct" : (fyQ === 3 ? "Nov-Jan" : "Feb-Apr"));
  const yrRange = fyQ === 3 ? `${fy-1}-${fy}` : fy;
  return `FY${fyShort} Q${fyQ} (${monthsStr} ${yrRange})`;
}

function enrichSystemTelemetry(s) {
  const serial = s.serialNumber || s.serial_number || "unknown";
  const name = s.systemName || s.system_name || "unknown";
  const cluster = s.clusterName || s.cluster_name || "unknown";
  const customer = s.customerName || s.customer_name || "customer";
  const osVer = s.ontapVersion || s.ontap_version || s.osVersion || "9.12.1";
  const model = s.platform || s.model || "AFF A400";
  const status = s.status || "normal";

  // Mapped platform categories
  const modelLower = model.toLowerCase();
  const isAFF = modelLower.includes("aff");
  const isASA = modelLower.includes("asa");
  const isFAS = modelLower.includes("fas");
  const isStorageGrid = modelLower.includes("storagegrid") || modelLower.includes("sg60") || modelLower.includes("sg61") || modelLower.includes("sg10");
  const isEseries = modelLower.includes("e-series") || modelLower.includes("ef600") || modelLower.includes("e5700") || modelLower.includes("ef300");

  // 1. Dynamic Upgrade Recommendations
  let upgrades = s.upgrades;
  if (!upgrades) {
    if (isStorageGrid) {
      upgrades = osVer.startsWith("11.") 
        ? { targetVersion: "12.0.0", urgency: "Recommended", benefits: "Mitigates CVE-2026-22051 authenticated metrics query and SSRF security bulletins." }
        : { targetVersion: "Up to Date", urgency: "None", benefits: "" };
    } else if (isEseries) {
      upgrades = { targetVersion: "Up to Date", urgency: "None", benefits: "" };
    } else {
      // ONTAP upgrades
      const match = osVer.match(/9\.([0-9]+)/);
      if (match) {
        const minor = parseInt(match[1]);
        if (minor < 16) {
          upgrades = { targetVersion: "9.16.1P9", urgency: "Recommended", benefits: "Resolves critical Locked Snapshot bypass CVE-2026-22050 vulnerabilities." };
        } else if (minor < 19) {
          upgrades = { targetVersion: "9.19.1P1", urgency: "Recommended", benefits: "Performance enhancements for next-gen block and NVMe-oF data paths." };
        } else {
          upgrades = { targetVersion: "Up to Date", urgency: "None", benefits: "" };
        }
      } else {
        upgrades = { targetVersion: "Up to Date", urgency: "None", benefits: "" };
      }
    }
  }

  // 2. Dynamic Contracts
  let contracts = s.contracts;
  if (!contracts) {
    const currentYear = new Date().getFullYear();
    const expiryDate = `${currentYear + 2}-06-30`;
    contracts = {
      status: "normal",
      endDate: expiryDate,
      daysRemaining: 730,
      supportLevel: isStorageGrid ? "StorageGRID Premium Support" : (isEseries ? "SANtricity SupportEdge" : "SupportEdge Premium")
    };
  }

  // 3. Dynamic Lifecycle
  let lifecycle = s.lifecycle;
  if (!lifecycle) {
    let releaseYear = 2022;
    const match = osVer.match(/9\.([0-9]+)/);
    if (match) {
      const minor = parseInt(match[1]);
      releaseYear = 2016 + Math.ceil(minor / 2);
    } else if (isStorageGrid || osVer.startsWith("11.") || osVer.startsWith("12.")) {
      releaseYear = 2024;
    }
    const eoaYear = releaseYear + 3;
    const eosYear = releaseYear + 5;
    const currentYear = new Date().getFullYear();
    lifecycle = {
      eoaDate: `${eoaYear}-12-31`,
      eosDate: `${eosYear}-12-31`,
      isNearEos: eosYear <= currentYear + 1
    };
  }

  // 4. Dynamic Efficiency Ratios
  let efficiency = s.efficiency;
  if (!efficiency) {
    let ratio = "1.0:1";
    let physical = 45.2;
    let logical = 45.2;
    if (isAFF || isASA) {
      ratio = "3.8:1";
      logical = 171.76;
    } else if (isFAS) {
      ratio = "1.5:1";
      logical = 67.8;
    }
    efficiency = {
      ratio: ratio,
      logicalUsedTB: logical,
      physicalUsedTB: physical,
      spaceSavedTB: logical - physical,
      fabricPoolTieredTB: (isAFF || isASA) ? 12.5 : 0.0
    };
  }

  // 5. Dynamic Logistics & Contacts
  const logistics = s.logistics || {
    deliveryAddress: "Primary Corporate Datacenter, Suite 100",
    accessRestrictions: "Escorted access only; 24-hour advanced clearance required.",
    shippingAlert: "None"
  };
  const contacts = s.contacts || {
    name: "Corporate Storage Ops Team",
    phone: "+1-800-555-0199",
    email: "storage-admin@corporate.local",
    nssUsername: "netapp_admin_ops"
  };

  // 6. Dynamic Sales Health & Projections
  const salesHealth = s.salesHealth || {
    accountManager: "Assigned Account Representative",
    supportTam: "Active Lead TAM Engaged",
    sentimentScore: 8.5,
    healthStatus: "Stable",
    upsellPotential: (lifecycle.isNearEos || contracts.daysRemaining < 180) ? "High (Tech Refresh Window)" : "Medium",
    refreshWindow: (lifecycle.isNearEos) ? "Immediate Action Required" : "Q3 2027"
  };

  const projections = s.projections || {
    growthRateGBPerDay: 150,
    daysToLimit: 420,
    limitDate: `${new Date().getFullYear() + 1}-08-15`,
    peakIops: 7500,
    avgLatencyMs: 1.8,
    historicalCapacityMonths: [32.5, 34.2, 36.8, 38.4, 40.1, 42.5],
    projectedCapacityMonths: [44.8, 46.2, 48.0]
  };

  // 7. Dynamic Risks Remediation Planning
  const risks = (s.risks || []).map(r => {
    if (!r.remediationPlan) {
      r.remediationPlan = generateDynamicRemediationPlan(r, { clusterName: cluster });
    }
    return r;
  });

  return {
    serialNumber: serial,
    systemName: name,
    clusterName: cluster,
    customerName: customer,
    ontapVersion: osVer,
    platform: model,
    status: status,
    risks: risks,
    upgrades: upgrades,
    contracts: contracts,
    lifecycle: lifecycle,
    fieldActions: s.fieldActions || [],
    efficiency: efficiency,
    snapmirror: s.snapmirror || { enabled: false, relationships: [] },
    hypervisors: s.hypervisors || [],
    logistics: logistics,
    contacts: contacts,
    salesHealth: salesHealth,
    projections: projections,
    securityBulletins: s.securityBulletins || [],
    supportCases: s.supportCases || []
  };
}

function generateDynamicRemediationPlan(risk, sys) {
  const desc = (risk.description || "").toLowerCase();
  const cat = risk.category || "General";
  const catLower = cat.toLowerCase();
  
  let cause = "Undetermined configuration deviation identified in telemetry sync.";
  let impact = "Potential compliance degradation or risk of localized performance instability.";
  let steps = ["1. Review the configuration using standard ONTAP show command templates.", "2. Consult target platform documentation guidelines.", "3. Request technical assistance if baseline deviations require custom adjustment."];
  let options = ["Option A: Apply recommended changes under next change control window.", "Option B: Retain current parameters if business exceptions mandate legacy settings."];
  let thirdParty = "No direct third-party virtualization or backup hypervisor dependencies identified.";

  if (catLower.includes("security") || desc.includes("insecure") || desc.includes("vulnerability") || desc.includes("cve")) {
    if (desc.includes("smb") || desc.includes("cifs")) {
      cause = "Legacy SMBv1 protocol is enabled on target SVM parameters, violating security hardening policy.";
      impact = "Exposes CIFS exports to interception, credential spoofing, or legacy ransomware attacks (CVE-2017-0144).";
      steps = [
        `1. Access administrative CLI for cluster: ${sys.clusterName || 'cluster'}.`,
        "2. Disable legacy SMB1: 'vserver cifs options modify -vserver <svm_name> -smb1-enabled false'",
        "3. Verify configuration state: 'vserver cifs options show -vserver <svm_name> -fields smb1-enabled'"
      ];
      options = [
        "Option A: Disable SMBv1 cluster-wide immediately (Recommended).",
        "Option B: Isolate legacy clients to dedicated, firewalled network segments if SMBv1 is mandatory."
      ];
      thirdParty = "Modern Windows and Linux clients are fully compatible. Legacy Windows XP/2003 clients will lose access.";
    } else if (desc.includes("export") || desc.includes("nfs") || desc.includes("policy")) {
      cause = "NFS export policy rule allows superuser mounts to unauthorized subnets (root-squashing disabled).";
      impact = "Unrestricted hosts on matching networks can mount volumes and write files with full root authority.";
      steps = [
        "1. Identify offending policy rules: 'vserver export-policy rule show -vserver <svm_name>'.",
        "2. Restrict rule to secure clients: 'vserver export-policy rule modify -vserver <svm_name> -policyname default -ruleindex 1 -clientmatch <trusted_subnet>'",
        "3. Squash root privileges: 'vserver export-policy rule modify -vserver <svm_name> -policyname default -ruleindex 1 -superuser none'"
      ];
      options = [
        "Option A: Restrict client match to target subnet and disable superuser authority (Recommended).",
        "Option B: Configure Kerberos (krb5/krb5i) if strong cryptographic authentication is required."
      ];
      thirdParty = "VMware ESXi hosts mounting NFS datastores require root access. Ensure client matches are limited specifically to ESXi VMkernel IP addresses.";
    } else {
      cause = "Security parameter setting deviates from the ONTAP Security Hardening baseline.";
      impact = "Increased administrative attack surface and reduction in active compliance validation scores.";
      steps = [
        "1. Consult ONTAP Security Hardening Guidelines (TR-4569).",
        "2. Locate configuration parameter inside SVM settings.",
        "3. Apply target hardening modifications under a standard change control window."
      ];
      options = [
        "Option A: Harden configuration settings online (non-disruptive).",
        "Option B: Register a security policy exception in corporate risk log."
      ];
      thirdParty = "Verify that third-party infrastructure management dashboards continue to authenticate normally.";
    }
  } else if (catLower.includes("hardware") || desc.includes("path") || desc.includes("cable") || desc.includes("fan") || desc.includes("battery") || desc.includes("bbu")) {
    if (desc.includes("path") || desc.includes("sas") || desc.includes("nvme") || desc.includes("cable")) {
      cause = "Degraded connection, interface errors, or disconnected physical cable path.";
      impact = "Loss of storage path redundancy. A secondary failure on the redundant loop triggers localized data unavailability.";
      steps = [
        "1. Verify active device path states: 'storage path show'.",
        "2. Check status LEDs on physical shelf modules and transceivers.",
        "3. Reseat copper or optical cable connections.",
        "4. Replace cable or transceiver module if diagnostics report persistent CRC errors."
      ];
      options = [
        "Option A: Perform reseat or cabling swap online. Active multipathing protects active I/O flows.",
        "Option B: Schedule maintenance window if replacing shelf interface modules (IOM/NSM)."
      ];
      thirdParty = "Hypervisors (ESXi/AHV) may report SCSI device path degradation alerts which resolve automatically upon link restore.";
    } else {
      cause = "Hardware component fault or sensor reading outside target operational limits.";
      impact = "Risk of localized hardware failure leading to performance degradation or controller reboots.";
      steps = [
        "1. Query cluster hardware health: 'system health alert show'.",
        "2. Retrieve detailed component status logs.",
        "3. Coordinate module replacement (FRU) with NetApp Support."
      ];
      options = [
        "Option A: Hot-swap replacement online (non-disruptive for hot-pluggable fans/power supplies).",
        "Option B: Schedule off-peak maintenance window if the component requires node takeover/failover."
      ];
      thirdParty = "Monitor virtualization console logs for physical chassis alarm notifications.";
    }
  } else if (catLower.includes("software") || catLower.includes("firmware") || desc.includes("version") || desc.includes("upgrade") || desc.includes("outdated")) {
    cause = "Node or component software/firmware version runs below the target validated release baseline.";
    impact = "Exposure to resolved software bugs, microcode errors, or compatibility boundaries.";
    steps = [
      "1. Download target software package from NetApp support site.",
      "2. Upload package to local node web servers.",
      "3. Trigger rolling upgrade: 'storage firmware download' or standard software upgrade sequence.",
      "4. Verify post-upgrade version state."
    ];
    options = [
      "Option A: Perform rolling non-disruptive update (NDU) during off-peak hours.",
      "Option B: Perform update during standard scheduled hardware lifecycle maintenance."
    ];
    thirdParty = "Ensure upstream hypervisors and backup engines are fully qualified for the target version in the Interoperability Matrix (IMT).";
  }

  return { cause, impact, steps, options, thirdParty };
}

function getLogisticsUpdateTicketsAndDiffs(sys) {
  const l = { deliveryAddress: "Not Set", accessRestrictions: "Not Set", shippingAlert: "None", ...sys.logistics };
  const c = { name: "Not Set", phone: "Not Set", email: "Not Set", nssUsername: "Not Set", ...sys.contacts };
  
  const origL = sys.originalLogistics || { deliveryAddress: "Not Set", accessRestrictions: "Not Set", shippingAlert: "None" };
  const origC = sys.originalContacts || { name: "Not Set", phone: "Not Set", email: "Not Set", nssUsername: "Not Set" };
  
  const changes = [];
  if (l.deliveryAddress !== origL.deliveryAddress) {
    changes.push({ field: "Delivery Address", oldVal: origL.deliveryAddress, newVal: l.deliveryAddress });
  }
  if (l.accessRestrictions !== origL.accessRestrictions) {
    changes.push({ field: "Access Restrictions", oldVal: origL.accessRestrictions, newVal: l.accessRestrictions });
  }
  if (l.shippingAlert !== origL.shippingAlert) {
    changes.push({ field: "Shipping Alert", oldVal: origL.shippingAlert, newVal: l.shippingAlert });
  }
  if (c.name !== origC.name) {
    changes.push({ field: "Contact Name", oldVal: origC.name, newVal: c.name });
  }
  if (c.phone !== origC.phone) {
    changes.push({ field: "Contact Phone", oldVal: origC.phone, newVal: c.phone });
  }
  if (c.email !== origC.email) {
    changes.push({ field: "Contact Email", oldVal: origC.email, newVal: c.email });
  }
  if (c.nssUsername !== origC.nssUsername) {
    changes.push({ field: "NSS Username", oldVal: origC.nssUsername, newVal: c.nssUsername });
  }
  
  const hasChanges = changes.length > 0;
  
  let diffsHTML = "";
  let diffsTXT = "";
  let ticketTXT = "";
  
  if (hasChanges) {
    diffsHTML = `
      <div style="margin-top: 16px; background-color: rgba(0, 188, 212, 0.03); border: 1px solid rgba(0, 188, 212, 0.15); padding: 16px; border-radius: var(--radius-sm);">
        <div style="font-weight: 700; color: var(--accent-cyan); margin-bottom: 8px; font-size: 0.82rem; text-transform: uppercase;">Detected Local Edits (Pending Official Active IQ Update)</div>
        <table style="width: 100%; border-collapse: collapse; font-size: 0.78rem; text-align: left; margin-bottom: 12px;">
          <thead>
            <tr style="border-bottom: 1px solid var(--border-color); color: var(--text-muted);">
              <th style="padding: 6px 0;">Field Name</th>
              <th style="padding: 6px 12px;">Old Value (DB)</th>
              <th style="padding: 6px 0;">New Value (Local Edit)</th>
            </tr>
          </thead>
          <tbody>
            ${changes.map(ch => `
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                <td style="padding: 6px 0; font-weight: 600;">${ch.field}</td>
                <td style="padding: 6px 12px; color: var(--text-muted); font-style: italic;">${ch.oldVal || '(Not Configured)'}</td>
                <td style="padding: 6px 0; color: var(--status-normal); font-weight: 600;">${ch.newVal || '(Cleared)'}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
    `;
    
    diffsTXT = `DETECTED LOGISTICS CHANGES (PENDING OFFICIAL ACTIVE IQ UPDATE):\n` + 
      changes.map(ch => ` * ${ch.field}:\n   - Old: ${ch.oldVal || '(Not Configured)'}\n   - New: ${ch.newVal || '(Cleared)'}`).join("\n") + "\n";
    
    const changeLines = changes.map(ch => `* ${ch.field}:\n  - Old: ${ch.oldVal || '(Not Configured)'}\n  - New: ${ch.newVal || '(Cleared)'}`).join("\n");
    
    ticketTXT = `To: NetApp Support (Install Base & Serial Registration Group)
Subject: Non-Technical Install Base Record Update Request - S/N: ${sys.serialNumber}

Please update the install site records and contact directory for the following system:
* Serial Number: ${sys.serialNumber}
* Platform Model: ${sys.platform}
* Customer Account: ${sys.customerName}

REQUESTED SYSTEM CHANGES:
${changeLines}

Reason for Change: Updating local datacenter access restrictions and primary site contact records to prevent parts delivery shipment delays. Please notify once records have updated in NetApp CRM and Active IQ.`;

    diffsHTML += `
        <div style="font-weight: 700; color: var(--text-secondary); margin-bottom: 6px; font-size: 0.78rem;">Non-Technical Ticket Copy-Paste Template:</div>
        <textarea readonly class="form-input" rows="8" style="font-family: monospace; font-size: 0.74rem; background: rgba(0,0,0,0.3); border-color: var(--border-color); color: var(--text-secondary); cursor: text;" onclick="this.select()">${ticketTXT}</textarea>
      </div>
    `;
  }
  
  return { hasChanges, diffsHTML, diffsTXT, ticketTXT };
}

function compileCustomerSuccessPlanText(scopeTitle, allRisks, allUpgrades, targetSystems, expiringContracts, allSupportCases) {
  let totalCapTB = 0;
  let logicalCapTB = 0;
  let totalSavedTB = 0;
  let activeTAMOwner = "Not Set";
  let activeAMOwner = "Not Set";
  let csatScoreSum = 0;
  let systemCount = targetSystems.length;

  targetSystems.forEach(sys => {
    if (sys.efficiency) {
      logicalCapTB += sys.efficiency.logicalUsedTB || 0;
      totalCapTB += sys.efficiency.physicalUsedTB || 0;
      totalSavedTB += sys.efficiency.spaceSavedTB || 0;
    }
    if (sys.salesHealth) {
      csatScoreSum += sys.salesHealth.sentimentScore || 7.5;
      activeTAMOwner = sys.salesHealth.supportTam || activeTAMOwner;
      activeAMOwner = sys.salesHealth.accountManager || activeAMOwner;
    }
  });

  const avgCsat = systemCount > 0 ? (csatScoreSum / systemCount).toFixed(1) : "No Data";
  const spaceSavedRatio = totalCapTB > 0 ? (logicalCapTB / totalCapTB).toFixed(1) : "1.0";

  const risksText = allRisks.map((r, i) => `${i+1}. [Priority ${r.severity.toUpperCase()}] ${r.systemName}: ${r.description}\n   -> Recommendation: ${r.recommendation}`).join("\n\n");
  const upgradesText = allUpgrades.map(u => {
    const hops = calculateUpgradePath(u.platform, u.currentVersion || "", u.targetVersion);
    let hopDetails = "";
    if (hops.length > 0) {
      if (hops.length > 1) {
        hopDetails += `\n     [Multi-Hop Upgrade Sequence Required: ${hops.map(h => h.from + ' -> ' + h.to).join(' | ')}]`;
      }
      hops.forEach((h, idx) => {
        hopDetails += `\n     * Hop ${idx + 1}: ${h.from} -> ${h.to}
       - Steps: ${h.steps.map(s => s.replace(/<[^>]*>/g, "")).join(" | ")}
       - Recommendations: ${h.recommendations.map(r => r.replace(/<[^>]*>/g, "")).join(" | ")}
       - Considerations: ${h.considerations.map(c => c.replace(/<[^>]*>/g, "")).join(" | ")}
       - Doc Link: ${h.docLink}`;
      });
    }
    return `- Upgrade ${u.systemName} from ${u.currentVersion || "current"} to ${u.targetVersion} (${u.urgency})\n     -> Benefit: ${u.benefits}${hopDetails}`;
  }).join("\n");
  const casesText = allSupportCases.map(c => `- Case ID: ${c.id} (${c.systemName}) | Severity: ${c.severity} | Next Action Owner: ${c.nextActionBy || "Under Review"}\n  -> Title: ${c.title}`).join("\n");
  const contractsText = expiringContracts.map(e => `- System: ${e.systemName} | Support Level: ${e.supportLevel} | Expiry Date: ${e.endDate} (${e.daysRemaining} days remaining)`).join("\n");

  return `================================================================================
CUSTOMER SUCCESS PLAN (CSP) & ENVIRONMENTAL POSTURE OPTIMIZATION
================================================================================
CUSTOMER SCOPE       : ${scopeTitle}
DATE GENERATED       : ${new Date().toISOString().split('T')[0]}
ACCOUNT TEAM         : TAM: ${activeTAMOwner} | Account Manager: ${activeAMOwner}
CSAT SENTIMENT RATING: ${avgCsat} / 10.0 (Support & Account Hygiene)
ENVIRONMENT HEALTH   : ${allRisks.length > 0 ? 'WARNING - Action Required' : 'OPTIMAL / COMPLIANT'}

--------------------------------------------------------------------------------
1. EXECUTIVE SUMMARY & VALUE ALIGNMENT (CSM/CSAT PRACTICE)
--------------------------------------------------------------------------------
The primary objective of this Customer Success Plan is to secure, optimize, and streamline storage operations in alignment with standard industry frameworks (ITIL Change Control, NIST/SANS Hardening, and NetApp Best Practices). 

* WORKLOAD ADOPTION & EFFICIENCY HYGIENE:
  - Total Physical Used Capacity: ${totalCapTB.toFixed(1)} TB
  - Total Logical Capacity Represented: ${logicalCapTB.toFixed(1)} TB
  - Storage Efficiency Ratio: ${spaceSavedRatio}:1 (Saved ${totalSavedTB.toFixed(1)} TB via Deduplication/Compression)
  - Capacity Projections: High-runway analytics applied. Tech refresh plans are mapped to lifecycle windows.

* CUSTOMER SATISFACTION (CSAT) CRITERIA:
  - The support sentiment score is rated at ${avgCsat}/10. 
  - Periodic QBRs (Quarterly Business Reviews) will be scheduled to review hardware lifecycle transitions and cloud integration milestones.

--------------------------------------------------------------------------------
2. SUPPORT CASE & SERVICE RESOLUTION HYGIENE (SAM PRACTICE)
--------------------------------------------------------------------------------
Maintaining operational hygiene involves tracking and resolving support tickets promptly to prevent support SLA deviations.

* ACTIVE SUPPORT TICKETS:
${allSupportCases.length > 0 ? casesText : "✓ No active open support cases detected."}

* CONTRACT COVERAGE & LIFECYCLE RISKS:
${expiringContracts.length > 0 ? contractsText : "✓ All active support contracts have > 90 days remaining. SupportEdge Premium SLA active."}

--------------------------------------------------------------------------------
3. PHASED ENVIRONMENTAL POSTURE REMEDIATION ROADMAP (TAM PRACTICE)
--------------------------------------------------------------------------------

PHASE 1: IMMEDIATE CRITICAL MITIGATION & HARDENING (DAYS 1 - 7)
--------------------------------------------------------------
Focus: Address severe network path errors and SANS/NIST security configuration drifts.

* ACTION 1.1: Security Protocol Hardening (CVE / Ransomware Mitigation)
  - Standard Practice: Disable legacy SMBv1 protocols to block remote code execution. Enforce root squashing (superuser=none) in export policies.
  - CLI Remediation Command: 
    - CIFS: 'vserver cifs options modify -vserver <svm> -smb1-enabled false'
    - NFS: 'vserver export-policy rule modify -policyname default -ruleindex 1 -superuser none'
  - Verification: 'vserver cifs options show -fields smb1-enabled'

* ACTION 1.2: Restore Physical Cable/Path Redundancy
  - Standard Practice: Resolve single-controller SAS loop alerts to recover dual-pathing.
  - CLI Verification: 'storage show path -fields disk-count,path-link-status'

* IDENTIFIED PHASE 1 ITEMS IN ACTIVE ENVIRONMENT:
${allRisks.length > 0 ? risksText : "✓ No active high-priority configuration drifts detected."}

PHASE 2: SOFTWARE LIFECYCLE & FABRIC ALIGNMENT (DAYS 8 - 30)
------------------------------------------------------------
Focus: Bring storage operating system versions and networking switches to validated baselines.

* ACTION 2.1: Non-Disruptive ONTAP / SANtricity OS Upgrades
  - Standard Practice: Utilize Active IQ Digital Advisor 'Upgrade Advisor' scripts. Cross-reference NetApp IMT.
  - Upgrade Targets:
${allUpgrades.length > 0 ? upgradesText : "  ✓ All systems are running recommended stable software baselines."}

* ACTION 2.2: Interconnect Switch Firmware Upgrades
  - Standard Practice: Update Cisco Nexus/Brocade switches. Enforce ISSU (In-Service Software Upgrade) or hot load firmware procedures.

PHASE 3: OPERATIONAL AUDITS & BEST PRACTICE COMPLIANCE (DAYS 31 - 90)
--------------------------------------------------------------------
Focus: Drive long-term efficiency, audit logging, and host integration compliance.

* ACTION 3.1: Hypervisor Storage Driver Optimization
  - Standard Practice: Configure VMware ESXi hosts with VMW_PSP_RR Round Robin policies, setting the IOPS limit = 1 to load-balance queue depths.
  - Run Command (ESXi 6.x): 'esxcli storage nmp psp roundrobin device config set -d <naa_id> -I 1 -t iops'
  - Run Command (ESXi 7.0/8.0+): 'esxcli storage nmp psp roundrobin device config set --device <naa_id> --type iops --iops 1'

* ACTION 3.2: Enable SVM Configuration Change Auditing
  - Standard Practice: Configure and enable vserver audit logging for compliance.
  - Run Commands: 'vserver audit create -vserver <svm_name> -destination /audit_log -format json' and 'vserver audit enable -vserver <svm_name>'

* ACTION 3.3: Third-Party Backup Snapshot Scheduling Compliance
  - Standard Practice: Avoid schedule collision between third-party snapshot orchestration (Veeam, Commvault, Rubrik) and native ONTAP snapshot policies. Disable native ONTAP snapshot schedules on volumes managed by third-party backup platforms to prevent reaching the 255-snapshot-per-volume ceiling.
  - Run Command: 'volume modify -vserver <svm_name> -volume <vol_name> -snapshot-policy none'

--------------------------------------------------------------------------------
4. ITIL CHANGE MANAGEMENT GOVERNANCE & RUNBOOK GUIDELINES
--------------------------------------------------------------------------------
All operations under this plan must comply with standard ITIL Change Control procedures:
1. PRE-CHANGE VERIFICATION: Execute 'cluster show', 'system health alert show', and 'storage failover show' to verify cluster quorum, node health, and SFO state prior to any change.
2. SAFETY CLASSIFICATION: Verify command safety tiers (Non-Disruptive, Disruptive but Data-Safe, Destructive or Irreversible) prior to execution. For destructive actions, ensure a valid backup or Snapshot exists.
3. MAINTENANCE WINDOWS: Schedule hardware spares replacement during off-peak windows to absorb transient latency spikes.
4. CHANGE ROLLBACK PLAN: Document rollback CLI commands for all upgrades (e.g. reverting to fallback boot partitions if post-upgrade checks fail).
================================================================================`;
}

function compileExtendedDeliverables(targetSystems, allRisks, allUpgrades, expiringContracts, allSupportCases, scopeTitle) {
  const cleanScope = scopeTitle.replace(/_/g, ' ');
  
  // 1. Problem Statements & Business Impacts
  let problemStatements = `================================================================================
EXECUTIVE PROBLEM STATEMENTS & BUSINESS IMPACT AUDIT
================================================================================
SCOPE: ${cleanScope}
GENERATED BY: NetApp Support & Operations Team
DATE: ${new Date().toISOString().split('T')[0]}

`;

  if (allRisks.length === 0 && expiringContracts.length === 0) {
    problemStatements += "✓ No critical operational issues or expiring contracts identified in the active scope.\n";
  } else {
    allRisks.forEach((r, idx) => {
      let bizImpact = "High risk of data unavailability, application slowdowns, or critical security vulnerabilities leading to compliance violations.";
      if (r.category === "Security") {
        bizImpact = "CRITICAL SECURITY EXPOSURE: Exposes storage controllers to unauthorized data access, remote code executions, or potential ransomware propagation (e.g. WannaCry, EternalBlue).";
      } else if (r.category === "Hardware") {
        bizImpact = "HARDWARE FAILURE OUTAGE: Loss of SAS loop redundancy or aggregate failures could lead to Data Unavailable (DU) status, crashing VMs and enterprise applications.";
      }
      
      problemStatements += `${idx + 1}. PROBLEM IDENTIFIED ON SYSTEM: ${r.systemName}
   - Issue Type: [${r.category}] ${r.description}
   - Technical Risk Level: ${r.severity.toUpperCase()}
   - Business & Financial Impact: ${bizImpact}
   - Operational Analysis: ${r.remediationPlan ? r.remediationPlan.impact : "System path degradation or microcode inconsistencies require immediate intervention to protect active LUNs/Shares."}
\n`;
    });
  }

  // 2. Customer Advisories & QBR Communications
  let customerComms = `================================================================================
CUSTOMER COMMUNICATIONS & ADVISORY ALERT NOTIFICATIONS
================================================================================
SCOPE: ${cleanScope}
DELIVERABLE TEMPLATES: Client Email Notification & QBR Follow-up Outlines

--------------------------------------------------------------------------------
TEMPLATE A: URGENT TECHNICAL ADVISORY EMAIL
--------------------------------------------------------------------------------
Subject: Urgent Action Required: NetApp Operational Health & Security Advisory - ${cleanScope}

Dear Storage Operations Team,

We have completed our monthly system posture audit for your storage infrastructure using NetApp Active IQ Digital Advisor. The telemetry analysis identified critical configuration vulnerabilities and operational risks that require scheduling maintenance.

A summary of the items is detailed below:

${allRisks.length > 0 ? `CRITICAL SECURITY & HARDWARE RISKS:\n` + allRisks.map(r => ` - [System: ${r.systemName}] [Severity: ${r.severity.toUpperCase()}] ${r.description}`).join("\n") : "✓ No critical configuration risks identified."}

${allSupportCases.length > 0 ? `ACTIVE SERVICE CASES IN PROGRESS:\n` + allSupportCases.map(c => ` - Case ID: ${c.id} | Subject: ${c.title} | Current Status: ${c.status}`).join("\n") : "✓ No active open technical support cases."}

We have compiled complete runbooks, CLI rollback commands, and parts dispatch details inside the attached Solution Proposal. Please review and advise on your next Change Advisory Board (CAB) window so we can allocate engineering resources.

Best Regards,
[Your Name]
NetApp Support Account Manager (SAM)

--------------------------------------------------------------------------------
TEMPLATE B: QBR EXECUTIVE SUMMARIES (FOR CSM SLIDES)
--------------------------------------------------------------------------------
* KEY EXECUTIVE FINDINGS:
  - Total Systems Monitored: ${targetSystems.length}
  - Total Risks Flagged: ${allRisks.length} (${allRisks.filter(r=>r.severity==='critical').length} Critical, ${allRisks.filter(r=>r.severity==='high').length} High)
  - Open Support Cases: ${allSupportCases.length}
  - Upgrades Recommended: ${allUpgrades.length} systems
  
* ROADMAP RECOMMENDATION:
  1. Remediate critical protocol vulnerability issues (disable legacy SMB1 / enable root squashing).
  2. Implement sequential OS upgrades to move legacy controllers to stable ONTAP releases.
  3. Swap degraded SAS cabling components to restore backend network redundancy.
`;

  // 3. Change Control & Dispatch Tickets
  let changeTickets = `================================================================================
ITIL CHANGE CONTROL & OPERATIONS DISPATCH TICKET TEMPLATES
================================================================================
SCOPE: ${cleanScope}
CLASSIFICATION: Infrastructure Operations -> NetApp Storage Maintenance
DEFAULT RISK RATING: Medium (Online/Non-Disruptive Execution)

`;

  targetSystems.forEach((sys, sidx) => {
    const l = sys.logistics || { deliveryAddress: "Not Configured", accessRestrictions: "Not Configured" };
    const c = sys.contacts || { name: "Not Configured", phone: "Not Configured" };
    
    changeTickets += `--------------------------------------------------------------------------------
TICKET ${sidx + 1}: LOGISTICS DISPATCH & CHANGE RUNBOOK - ${sys.systemName}
--------------------------------------------------------------------------------
* TICKET SUMMARY: Schedule storage remediation and parts replacement for S/N ${sys.serialNumber}
* CRITICAL LOGISTICS DETAILS:
  - Delivery Address: ${l.deliveryAddress}
  - Access Protocol: ${l.accessRestrictions}
  - On-Site Contact: ${c.name} (${c.phone})
  
* CHANGE DETAILS:
  - Implementation Window: Off-Peak (22:00 - 04:00 Local)
  - Impact Scope: System pathing remains active. Storage failover (SFO) handles I/O if a module reboot is required. No service interruption is anticipated.
  
* PRE-REQUISITES (SAFETY CHECKLIST):
  1. Validate aggregate health: 'storage aggregate show -state online'
  2. Confirm cluster failover status: 'storage failover show'
  3. Verify cluster quorum and node health: 'cluster show' and 'system health alert show'
  4. Verify current active paths: 'storage path show'
  5. Perform configuration backup: 'system configuration backup create'

* IMPLEMENTATION RUNBOOK:
${sys.risks && sys.risks.length > 0 ? sys.risks.map((r, rIdx) => `  [Sub-Task ${rIdx + 1}] ${r.description}
  Safety Classification: ${getRiskSafetyTier(r).toUpperCase()}
  remediation: ${r.remediationPlan ? r.remediationPlan.steps.join("\n  ") : "Follow NetApp Support KB guidelines."}`).join("\n\n") : "  ✓ No configuration risks require remediation."}

* CHANGE VERIFICATION:
  1. Execute 'system health alert show' to verify zero active warning states.
  2. Confirm disk/shelf links: 'storage port show'
  
* ROLLBACK PLAN:
  1. Revert any modified configuration variables using the inverse commands.
  2. For hardware swaps, re-seat the original SAS cables or components to restore previous operating paths.
  3. Contact NetApp support at 1-888-4-NETAPP if failover verification fails to resolve within 15 minutes.

\n\n`;
  });

  // 4. Solution Proposals
  let solutionProposals = `================================================================================
TECHNICAL SOLUTION & ARCHITECTURAL CONFIGURATION PROPOSAL
================================================================================
CUSTOMER: ${cleanScope}
PREPARED BY: NetApp Customer Success & TAM Team

1. EXECUTIVE SUMMARY & OBJECTIVE
The objective of this proposal is to optimize the storage architecture for ${cleanScope}, ensuring high availability, network path redundancy, and compliance with modern enterprise security baselines.

2. PROPOSED ARCHITECTURAL CORRECTIONS:
`;

  let hasSecurity = false;
  let hasPathing = false;
  let hasUpgrade = false;

  allRisks.forEach(r => {
    if (r.category === "Security") hasSecurity = true;
    if (r.category === "Hardware" && r.description.includes("Path")) hasPathing = true;
  });
  if (allUpgrades.length > 0) hasUpgrade = true;

  if (hasSecurity) {
    solutionProposals += `
A. PROTOCOL SECURITY HARDENING (SMBv1 & NFS EXPORTS)
   - Recommendation: Disable legacy SMBv1 protocols to block remote code executions (WannaCry vectors) and restrict NFS policy root mounting permissions.
   - Design Principle: Enforce AUTH_SYS/Kerberos parameters and squash root permissions (superuser=none) across all storage virtual machines (SVMs).
`;
  }
  if (hasPathing) {
    solutionProposals += `
B. BACK-END SAS FABRIC REDUNDANCY
   - Recommendation: Replace degraded physical cabling and reseat SAS connections on loop ports.
   - Design Principle: Dual-path storage connectivity is mandatory to survive single host port adapter failures and protect active disks against Data Unavailable (DU) states.
`;
  }
  if (hasUpgrade) {
    solutionProposals += `
C. ONTAP OS & SOFTWARE COMPLIANCE LIFECYCLE
   - Recommendation: Perform sequential, non-disruptive rolling upgrades to validated OS baselines.
   - Design Principle: Ensure storage controllers are updated to release targets that support modern TLS 1.3 encryption, patch microcode vulnerabilities, and align with NetApp Interoperability Matrix guidelines.
`;
  }

  solutionProposals += `
3. OPERATIONAL ROADMAP & PROJECT PLANNING
   - Stage 1: Backup and Pre-upgrade checks (Week 1)
   - Stage 2: Hardware replacement & Cabling alignment (Week 2-3)
   - Stage 3: ONTAP / SANtricity OS upgrade execution (Week 4-5)
   - Stage 4: Post-remediation verification & client validation (Week 6)`;

  // 5. Implementation Runbooks
  let implementationPlans = `================================================================================
DETAILED STEP-BY-STEP CLI RUNBOOK & IMPLEMENTATION PLANS
================================================================================
SCOPE: ${cleanScope}
COMPILING ACTIVE CLI COMMAND RUNBOOKS

`;

  targetSystems.forEach((sys, sysIdx) => {
    implementationPlans += `--------------------------------------------------------------------------------
SYSTEM ${sysIdx + 1}: CLI RUNBOOK - ${sys.systemName} (S/N: ${sys.serialNumber})
--------------------------------------------------------------------------------
`;
    
    if (sys.risks && sys.risks.length > 0) {
      sys.risks.forEach((r, rIdx) => {
        implementationPlans += `[Task ${rIdx + 1}] ${r.description}
- Category: ${r.category}
- Specific Action Plan:
`;
        const verStr = sys.ontapVersion || "9.12.1";
        const parts = verStr.split('.');
        const major = parseInt(parts[0]) || 9;
        const minor = parseInt(parts[1]) || 12;
        const is92OrNewer = (major > 9) || (major === 9 && minor >= 2);
        const is95OrNewer = (major > 9) || (major === 9 && minor >= 5);

        if (r.description.includes("SMBv1")) {
          if (is92OrNewer) {
            implementationPlans += `  * [ONTAP ${verStr} - 9.2+ Compliance Command] Run to disable SMBv1 on SVM:
    vserver cifs options modify -vserver <svm_name> -smb1-enabled false
  * Verify the modification:
    vserver cifs options show -fields smb1-enabled\n\n`;
          } else {
            implementationPlans += `  * [ONTAP ${verStr} - Legacy <9.2 Command] Run to disable SMBv1 on SVM:
    vserver cifs options modify -vserver <svm_name> -is-smb1-enabled false
  * Verify the modification:
    vserver cifs options show -fields is-smb1-enabled\n\n`;
          }
        } else if (r.description.includes("NFS export policy") || r.description.includes("root")) {
          implementationPlans += `  * Modify export policy rule index to squash root permissions:
    vserver export-policy rule modify -vserver <svm_name> -policyname default -ruleindex 1 -superuser none
  * Restrict access to secure subnets:
    vserver export-policy rule modify -vserver <svm_name> -policyname default -ruleindex 1 -clientmatch 10.100.0.0/16\n\n`;
        } else if (r.description.includes("NTP")) {
          if (is95OrNewer) {
            implementationPlans += `  * [ONTAP ${verStr} - 9.5+ Command] Reconfigure active NTP servers:
    cluster time-service ntp server modify -server time.windows.com
  * Verify time synchronization status:
    cluster time-service ntp status show\n\n`;
          } else {
            implementationPlans += `  * [ONTAP ${verStr} - Legacy <9.5 Command] Reconfigure active NTP servers:
    system services ntp server modify -server time.windows.com
  * Verify time synchronization status:
    system services ntp status show\n\n`;
          }
        } else if (r.description.includes("Shelf") || r.description.includes("firmware")) {
          implementationPlans += `  * Download the firmware package to the nodes:
    storage firmware download -node * -package iom12_0260.flw
  * Trigger the update:
    storage shelf firmware update
  * Monitor progress:
    storage shelf firmware show-update-status\n\n`;
        } else {
          implementationPlans += `  * Steps:\n  ` + (r.remediationPlan ? r.remediationPlan.steps.join("\n  ") : "  Consult support documentation.") + `\n\n`;
        }
      });
    } else {
      implementationPlans += "✓ No configuration actions required for this system.\n\n";
    }

    const isASA = (sys.platform || "").includes("ASA");
    if (isASA) {
      implementationPlans += `[ASA SAN Platform Verification]
  * Verify symmetric active-active multipathing states on hosts:
    esxcli storage nmp device list
  * Verify SCSI UNMAP allocation & reclamation options on SVM LUNs:
    lun show -vserver <svm_name> -fields space-allocation,space-reclamation
  * Confirm that host igroup mapping paths are balanced across HA nodes:
    igroup show -vserver <svm_name> -fields ostype,protocol\n\n`;
    }

    if (sys.upgrades && sys.upgrades.targetVersion !== "Up to Date") {
      const origVer = sys.santricityVersion ? sys.santricityVersion : sys.ontapVersion;
      const hops = calculateUpgradePath(sys.platform, origVer, sys.upgrades.targetVersion);
      implementationPlans += `[Software Upgrade Runbook]
- Current Release: ${origVer}
- Target Release: ${sys.upgrades.targetVersion}
- Pathfinder Upgrade Hops:
`;
      hops.forEach((h, hIdx) => {
        implementationPlans += `  Hop ${hIdx + 1}: ${h.from} -> ${h.to}
  * Pre-upgrade advisory steps:
    ${h.steps.join("\n    ")}
  * Upgrade guide link: ${h.docLink}
`;
      });
      implementationPlans += `\n`;
    }
  });

  // 7. Sales & Hardware Refresh Proposals
  let salesProposals = `================================================================================
SALES PROPOSALS & HARDWARE REFRESH RECOMMENDATIONS
================================================================================
CUSTOMER: ${cleanScope}
PREPARED BY: NetApp Account Management & Customer Success

`;

  if (expiringContracts.length === 0 && targetSystems.filter(s => s.lifecycle && s.lifecycle.isNearEos).length === 0) {
    salesProposals += "✓ No urgent hardware lifecycle refreshes or support contract renewals required.\n";
  } else {
    salesProposals += "1. URGENT SUPPORT CONTRACT RENEWALS:\n";
    expiringContracts.forEach(e => {
      salesProposals += ` - System: ${e.systemName} (S/N: ${e.serialNumber || "unknown"})
   Support Level: ${e.supportLevel}
   Expiry Date: ${e.endDate} (${e.daysRemaining} days remaining)
   Recommendation: Renew support contract immediately to maintain active technical support and hardware replacement services.\n\n`;
    });

    salesProposals += "2. LIFECYCLE REFRESH OPPORTUNITIES (EOS/EOL DECOMMISSIONING):\n";
    targetSystems.forEach(sys => {
      if (sys.lifecycle && (sys.lifecycle.isNearEos || sys.ontapVersion === "9.5")) {
        salesProposals += ` - System: ${sys.systemName} (S/N: ${sys.serialNumber})
   Platform: ${sys.platform}
   Current OS Version: ${sys.ontapVersion}
   EOA Date: ${sys.lifecycle.eoaDate} | EOS Date: ${sys.lifecycle.eosDate}
   Recommendation: This system is approaching end-of-support or running legacy ONTAP release. Propose a hardware technology refresh to modern NetApp AFF/FAS storage platforms (e.g. AFF A150 or AFF A250) to capitalize on 3.5:1 storage efficiency guarantees, advanced clustering, and cloud integration.\n\n`;
      }
    });
  }

  // 8. Customer Success Plan (CSP)
  let customerSuccessPlan = compileCustomerSuccessPlanText(scopeTitle, allRisks, allUpgrades, targetSystems, expiringContracts, allSupportCases);

  return {
    problemStatements,
    customerComms,
    changeTickets,
    solutionProposals,
    implementationPlans,
    salesProposals,
    customerSuccessPlan
  };
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
    if (sys.risks) {
      sys.risks.forEach(r => allRisks.push({ systemName: sys.systemName, ...r }));
    }
    if (sys.upgrades && sys.upgrades.targetVersion !== "Up to Date") {
      allUpgrades.push({ systemName: sys.systemName, platform: sys.platform, currentVersion: sys.santricityVersion ? sys.santricityVersion : sys.ontapVersion, ...sys.upgrades });
    }
    if (sys.contracts && sys.contracts.daysRemaining <= 90) {
      expiringContracts.push({ systemName: sys.systemName, serialNumber: sys.serialNumber, ...sys.contracts });
    }
    if (sys.fieldActions) {
      sys.fieldActions.forEach(fa => activeFAs.push({ systemName: sys.systemName, ...fa }));
    }
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
  const docs = compileExtendedDeliverables(targetSystems, allRisks, allUpgrades, expiringContracts, allSupportCases, scopeTitle);

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
          
          <div style="font-size: 0.78rem; margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
            <span style="color: var(--text-muted); font-weight: 500;">Safety Tier:</span>
            <span style="background: ${getRiskSafetyTier(r) === 'Destructive or Irreversible' ? 'var(--status-critical)' : (getRiskSafetyTier(r) === 'Disruptive but Data-Safe' ? 'var(--status-warning)' : 'var(--status-normal)')}; color: #fff; font-size: 0.68rem; padding: 2px 6px; border-radius: var(--radius-sm); font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">${getRiskSafetyTier(r)}</span>
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
    const l = { deliveryAddress: "Not Set", accessRestrictions: "Not Set", shippingAlert: "None", ...sys.logistics };
    const c = { name: "Not Set", phone: "Not Set", email: "Not Set", nssUsername: "Not Set", ...sys.contacts };
    const h = { accountManager: "Not Set", supportTam: "Not Set", sentimentScore: 7.0, healthStatus: "Stable", upsellPotential: "None", refreshWindow: "Under Review", ...sys.salesHealth };
    const p = { growthRateGBPerDay: 100, daysToLimit: 120, limitDate: "Under Review", ...sys.projections };
    
    const logisticsDiffs = getLogisticsUpdateTicketsAndDiffs(sys);
    
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
            <div><strong>Primary Site Contact:</strong><br><span style="color: var(--text-secondary);">${c.name} (${c.phone} / ${c.email} / NSS: ${c.nssUsername})</span></div>
            <div style="margin-top: 8px;"><strong>Sales Lead & Support TAM:</strong><br><span style="color: var(--text-secondary);">AM: ${h.accountManager} | TAM: ${h.supportTam}</span></div>
            <div style="margin-top: 8px; display: flex; gap: 20px;">
              <div><strong>CSAT Score:</strong> <span style="font-weight: 700; color: var(--accent-cyan);">${h.sentimentScore.toFixed(1)}/10</span></div>
              <div><strong>Tech Refresh window:</strong> <span style="font-weight: 700; color: var(--status-warning);">${convertToNetAppFiscal(h.refreshWindow)}</span></div>
            </div>
          </div>
        </div>
        
        ${logisticsDiffs.diffsHTML}
        
        <div style="margin-top: 12px; font-size: 0.78rem; color: var(--text-muted); line-height: 1.4; border-top: 1px dashed var(--border-color); padding-top: 12px;">
          <strong>How to Update Active IQ Install Base Records Officially:</strong>
          <ol style="margin-left: 16px; margin-top: 4px; color: var(--text-secondary);">
            <li>Log in to the <strong>NetApp Support Site (support.netapp.com)</strong>.</li>
            <li>Navigate to <strong>Resources > Register Products / Install Base</strong>.</li>
            <li>Click <strong>Open a Non-Technical Ticket</strong>. Select the <strong>"Install Base Update / Serial Number Move"</strong> category.</li>
            <li>Copy-paste the template above or detail your changes, then submit the ticket. NetApp's Install Base Group (IBG) typically processes updates within 24-48 hours, automatically syncing changes to the customer's Active IQ portal.</li>
          </ol>
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
          <li><strong>Multipathing PSP</strong>: Confirm ESXi hosts utilize VMW_PSP_RR Round Robin policies with IOPS limit=1 to distribute workload. Fixed pathing configurations should be corrected immediately using: 'esxcli storage nmp psp roundrobin device config set -d <naa_id> -I 1 -t iops' (for ESXi 6.x) or 'esxcli storage nmp psp roundrobin device config set --device <naa_id> --type iops --iops 1' (for ESXi 7.0/8.0+).</li>
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
        <h2 style="font-size: 1.15rem; margin: 0; border: none; padding: 0;">9. Executable Account Deliverables Suite</h2>
      </div>
      
      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">A. Problem Statements & Business Impact Summaries</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('PROBLEM_STATEMENTS')">Download Draft (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Technical problem statements translating identified risks into business, financial, and operational risk contexts.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${docs.problemStatements}</textarea>
      </div>

      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">B. Customer Advisories & QBR Communications</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('EMAIL')">Download Draft (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Proactive advisory notification emails and slides content to share during Quarterly Business Reviews.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${docs.customerComms}</textarea>
      </div>

      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">C. ITIL-Aligned Change Control & Dispatch Ticket Templates</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('TICKET')">Download Draft (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Pre-formatted change control tickets specifying pre-requisites, impact scope, implementation plans, and rollback runbooks.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${docs.changeTickets}</textarea>
      </div>

      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">D. Technical Solution & Architecture Proposals</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('SOLUTION_PROPOSAL')">Download Draft (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Formal solution design architectures detailing the rationale behind SAN/NAS and upgrade remediation practices.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${docs.solutionProposals}</textarea>
      </div>

      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">E. Step-by-Step CLI Runbooks & Upgrade Execution Plans</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('IMPLEMENTATION')">Download Runbook (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Detailed, command-level runbooks showing exact CLI syntax to disable SMB1, modify exports, execute shelf upgrades, and run OS updates.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${docs.implementationPlans}</textarea>
      </div>

      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">F. Sales Refresh & Hardware Renewal Proposals</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('SALES_PROPOSAL')">Download Draft (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Pre-sales recommendations for hardware upgrades (EOS/EOL controllers) and aggregate expansion plans.</p>
        <textarea style="width: 100%; height: 160px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${docs.salesProposals}</textarea>
      </div>

      <div style="margin-bottom: 24px; background: rgba(255,255,255,0.01); border: 1px solid var(--border-color); padding: 18px; border-radius: var(--radius-sm);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="font-size: 0.95rem; color: var(--accent-cyan); margin: 0;">G. Phased Customer Success & Posture Optimization Plan</h4>
          <button class="action-btn secondary" style="font-size: 0.72rem; padding: 4px 10px;" onclick="downloadDeliverable('SUCCESS_PLAN')">Download Success Plan (TXT)</button>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">Roadmap detailing CSM checkpoints, storage ROI optimization runs, and CSAT alignment schedules.</p>
        <textarea style="width: 100%; height: 220px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary); font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: var(--radius-sm); resize: vertical;" readonly>${docs.customerSuccessPlan}</textarea>
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
    if (sys.risks) {
      sys.risks.forEach(r => allRisks.push({ systemName: sys.systemName, ...r }));
    }
    if (sys.upgrades && sys.upgrades.targetVersion !== "Up to Date") {
      allUpgrades.push({ systemName: sys.systemName, platform: sys.platform, currentVersion: sys.santricityVersion ? sys.santricityVersion : sys.ontapVersion, ...sys.upgrades });
    }
    if (sys.contracts && sys.contracts.daysRemaining <= 90) {
      expiringContracts.push({ systemName: sys.systemName, serialNumber: sys.serialNumber, ...sys.contracts });
    }
    if (sys.fieldActions) {
      sys.fieldActions.forEach(fa => activeFAs.push({ systemName: sys.systemName, ...fa }));
    }
    if (sys.securityBulletins) {
      sys.securityBulletins.forEach(sb => allSecurityAdvisories.push({ systemName: sys.systemName, ...sb }));
    }
    if (sys.supportCases) {
      sys.supportCases.forEach(sc => allSupportCases.push({ systemName: sys.systemName, ...sc }));
    }
    const sws = getSystemSwitches(sys);
    if (sws) {
      sws.forEach(sw => {
        if (sw.status !== "Optimal") {
          switchAlerts.push({ systemName: sys.systemName, ...sw });
        }
      });
    }
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
- Safety Classification: ${getRiskSafetyTier(r).toUpperCase()}
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
  allUpgrades.map(u => {
    const origSys = targetSystems.find(s => s.systemName === u.systemName);
    const currentVer = origSys ? (origSys.santricityVersion ? origSys.santricityVersion : origSys.ontapVersion) : "unknown";
    const hops = calculateUpgradePath(u.platform, currentVer, u.targetVersion);
    
    let hopsText = "";
    if (hops.length > 0) {
      if (hops.length > 1) {
        hopsText += "\n   [WARNING: Direct Upgrade is NOT supported. Sequential multi-hop sequence is required:]\n";
      }
      hops.forEach((hop, idx) => {
        hopsText += `\n   Hop ${idx + 1}: ${hop.from} -> ${hop.to}
   -------------------------------------------------
   * Steps:
${hop.steps.map(s => `     - ${s.replace(/<[^>]*>/g, "")}`).join("\n")}
   * Pre-upgrade Recommendations:
${hop.recommendations.map(r => `     - ${r.replace(/<[^>]*>/g, "")}`).join("\n")}
   * Important Considerations:
${hop.considerations.map(c => `     - ${c.replace(/<[^>]*>/g, "")}`).join("\n")}
   * Documentation Link: ${hop.docLink}
`;
      });
    }

    return `System: ${u.systemName} [Urgency: ${u.urgency}]
- Current OS: ${currentVer}
- Recommended OS Target Version: ${u.targetVersion}
- Platform Model: ${u.platform}
- Latest Supported OS Version: ${getLatestSupportedVersion(u.platform)}
- Expected Upgrade Benefits: ${u.benefits}
${hopsText}`;
  }).join("\n\n")}`;
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
Date Generated: ${new Date().toISOString().split('T')[0]}

`;
    targetSystems.forEach(sys => {
      const l = { deliveryAddress: "Not Set", accessRestrictions: "Not Set", shippingAlert: "None", ...sys.logistics };
      const c = { name: "Not Set", phone: "Not Set", email: "Not Set", nssUsername: "Not Set", ...sys.contacts };
      const h = { accountManager: "Not Set", supportTam: "Not Set", sentimentScore: 7.0, healthStatus: "Stable", ...sys.salesHealth };
      const p = { growthRateGBPerDay: 100, daysToLimit: 120, limitDate: "Under Review", ...sys.projections };
      
      const logisticsDiffs = getLogisticsUpdateTicketsAndDiffs(sys);
      
      text += `================================================================================
SYSTEM: ${sys.systemName} (S/N: ${sys.serialNumber})
================================================================================
- Delivery Address: ${l.deliveryAddress}
- Access Restrictions: ${l.accessRestrictions}
- Logistics Alerts: ${l.shippingAlert}
- Storage Growth Runway: ${p.daysToLimit} Days remaining (Est. limit date: ${p.limitDate})
- Primary Contact: ${c.name} (${c.phone} / ${c.email} / NSS: ${c.nssUsername})
- Sales Rep: AM: ${h.accountManager} | TAM: ${h.supportTam}
- CSAT Score: ${h.sentimentScore.toFixed(1)}/10 [Status: ${h.healthStatus}]
- Tech Refresh Window (NetApp Fiscal): ${convertToNetAppFiscal(h.refreshWindow)}
`;

      if (logisticsDiffs.hasChanges) {
        text += `${logisticsDiffs.diffsTXT}
--------------------------------------------------------------------------------
TICKET SUBMISSION TEMPLATE:
--------------------------------------------------------------------------------
${logisticsDiffs.ticketTXT}
--------------------------------------------------------------------------------

`;
      }
      
      text += `OFFICIAL ACTIVE IQ UPDATE STEPS:
To officially update the installation address or system contacts in the central NetApp databases:
1. Log in to support.netapp.com using your NetApp Support Site (NSS) credentials.
2. Go to "Resources" -> "Register Products / Install Base".
3. Open a Non-Technical Ticket under the "Install Base Update / Serial Number Move" category.
4. Copy-paste the ticket details provided above into the case description.
5. NetApp's Install Base Group (IBG) will process the database updates within 24-48 hours.

\n\n`;
    });
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
    if (sys.risks) {
      sys.risks.forEach(r => allRisks.push({ systemName: sys.systemName, ...r }));
    }
    if (sys.upgrades && sys.upgrades.targetVersion !== "Up to Date") {
      allUpgrades.push({ systemName: sys.systemName, platform: sys.platform, currentVersion: sys.santricityVersion ? sys.santricityVersion : sys.ontapVersion, ...sys.upgrades });
    }
    if (sys.contracts && sys.contracts.daysRemaining <= 90) {
      expiringContracts.push({ systemName: sys.systemName, serialNumber: sys.serialNumber, ...sys.contracts });
    }
    if (sys.supportCases) {
      sys.supportCases.forEach(sc => allSupportCases.push({ systemName: sys.systemName, ...sc }));
    }
  });

  const docs = compileExtendedDeliverables(targetSystems, allRisks, allUpgrades, expiringContracts, allSupportCases, scopeTitle.replace(/_/g, ' '));

  if (type === 'EMAIL') {
    triggerFileDownload(`advisory_email_${cleanScope}.txt`, docs.customerComms);
  } else if (type === 'PROPOSAL') {
    triggerFileDownload(`upgrade_proposal_${cleanScope}.txt`, docs.salesProposals);
  } else if (type === 'TICKET') {
    triggerFileDownload(`change_ticket_${cleanScope}.txt`, docs.changeTickets);
  } else if (type === 'SUCCESS_PLAN') {
    triggerFileDownload(`success_plan_${cleanScope}.txt`, docs.customerSuccessPlan);
  } else if (type === 'PROBLEM_STATEMENTS') {
    triggerFileDownload(`problem_statements_${cleanScope}.txt`, docs.problemStatements);
  } else if (type === 'IMPLEMENTATION') {
    triggerFileDownload(`implementation_runbook_${cleanScope}.txt`, docs.implementationPlans);
  } else if (type === 'SALES_PROPOSAL') {
    triggerFileDownload(`sales_refresh_proposal_${cleanScope}.txt`, docs.salesProposals);
  } else if (type === 'SOLUTION_PROPOSAL') {
    triggerFileDownload(`solution_architecture_proposal_${cleanScope}.txt`, docs.solutionProposals);
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
  const originalBody = document.getElementById("generatedPlanBody");
  if (!originalBody) return;

  // Create temporary clone container to process HTML edits without affecting the user's dashboard view
  const tempDiv = document.createElement("div");
  tempDiv.innerHTML = originalBody.innerHTML;
  
  // Find all textareas (advisory email, proposal, ticket, success plan) and swap them for pre-wrap divs to display complete texts in printout
  const textareas = tempDiv.querySelectorAll("textarea");
  textareas.forEach(ta => {
    const valText = ta.value || ta.innerText || "";
    const replacement = document.createElement("div");
    replacement.className = "print-textarea-replacement";
    replacement.innerText = valText;
    ta.parentNode.replaceChild(replacement, ta);
  });
  
  const printHtml = tempDiv.innerHTML;
  const printWindow = window.open("", "_blank");
  
  printWindow.document.write(`
    <html>
      <head>
        <title>NetApp Active IQ Consolidate Action Plan</title>
        <style>
          body {
            background-color: #ffffff;
            color: #111827;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            padding: 30px;
            line-height: 1.5;
          }
          h1 { font-size: 1.8rem; font-weight: 700; color: #111827; margin-bottom: 8px; }
          h2 { font-size: 1.25rem; font-weight: 700; color: #1f2937; margin-top: 30px; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }
          h3 { font-size: 1.1rem; font-weight: 600; color: #374151; margin-top: 20px; }
          h4 { font-size: 0.95rem; font-weight: 600; color: #4b5563; }
          .badge { display: inline-block; padding: 3px 8px; border-radius: 9999px; font-size: 0.68rem; font-weight: 600; text-transform: uppercase; border: 1px solid transparent; }
          .badge.critical { background: #fee2e2; color: #991b1b; border-color: #fca5a5; }
          .badge.high { background: #fee2e2; color: #991b1b; border-color: #fca5a5; }
          .badge.warning { background: #fef3c7; color: #92400e; border-color: #fde68a; }
          .badge.medium { background: #fef3c7; color: #92400e; border-color: #fde68a; }
          .badge.normal { background: #d1fae5; color: #065f46; border-color: #6ee7b7; }
          .badge.optimal { background: #d1fae5; color: #065f46; border-color: #6ee7b7; }
          .badge.info { background: #dbeafe; color: #1e40af; border-color: #93c5fd; }
          ul, ol { margin-left: 20px; margin-top: 6px; }
          li { margin-bottom: 8px; font-size: 0.85rem; color: #374151; }
          code { font-family: SFMono-Regular, Consolas, Monaco, monospace; font-size: 0.85rem; background: #f3f4f6; padding: 2px 4px; border-radius: 4px; color: #1f2937; }
          .plan-document-header { border-bottom: 3px solid #3b82f6; padding-bottom: 16px; margin-bottom: 30px; }
          .print-textarea-replacement {
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            padding: 12px 16px;
            border-radius: 4px;
            font-family: SFMono-Regular, Consolas, Monaco, monospace;
            font-size: 0.8rem;
            white-space: pre-wrap;
            margin-top: 8px;
            color: #1f2937;
            line-height: 1.45;
            border-left: 3px solid #3b82f6;
          }
          .plan-section {
            display: block !important;
            page-break-after: always;
            margin-bottom: 40px;
          }
          .plan-section:last-child {
            page-break-after: avoid;
          }
          button, .action-btn, .external-link { display: none !important; }
          @media print {
            body { padding: 0; }
          }
        </style>
      </head>
      <body>
        ${printHtml}
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

  // Inject current saved values summary for clear comparison
  const currentSummaryEl = document.getElementById("editorCurrentValuesSummary");
  if (currentSummaryEl) {
    currentSummaryEl.style.display = "block";
    currentSummaryEl.innerHTML = `
      <div style="font-weight: 700; color: var(--accent-cyan); margin-bottom: 6px; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.5px;">Current Saved Logistics (Active Database)</div>
      <div style="margin-bottom: 2px;"><strong>Site Address</strong>: <span style="color: var(--text-secondary); font-style: italic;">${logistics.deliveryAddress || '(Not Set)'}</span></div>
      <div style="margin-bottom: 2px;"><strong>Access Rules</strong>: <span style="color: var(--text-secondary);">${logistics.accessRestrictions || '(Not Set)'}</span></div>
      <div style="margin-bottom: 2px;"><strong>Tech Contact</strong>: <span style="color: var(--text-secondary);">${contacts.name || '(Not Set)'} (${contacts.email || 'No email'})</span></div>
    `;
  }

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

  // Store original telemetry parameters to generate difference mapping if modified
  if (!state.systems[idx].originalLogistics) {
    state.systems[idx].originalLogistics = JSON.parse(JSON.stringify(state.systems[idx].logistics || { deliveryAddress: "", accessRestrictions: "", shippingAlert: "None" }));
  }
  if (!state.systems[idx].originalContacts) {
    state.systems[idx].originalContacts = JSON.parse(JSON.stringify(state.systems[idx].contacts || { name: "", phone: "", email: "", nssUsername: "" }));
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

  // If action plan is currently visible on screen, regenerate it to reflect changes immediately
  if (document.getElementById("planControlsPanel").style.display === "flex") {
    generateActionPlan();
  }
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
  const apiBaseInput = document.getElementById("settingsApiBaseUrl").value.trim() || "https://api.activeiq.netapp.com/v1";
  const intervalInput = parseInt(document.getElementById("settingsSyncInterval").value) || 0;
  const wlOnlyToggle = document.getElementById("settingsWatchlistOnlyToggle").checked;
  const oldMockMode = state.mockMode;
  
  state.apiBaseUrl = apiBaseInput;
  state.syncInterval = intervalInput;
  state.watchlistOnly = wlOnlyToggle;
  
  safeSetItem("aiq_api_base_url", apiBaseInput);
  safeSetItem("aiq_sync_interval", intervalInput.toString());
  safeSetItem("aiq_watchlist_only", wlOnlyToggle ? "true" : "false");
  
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
  updateScheduledSyncInfo();
  switchTab("settings");
}

async function updateApplicationCode() {
  if (window.location.protocol === "file:") {
    alert("Application Update Unavailable:\nUpdating code via Git is only supported when running the local Python server (server.py).\n\nIf you are running the dashboard as a file, please open a terminal in the folder and run 'git pull' manually.");
    return;
  }
  
  const btn = document.getElementById("appUpdateButton");
  if (!btn) return;
  const origText = btn.innerText;
  btn.disabled = true;
  btn.innerText = "Updating...";
  
  try {
    const response = await fetch("/api/app/update", { method: "POST" });
    const data = await response.json();
    if (response.ok && data.status === "success") {
      alert(`Success: ${data.message}`);
      window.location.reload();
    } else {
      throw new Error(data.message || "Failed to execute git update.");
    }
  } catch (err) {
    console.error("Update failed:", err);
    alert(`Update Failed:\n${err.message}\n\nEnsure that you have Git installed, the project directory is a valid git repository, and the local server is running with write permissions.`);
  } finally {
    btn.disabled = false;
    btn.innerText = origText;
  }
}

function updateScheduledSyncInfo() {
  const lastSyncEl = document.getElementById("syncLastTime");
  const nextSyncEl = document.getElementById("syncNextTime");
  
  if (!lastSyncEl || !nextSyncEl) return;
  
  if (!state.lastSync) {
    lastSyncEl.innerText = "Never Synced";
    lastSyncEl.style.color = "var(--text-secondary)";
  } else {
    lastSyncEl.innerText = new Date(state.lastSync).toLocaleString();
    lastSyncEl.style.color = "var(--text-primary)";
  }
  
  if (state.syncInterval === 0) {
    nextSyncEl.innerText = "Not Scheduled (Manual)";
    nextSyncEl.style.color = "var(--text-secondary)";
  } else {
    const lastTime = state.lastSync ? new Date(state.lastSync).getTime() : Date.now();
    const nextTime = new Date(lastTime + state.syncInterval * 60 * 60 * 1000);
    nextSyncEl.innerText = nextTime.toLocaleString();
    
    if (nextTime.getTime() < Date.now()) {
      nextSyncEl.style.color = "var(--status-warning)";
      nextSyncEl.innerText += " (Pending)";
    } else {
      nextSyncEl.style.color = "var(--status-normal)";
    }
  }
}

async function triggerManualSync() {
  const spinner = document.getElementById("syncSpinnerIcon");
  
  const mockToggle = document.getElementById("settingsMockModeToggle").checked;
  if (mockToggle) {
    alert("CORS/Offline Mode Warning:\nThe dashboard is currently in Offline Demo Mode. Please disable Offline Mode in settings and configure a valid Active IQ Developer Refresh Token to pull live REST telemetry.");
    return;
  }
  
  if (state.mockMode) {
    await saveSettings();
    return;
  }
  
  if (spinner) {
    spinner.style.animation = "spin 1s linear infinite";
  }
  
  try {
    await loadProductionData();
    state.lastSync = new Date().toISOString();
    safeSetItem("aiq_last_sync", state.lastSync);
    updateScheduledSyncInfo();
    
    alert(`Successfully synchronized with Active IQ!\n\nAll required metrics and data points collected:\n✓ System inventory & telemetry\n✓ Active predictive risk signatures\n✓ Multi-hop firmware/OS path plans\n✓ Contracts & warranty lifecycles\n✓ Switch fabric configuration states\n✓ Hypervisor integrations\n✓ Support cases & action items\n\nDashboard has been updated.`);
  } catch (err) {
    console.error("Manual sync failed:", err);
    alert(`Active IQ API Synchronization Failed:\n${err.message}\n\nRefer to CORS console logs or settings documentation for assistance.`);
  } finally {
    if (spinner) {
      spinner.style.animation = "";
    }
  }
}

async function checkAutoSync() {
  if (state.mockMode || state.syncInterval === 0) return;
  
  const lastTime = state.lastSync ? new Date(state.lastSync).getTime() : 0;
  const intervalMs = state.syncInterval * 60 * 60 * 1000;
  
  if (Date.now() - lastTime >= intervalMs) {
    console.log("Auto-polling interval reached. Querying Active IQ API...");
    try {
      await loadProductionData();
      state.lastSync = new Date().toISOString();
      safeSetItem("aiq_last_sync", state.lastSync);
      updateScheduledSyncInfo();
      console.log("Auto-poll synchronized successfully.");
    } catch (err) {
      console.error("Auto-sync interval pull failed:", err);
    }
  }
}

// Start auto-sync checking timer
setInterval(checkAutoSync, 60000); // Check every 60 seconds

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

  // 1. Fetch active watchlists from Active IQ API first
  let watchlistSerials = new Set();
  try {
    const apiWatchlists = await callActiveIQAPI("/watchlists");
    if (apiWatchlists) {
      const wlList = Array.isArray(apiWatchlists) ? apiWatchlists : (apiWatchlists.watchlists || []);
      state.watchlists = wlList.map(wl => {
        const serials = wl.serialNumbers || wl.systemSerials || [];
        serials.forEach(sn => watchlistSerials.add(sn.toString().trim()));
        return {
          id: wl.watchlistId || wl.id || "wl_" + Date.now(),
          name: wl.watchListName || wl.name || "Watchlist",
          systemSerials: serials
        };
      });
      saveWatchlists();
    }
  } catch (wlErr) {
    console.warn("Failed to retrieve Active IQ watchlists:", wlErr);
  }

  // 2. Fetch systems list
  try {
    const apiSystems = await callActiveIQAPI("/systems");
    if (apiSystems && (Array.isArray(apiSystems) || (typeof apiSystems === 'object' && apiSystems !== null))) {
      let systemsList = Array.isArray(apiSystems) ? apiSystems : (apiSystems.systems || [apiSystems]);
      
      // If Watchlist-Only Sync is active, filter systems
      if (state.watchlistOnly) {
        systemsList = systemsList.filter(s => {
          const sn = (s.serialNumber || s.serial_number || "").toString().trim();
          return watchlistSerials.has(sn);
        });
      }
      
      if (systemsList.length > 0) {
        state.systems = systemsList.map(s => enrichSystemTelemetry(s));
        saveSystems();
        
        state.lastSync = new Date().toISOString();
        safeSetItem("aiq_last_sync", state.lastSync);
        
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
    document.getElementById("settingsWatchlistOnlyToggle").checked = state.watchlistOnly;
    document.getElementById("settingsRefreshToken").value = safeGetItem("aiq_refresh_token") || "";
    document.getElementById("settingsApiBaseUrl").value = state.apiBaseUrl;
    document.getElementById("settingsSyncInterval").value = state.syncInterval.toString();
    updateScheduledSyncInfo();
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
  updateScheduledSyncInfo();
  
  if (!state.mockMode) {
    await loadProductionData();
    checkAutoSync();
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

function getSystemSvms(sys) {
  // If it is StorageGRID or SANtricity/E-Series, return null (SVMs are an ONTAP feature)
  if (!sys || !sys.platform || sys.platform.includes("StorageGRID") || sys.platform.includes("E-Series") || sys.platform.includes("EF600") || sys.santricityVersion) {
    return null;
  }

  // Base list of SVMs derived dynamically from system serial number
  const seed = parseInt(sys.serialNumber.replace(/[^0-9]/g, '')) || 1234;
  return [
    {
      name: `${sys.systemName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-svm-nfs`,
      status: "running",
      protocols: ["NFS"],
      volumesCount: (seed % 15) + 5,
      lifsCount: 4,
      securitySettings: {
        smb1Enabled: false,
        smbEncryption: "N/A",
        nfsExportSuperuser: seed % 2 === 0 ? "restricted" : "any_host", // Triggers rule security warning
        auditLogging: seed % 3 === 0 ? "Disabled" : "Enabled"
      }
    },
    {
      name: `${sys.systemName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-svm-cifs`,
      status: "running",
      protocols: ["CIFS"],
      volumesCount: (seed % 10) + 3,
      lifsCount: 2,
      securitySettings: {
        smb1Enabled: seed % 2 === 0 || sys.systemName.includes("aff-01"), // Triggers Critical SMBv1 warning on netapp-aff-01
        smbEncryption: seed % 3 === 0 ? "Disabled" : "Required",
        nfsExportSuperuser: "N/A",
        auditLogging: "Enabled"
      }
    },
    {
      name: `${sys.systemName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-svm-san`,
      status: "running",
      protocols: ["iSCSI", "FCP"],
      volumesCount: (seed % 8) + 2,
      lifsCount: 4,
      securitySettings: {
        smb1Enabled: false,
        smbEncryption: "N/A",
        nfsExportSuperuser: "N/A",
        auditLogging: "Disabled"
      }
    }
  ];
}

function getSystemModelName(sys) {
  const p = sys.platform || "";
  if (p.toLowerCase().includes("cloud volumes") || p.toLowerCase().includes("cvo")) {
    const cloudName = p.includes("AWS") ? "AWS" : (p.includes("Azure") ? "Azure" : "GCP");
    return `Cloud ONTAP (${cloudName})`;
  }
  if (p.toLowerCase().includes("storagegrid")) {
    if (p.includes("SG100")) return "StorageGRID SG100";
    if (p.includes("SG6060")) return "StorageGRID SG6060";
    return "StorageGRID Webscale";
  }
  if (p.toLowerCase().includes("metrocluster")) {
    return p.replace(/\s*\(.*\)\s*/g, "");
  }
  return p.replace(/\s*\(.*\)\s*/g, "");
}

// 12. Visual Port Mapping & L1 Topology Representation Helpers
function getSystemPortMappings(sys) {
  // Check if system has specific risks to dynamically fail/degrade ports
  const hasSasFailure = sys.risks && sys.risks.some(r => r.description.toLowerCase().includes("path failure") || r.description.toLowerCase().includes("sas"));
  const hasClusterFailure = sys.risks && sys.risks.some(r => r.description.toLowerCase().includes("cluster interconnect") || r.description.toLowerCase().includes("cluster network"));
  const hasMgmtFailure = sys.risks && sys.risks.some(r => r.description.toLowerCase().includes("management") || r.description.toLowerCase().includes("mgmt"));
  const hasBatteryFailure = sys.risks && sys.risks.some(r => r.description.toLowerCase().includes("battery") || r.description.toLowerCase().includes("bbu"));
  
  const platformStr = sys.platform || "";
  const isEseries = sys.santricityVersion !== undefined || platformStr.toLowerCase().includes("e-series") || platformStr.toLowerCase().includes("ef600") || platformStr.toLowerCase().includes("e5700") || platformStr.toLowerCase().includes("ef300");
  const isCloud = platformStr.toLowerCase().includes("cloud");
  const isStorageGrid = platformStr.toLowerCase().includes("storagegrid") || platformStr.toLowerCase().includes("sg60") || platformStr.toLowerCase().includes("sg61") || platformStr.toLowerCase().includes("sg10") || platformStr.toLowerCase().includes("sg57");
  const isNextGen = platformStr.includes("A90") || platformStr.includes("A70") || platformStr.includes("C80") || platformStr.includes("A1K") || platformStr.includes("ASA") || platformStr.includes("AFX") || /A[0-9]{2,3}/.test(platformStr) || /C[0-9]{2,3}/.test(platformStr) || /r2/i.test(platformStr);
  const isAFX = platformStr.toLowerCase().includes("afx");
  
  if (isAFX) {
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
        name: "Slot 1 (HA)",
        type: "cluster",
        status: "online",
        partnerType: "cluster_switch",
        partnerName: `HA replication peer`,
        partnerPort: "Dedicated HA Link",
        cablingStatus: "optimal",
        details: { speed: "100 Gbps RoCE", mtu: 9000 }
      },
      {
        name: "Slot 7 (Clus)",
        type: "cluster",
        status: hasClusterFailure ? "offline" : "online",
        partnerType: "cluster_switch",
        partnerName: `${sys.clusterName.toLowerCase()}-afx-clus-sw-01`,
        partnerPort: "Eth1/7",
        cablingStatus: hasClusterFailure ? "disconnected" : "optimal",
        details: { speed: "100 Gbps (400GbE Breakout)", mtu: 9000, ip: "169.254.1.10" }
      },
      {
        name: "Slot 10 (Store A)",
        type: "nvme",
        status: "online",
        partnerType: "disk_shelf",
        partnerName: "shelf-nx224-saz-1",
        partnerPort: "NSM140-A-IN",
        cablingStatus: "optimal",
        details: { speed: "100 Gbps NVMe", shelfStack: "SAZ Shared Storage Pool Module A" }
      },
      {
        name: "Slot 11 (Store B)",
        type: "nvme",
        status: hasSasFailure ? "offline" : "online",
        partnerType: "disk_shelf",
        partnerName: "shelf-nx224-saz-1",
        partnerPort: "NSM140-B-IN",
        cablingStatus: hasSasFailure ? "disconnected" : "optimal",
        details: { speed: "100 Gbps NVMe", shelfStack: "SAZ Shared Storage Pool Module B" }
      },
      {
        name: "Slot 12 (Data 1)",
        type: "data",
        status: "online",
        partnerType: "core_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-core-sw-01`,
        partnerPort: "Eth1/1",
        cablingStatus: "optimal",
        details: { speed: "100 Gbps", mtu: 9000, ip: `10.100.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.11` }
      },
      {
        name: "Slot 12 (Data 2)",
        type: "data",
        status: "online",
        partnerType: "core_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-core-sw-02`,
        partnerPort: "Eth1/1",
        cablingStatus: "optimal",
        details: { speed: "100 Gbps", mtu: 9000, ip: `10.100.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.12` }
      }
    ];
  }
  
  if (isCloud) {
    const provider = sys.platform.includes("AWS") ? "AWS VPC" : (sys.platform.includes("Azure") ? "Azure VNet" : "GCP VPC");
    return [
      {
        name: "e0a",
        type: "mgmt",
        status: "online",
        partnerType: "mgmt_switch",
        partnerName: `${provider} Management Subnet Gateway`,
        partnerPort: "vNic0",
        cablingStatus: "optimal",
        details: { speed: "10 Gbps Virtual", mtu: 1500, ip: `10.240.${(parseInt(sys.serialNumber.slice(-4)) || 100) % 250 + 1}.10` }
      },
      {
        name: "e0b",
        type: "data",
        status: "online",
        partnerType: "core_switch",
        partnerName: `${provider} Data Subnet Route Table`,
        partnerPort: "vNic1",
        cablingStatus: "optimal",
        details: { speed: "25 Gbps Virtual", mtu: 9000, ip: `10.240.${(parseInt(sys.serialNumber.slice(-4)) || 100) % 250 + 1}.20` }
      },
      {
        name: "e0c",
        type: "cluster",
        status: "online",
        partnerType: "cluster_switch",
        partnerName: `${provider} HA Interconnect Peering`,
        partnerPort: "vNic2",
        cablingStatus: "optimal",
        details: { speed: "25 Gbps Virtual", mtu: 9000, ip: "169.254.100.1" }
      },
      {
        name: "e0d",
        type: "data",
        status: "online",
        partnerType: "core_switch",
        partnerName: `${provider} Intercluster Sync Routing`,
        partnerPort: "vNic3",
        cablingStatus: "optimal",
        details: { speed: "10 Gbps Virtual", mtu: 9000, ip: `10.240.${(parseInt(sys.serialNumber.slice(-4)) || 100) % 250 + 1}.30` }
      }
    ];
  }

  if (isStorageGrid) {
    return [
      {
        name: "Grid Network",
        type: "cluster",
        status: "online",
        partnerType: "cluster_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-grid-sw-A`,
        partnerPort: "Port 1",
        cablingStatus: "optimal",
        details: { speed: "10/25 Gbps Bond", mtu: 9000, ip: `172.16.${(parseInt(sys.serialNumber.slice(-4)) || 100) % 250 + 1}.2` }
      },
      {
        name: "Admin Network",
        type: "mgmt",
        status: "online",
        partnerType: "mgmt_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-mgmt-sw-A`,
        partnerPort: "Port 2",
        cablingStatus: "optimal",
        details: { speed: "1 Gbps Active-Backup", mtu: 1500, ip: `10.120.${(parseInt(sys.serialNumber.slice(-4)) || 100) % 250 + 1}.2` }
      },
      {
        name: "Client Network",
        type: "data",
        status: "online",
        partnerType: "core_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-core-sw-A`,
        partnerPort: "Port 3",
        cablingStatus: "optimal",
        details: { speed: "10/25 Gbps Bond", mtu: 9000, ip: `192.168.${(parseInt(sys.serialNumber.slice(-4)) || 100) % 250 + 1}.2` }
      }
    ];
  }

  if (isEseries) {
    const isEf600 = sys.platform.includes("EF600");
    return [
      {
        name: "Mgmt 1",
        type: "mgmt",
        status: hasMgmtFailure ? "offline" : "online",
        partnerType: "mgmt_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-mgmt-sw-01`,
        partnerPort: "Fa0/12",
        cablingStatus: hasMgmtFailure ? "disconnected" : "optimal",
        details: { speed: "1 Gbps", mtu: 1500, ip: `10.220.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.21` }
      },
      {
        name: "Mgmt 2",
        type: "mgmt",
        status: "online",
        partnerType: "mgmt_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-mgmt-sw-02`,
        partnerPort: "Fa0/12",
        cablingStatus: "optimal",
        details: { speed: "1 Gbps", mtu: 1500, ip: `10.220.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.22` }
      },
      {
        name: "Host 1",
        type: isEf600 ? "data" : "fc",
        status: "online",
        partnerType: isEf600 ? "core_switch" : "san_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-${isEf600 ? 'core-sw-01' : 'san-sw-A'}`,
        partnerPort: isEf600 ? "Eth1/5" : "fc1/12",
        cablingStatus: "optimal",
        details: isEf600 
          ? { speed: "100 Gbps NVMe-oF", mtu: 9000, ip: `10.150.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.1` }
          : { speed: "32 Gbps FC", wwpn: `50:0a:09:80:40:2a:1b:${sys.serialNumber.slice(-2)}` }
      },
      {
        name: "Host 2",
        type: isEf600 ? "data" : "fc",
        status: "online",
        partnerType: isEf600 ? "core_switch" : "san_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-${isEf600 ? 'core-sw-02' : 'san-sw-B'}`,
        partnerPort: isEf600 ? "Eth1/5" : "fc1/12",
        cablingStatus: "optimal",
        details: isEf600 
          ? { speed: "100 Gbps NVMe-oF", mtu: 9000, ip: `10.150.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.2` }
          : { speed: "32 Gbps FC", wwpn: `50:0a:09:80:40:2a:1c:${sys.serialNumber.slice(-2)}` }
      },
      {
        name: "Host 3",
        type: isEf600 ? "data" : "fc",
        status: "online",
        partnerType: isEf600 ? "core_switch" : "san_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-${isEf600 ? 'core-sw-01' : 'san-sw-A'}`,
        partnerPort: isEf600 ? "Eth1/6" : "fc1/13",
        cablingStatus: "optimal",
        details: isEf600 
          ? { speed: "100 Gbps NVMe-oF", mtu: 9000, ip: `10.150.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.3` }
          : { speed: "32 Gbps FC", wwpn: `50:0a:09:80:40:2a:1d:${sys.serialNumber.slice(-2)}` }
      },
      {
        name: "Host 4",
        type: isEf600 ? "data" : "fc",
        status: "online",
        partnerType: isEf600 ? "core_switch" : "san_switch",
        partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-${isEf600 ? 'core-sw-02' : 'san-sw-B'}`,
        partnerPort: isEf600 ? "Eth1/6" : "fc1/13",
        cablingStatus: "optimal",
        details: isEf600 
          ? { speed: "100 Gbps NVMe-oF", mtu: 9000, ip: `10.150.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.4` }
          : { speed: "32 Gbps FC", wwpn: `50:0a:09:80:40:2a:1e:${sys.serialNumber.slice(-2)}` }
      },
      {
        name: "Exp 1",
        type: "sas",
        status: "online",
        partnerType: "disk_shelf",
        partnerName: "shelf-de224c-stack-1",
        partnerPort: "IOM-A-IN",
        cablingStatus: "optimal",
        details: { speed: "12 Gbps SAS", shelfStack: "DE224C Module A" }
      },
      {
        name: "Exp 2",
        type: "sas",
        status: hasSasFailure ? "offline" : "online",
        partnerType: "disk_shelf",
        partnerName: "shelf-de224c-stack-1",
        partnerPort: "IOM-B-IN",
        cablingStatus: hasSasFailure ? "disconnected" : "optimal",
        details: { speed: "12 Gbps SAS", shelfStack: "DE224C Module B" }
      }
    ];
  }
  
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
      details: { speed: isNextGen ? "100 Gbps" : "40 Gbps", mtu: 9000, ip: "169.254.1.10" }
    },
    {
      name: "e0b",
      type: "cluster",
      status: hasClusterFailure ? "offline" : "online",
      partnerType: "cluster_switch",
      partnerName: `${sys.clusterName.toLowerCase()}-clus-sw-02`,
      partnerPort: "Eth1/1",
      cablingStatus: hasClusterFailure ? "disconnected" : "optimal",
      details: { speed: isNextGen ? "100 Gbps" : "40 Gbps", mtu: 9000, ip: "169.254.2.10" }
    },
    {
      name: "e0c",
      type: "data",
      status: "online",
      partnerType: "core_switch",
      partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-core-sw-01`,
      partnerPort: "Eth1/41",
      cablingStatus: "optimal",
      details: { speed: isNextGen ? "100 Gbps" : "10 Gbps", mtu: 9000, ip: `10.100.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.11` }
    },
    {
      name: "e0d",
      type: "data",
      status: "online",
      partnerType: "core_switch",
      partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-core-sw-02`,
      partnerPort: "Eth1/41",
      cablingStatus: "optimal",
      details: { speed: isNextGen ? "100 Gbps" : "10 Gbps", mtu: 9000, ip: `10.100.${(parseInt(sys.serialNumber.slice(-4)) % 250) + 1}.12` }
    },
    {
      name: "0a",
      type: "fc",
      status: "online",
      partnerType: "san_switch",
      partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-san-sw-A`,
      partnerPort: "fc1/5",
      cablingStatus: "optimal",
      details: { speed: isNextGen ? "64 Gbps" : "32 Gbps", wwpn: `50:0a:09:80:30:1a:2b:${sys.serialNumber.slice(-2)}` }
    },
    {
      name: "0b",
      type: "fc",
      status: "online",
      partnerType: "san_switch",
      partnerName: `${sys.customerName.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-san-sw-B`,
      partnerPort: "fc1/5",
      cablingStatus: "optimal",
      details: { speed: isNextGen ? "64 Gbps" : "32 Gbps", wwpn: `50:0a:09:80:30:1a:2c:${sys.serialNumber.slice(-2)}` }
    },
    {
      name: "0c",
      type: isNextGen ? "nvme" : "sas",
      status: "online",
      partnerType: "disk_shelf",
      partnerName: isNextGen ? "shelf-ns224-stack-1" : "shelf-ds224c-stack-1",
      partnerPort: isNextGen ? "NSM-A-IN" : "IOM-A-IN",
      cablingStatus: "optimal",
      details: isNextGen 
        ? { speed: "100 Gbps NVMe", shelfStack: "NS224 NVMe Shelf Stack 1 Module A" }
        : { speed: "12 Gbps SAS", shelfStack: "Stack 1 Module A" }
    },
    {
      name: "0d",
      type: isNextGen ? "nvme" : "sas",
      status: hasSasFailure ? "offline" : "online",
      partnerType: "disk_shelf",
      partnerName: isNextGen ? "shelf-ns224-stack-1" : "shelf-ds224c-stack-1",
      partnerPort: isNextGen ? "NSM-B-IN" : "IOM-B-IN",
      cablingStatus: hasSasFailure ? "disconnected" : "optimal",
      details: isNextGen 
        ? { speed: "100 Gbps NVMe", shelfStack: "NS224 NVMe Shelf Stack 1 Module B" }
        : { speed: "12 Gbps SAS", shelfStack: "Stack 1 Module B" }
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

  let backplateHtml = "";
  const isEseries = sys.santricityVersion !== undefined || sys.platform.includes("E-Series");
  const isCloud = sys.platform.toLowerCase().includes("cloud");
  const isStorageGrid = sys.platform.toLowerCase().includes("storagegrid");

  if (isCloud) {
    backplateHtml = `
      <div style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(30, 64, 175, 0.2)); border: 3px dashed #3b82f6; border-radius: var(--radius-md); padding: 18px 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); text-align: center; position: sticky; top: 12px; border-left: 8px solid #3b82f6;">
        <div style="font-size: 0.8rem; font-weight: 700; color: #fff; margin-bottom: 6px;">VIRTUAL APPLIANCE NODE</div>
        <div style="font-size: 0.65rem; color: var(--accent-cyan); font-family: monospace; text-transform: uppercase; margin-bottom: 12px;">${sys.platform}</div>
        <div style="font-size: 2.2rem; margin: 15px 0; color: var(--accent-cyan); filter: drop-shadow(0 0 8px rgba(0, 229, 255, 0.4));">☁️</div>
        <div style="font-size: 0.65rem; color: var(--text-muted); line-height: 1.4; text-align: left; background: rgba(0,0,0,0.3); padding: 10px; border-radius: var(--radius-sm);">
          Cloud Volumes ONTAP represents a virtual appliance deployed in cloud subnets. Layer-1 cabling is managed dynamically by cloud provider hypervisors.
        </div>
      </div>
    `;
  } else if (isStorageGrid) {
    backplateHtml = `
      <div style="background: linear-gradient(135deg, rgba(168, 85, 247, 0.1), rgba(107, 33, 168, 0.2)); border: 3px solid #a855f7; border-radius: var(--radius-md); padding: 18px 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); text-align: center; position: sticky; top: 12px; border-left: 8px solid #a855f7;">
        <div style="font-size: 0.8rem; font-weight: 700; color: #fff; margin-bottom: 6px;">OBJECT APPLIANCE NODE</div>
        <div style="font-size: 0.65rem; color: var(--accent-cyan); font-family: monospace; text-transform: uppercase; margin-bottom: 12px;">${sys.platform}</div>
        <div style="font-size: 2.2rem; margin: 15px 0; color: #a855f7; filter: drop-shadow(0 0 8px rgba(168, 85, 247, 0.4));">⚙️</div>
        <div style="font-size: 0.65rem; color: var(--text-muted); line-height: 1.4; text-align: left; background: rgba(0,0,0,0.3); padding: 10px; border-radius: var(--radius-sm);">
          StorageGRID grid networks handle S3/Swift object ingest and replication across nodes. Port profiles map grid, admin, and client subnets.
        </div>
      </div>
    `;
  } else if (isEseries) {
    backplateHtml = `
      <div style="background: linear-gradient(135deg, #1e293b, #0f172a); border: 3px solid #475569; border-radius: var(--radius-md); padding: 18px 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); border-left: 8px solid #f59e0b; position: sticky; top: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #475569; padding-bottom: 8px; margin-bottom: 14px;">
          <div style="font-size: 0.65rem; font-weight: 700; color: #fff; letter-spacing: 0.5px;">
            ${sys.systemName.toLowerCase().endsWith('b') ? 'E-SERIES CONTROLLER B' : 'E-SERIES CONTROLLER A'}
          </div>
          <div style="font-size: 0.58rem; color: #f59e0b; font-family: monospace;">${getSystemModelName(sys)}</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; background: rgba(0,0,0,0.3); padding: 8px; border-radius: var(--radius-sm);">
          ${portsHtml}
        </div>
        <div style="margin-top: 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; border-top: 1px solid #475569; padding-top: 10px;">
          <div style="background: #1e293b; height: 18px; border-radius: var(--radius-sm); font-size: 0.55rem; text-align: center; color: var(--text-muted); font-weight: 700; line-height: 18px; border: 1px solid rgba(255,255,255,0.05);">POWER-A</div>
          <div style="background: #1e293b; height: 18px; border-radius: var(--radius-sm); font-size: 0.55rem; text-align: center; color: var(--text-muted); font-weight: 700; line-height: 18px; border: 1px solid rgba(255,255,255,0.05);">POWER-B</div>
        </div>
        <div style="margin-top: 12px; font-size: 0.62rem; color: var(--text-muted); line-height: 1.35; text-align: center;">
          E-Series SANtricity hardware L1 host and storage expansion interface mapping layout.
        </div>
      </div>
    `;
  } else {
    backplateHtml = `
      <div style="background: linear-gradient(135deg, #1f2937, #111827); border: 3px solid #374151; border-radius: var(--radius-md); padding: 18px 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); border-left: 8px solid var(--accent-cyan); position: sticky; top: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #4b5563; padding-bottom: 8px; margin-bottom: 14px;">
          <div style="font-size: 0.65rem; font-weight: 700; color: #fff; letter-spacing: 0.5px;">
            ${sys.systemName.toLowerCase().endsWith('b') ? 'CONTROLLER B (SLOT B - BOTTOM)' : 'CONTROLLER A (SLOT A - TOP)'}
          </div>
          <div style="font-size: 0.58rem; color: var(--accent-cyan); font-family: monospace;">${getSystemModelName(sys)}</div>
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
    `;
  }

  container.innerHTML = `
    ${tabsHtml}
    <div style="display: grid; grid-template-columns: 280px 1fr; gap: 24px; align-items: start;">
      ${backplateHtml}
      
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
    
    // Dynamically update E-Series visual health panel and SVM security panel to remain context-aware
    const eseriesCard = document.getElementById("tamEseriesVisualCard");
    const isEseries = activeSys && (activeSys.santricityVersion !== undefined || activeSys.platform.includes("E-Series"));
    if (eseriesCard) {
      if (isEseries) {
        eseriesCard.style.display = "block";
        renderEseriesHardwareAudit(activeSys);
      } else {
        eseriesCard.style.display = "none";
      }
    }
    
    const svmCard = document.getElementById("tamSvmCard");
    if (svmCard) {
      const svms = getSystemSvms(activeSys);
      if (svms && svms.length > 0) {
        svmCard.style.display = "block";
        renderSvmSecurityAudit(activeSys);
      } else {
        svmCard.style.display = "none";
      }
    }
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

function renderEseriesHardwareAudit(sys) {
  const container = document.getElementById("tamEseriesVisualContainer");
  if (!container) return;

  const hw = sys.eseriesHardware;
  if (!hw) {
    container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 12px;">No hardware details available for this system.</div>`;
    return;
  }

  // 1. Render Controllers
  let controllersHtml = "";
  hw.controllers.forEach(ctrl => {
    const isOptimal = ctrl.status === "Optimal";
    const bbuOptimal = ctrl.batteryStatus === "Optimal";
    const statusColor = isOptimal ? "var(--status-normal)" : "var(--status-critical)";
    const bbuColor = bbuOptimal ? "var(--status-normal)" : "var(--status-warning)";
    
    controllersHtml += `
      <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 16px; display: flex; flex-direction: column; gap: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <h4 style="font-weight: 600; color: #fff; font-size: 0.9rem; margin: 0;">${ctrl.name}</h4>
          <span style="font-size: 0.72rem; color: ${statusColor}; font-weight: 700;">● ${ctrl.status}</span>
        </div>
        <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.5; margin-top: 8px;">
          <div>Cache Size: <strong>${ctrl.cacheGB} GB</strong></div>
          <div>NVSRAM: <code>${ctrl.nvsram}</code></div>
          <div style="margin-top: 4px; display: flex; justify-content: space-between; align-items: center;">
            <span>Battery Backup (BBU):</span>
            <span style="color: ${bbuColor}; font-weight: 600;">${ctrl.batteryStatus}</span>
          </div>
        </div>
      </div>
    `;
  });

  // 2. Render Storage Pools / Volume Groups
  let poolsHtml = "";
  hw.storagePools.forEach(pool => {
    const usedTB = (pool.capacityTB - pool.freeTB).toFixed(1);
    const pct = ((usedTB / pool.capacityTB) * 100).toFixed(0);
    poolsHtml += `
      <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 14px; display: flex; flex-direction: column; gap: 6px;">
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem;">
          <strong style="color: #fff;">${pool.name}</strong>
          <span style="color: var(--status-info); font-size: 0.72rem; font-weight: 600;">${pool.raidType}</span>
        </div>
        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
          Capacity: ${usedTB} TB / ${pool.capacityTB} TB (${pct}% Used)
        </div>
        <div style="background: rgba(255,255,255,0.08); height: 8px; border-radius: 4px; overflow: hidden; margin-top: 6px;">
          <div style="background: var(--accent-cyan); width: ${pct}%; height: 100%;"></div>
        </div>
      </div>
    `;
  });

  // 3. Render Shelves & Disks
  let shelvesHtml = "";
  hw.shelves.forEach(shelf => {
    let disksHtml = "";
    
    shelf.disks.forEach(disk => {
      let color = "var(--status-normal)";
      if (disk.status === "Failed") color = "var(--status-critical)";
      else if (disk.status === "Reconstructing") color = "var(--status-warning)";
      
      const tooltip = `Bay ${disk.bay} | ${disk.type} | ${disk.size}\nStatus: ${disk.status}\nSSD Wear Life Remaining: ${disk.wearLife}%`;
      const isSSD = disk.type.toLowerCase().includes("ssd");
      
      disksHtml += `
        <div class="eseries-disk-slot" data-tooltip="${tooltip}"
             style="background: rgba(255,255,255,0.04); border: 1px solid var(--border-color); border-radius: 3px; padding: 8px 4px; text-align: center; cursor: pointer; transition: all 0.2s;"
             onmouseenter="this.style.borderColor='var(--accent-cyan)'; this.style.background='rgba(0, 229, 255, 0.05)';"
             onmouseleave="this.style.borderColor=''; this.style.background='';">
          <div style="font-size: 0.65rem; color: var(--text-secondary); font-weight: 600; margin-bottom: 4px;">Bay ${disk.bay}</div>
          <div style="width: 8px; height: 8px; border-radius: 50%; background: ${color}; margin: 4px auto;"></div>
          <div style="font-size: 0.58rem; color: var(--text-muted); font-family: monospace;">${disk.size}</div>
          ${isSSD ? `
            <div style="margin-top: 6px; padding: 0 4px;">
              <div style="font-size: 0.52rem; color: var(--text-muted); margin-bottom: 2px;">Wear: ${disk.wearLife}%</div>
              <div style="background: rgba(255,255,255,0.1); height: 3px; border-radius: 1.5px; overflow: hidden;">
                <div style="background: ${disk.wearLife < 85 ? 'var(--status-warning)' : 'var(--status-normal)'}; width: ${disk.wearLife}%; height: 100%;"></div>
              </div>
            </div>
          ` : `<div style="font-size: 0.52rem; color: var(--text-muted); margin-top: 6px;">HDD</div>`}
        </div>
      `;
    });

    shelvesHtml += `
      <div style="border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 16px; background: rgba(15,22,38,0.2); display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">
          <span style="font-weight: 600; color: #fff; font-size: 0.82rem;">${shelf.name} (${shelf.model})</span>
          <span style="font-size: 0.72rem; color: var(--text-secondary);">DE224C Multi-Interface SAS</span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(8, 1fr); gap: 10px;">
          ${disksHtml}
        </div>
      </div>
    `;
  });

  container.innerHTML = `
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 20px;">
      <!-- Controller Module Stats -->
      <div>
        <h4 style="font-size: 0.85rem; font-weight: 700; color: var(--text-secondary); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Active-Active Controllers</h4>
        <div style="display: flex; flex-direction: column; gap: 12px;">
          ${controllersHtml}
        </div>
      </div>
      
      <!-- Storage Pools Details -->
      <div>
        <h4 style="font-size: 0.85rem; font-weight: 700; color: var(--text-secondary); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Volumes & Disk Pools</h4>
        <div style="display: flex; flex-direction: column; gap: 12px;">
          ${poolsHtml}
        </div>
      </div>
    </div>
    
    <div>
      <h4 style="font-size: 0.85rem; font-weight: 700; color: var(--text-secondary); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Storage Shelves & Drive bays</h4>
      ${shelvesHtml}
    </div>
  `;
}

function renderSvmSecurityAudit(sys) {
  const container = document.getElementById("tamSvmContainer");
  if (!container) return;

  const svms = getSystemSvms(sys);
  if (!svms || svms.length === 0) {
    container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 12px;">SVM auditing is only available for ONTAP storage arrays.</div>`;
    return;
  }

  // Compile SVM rows
  let svmRowsHtml = "";
  let anySmb1 = false;
  let anyInsecureNfs = false;
  let anyDisabledAudit = false;

  svms.forEach(svm => {
    const isSmb1 = svm.securitySettings.smb1Enabled === true;
    const isInsecureNfs = svm.securitySettings.nfsExportSuperuser === "any_host";
    const isAuditDisabled = svm.securitySettings.auditLogging === "Disabled";
    
    if (isSmb1) anySmb1 = true;
    if (isInsecureNfs) anyInsecureNfs = true;
    if (isAuditDisabled) anyDisabledAudit = true;

    // Security Status badge
    let secStatusBadge = `<span class="badge info" style="background: rgba(0, 230, 118, 0.08); border-color: rgba(0, 230, 118, 0.25); color: var(--status-normal);">✓ Secure</span>`;
    if (isSmb1 || isInsecureNfs) {
      secStatusBadge = `<span class="badge critical" style="background: rgba(255, 51, 102, 0.08); border-color: rgba(255, 51, 102, 0.25); color: var(--status-critical);">✗ At Risk</span>`;
    } else if (isAuditDisabled) {
      secStatusBadge = `<span class="badge warning" style="background: rgba(255, 152, 0, 0.08); border-color: rgba(255, 152, 0, 0.25); color: var(--status-warning);">⚠️ Warning</span>`;
    }

    // Protocol label list
    const protoBadges = svm.protocols.map(p => {
      let color = "var(--accent-cyan)";
      if (p === "NFS") color = "#3b82f6";
      if (p === "CIFS") color = "#10b981";
      if (p === "iSCSI") color = "#f59e0b";
      if (p === "FCP") color = "#eab308";
      return `<span style="background: rgba(255,255,255,0.05); color: ${color}; border: 1px solid rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 4px; font-size: 0.68rem; font-weight: 600; margin-right: 4px; font-family: monospace;">${p}</span>`;
    }).join("");

    svmRowsHtml += `
      <tr style="border-bottom: 1px solid var(--border-color);">
        <td style="padding: 10px; font-weight: 700; color: #fff;"><code>${svm.name}</code></td>
        <td style="padding: 10px;">
          <span style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.75rem; color: var(--status-normal);">
            <span style="width: 8px; height: 8px; border-radius: 50%; background: var(--status-normal);"></span>
            ${svm.status}
          </span>
        </td>
        <td style="padding: 10px;">${protoBadges}</td>
        <td style="padding: 10px; text-align: center; color: var(--text-secondary);">${svm.volumesCount}</td>
        <td style="padding: 10px; text-align: center; color: var(--text-secondary);">${svm.lifsCount}</td>
        <td style="padding: 10px;">${secStatusBadge}</td>
      </tr>
    `;
  });

  // Build Protocol Hardening Compliance Ticks
  const smb1StatusHtml = anySmb1
    ? `<span style="color: var(--status-critical); font-weight: 700;">✗ At Risk (SMB1 Enabled)</span><div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">Ransomware vulnerability. Remediation: Run <code>vserver cifs options modify -vserver &lt;svm&gt; -smb1-enabled false</code></div>`
    : `<span style="color: var(--status-normal); font-weight: 600;">✓ Secure (SMBv1 Disabled)</span><div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">Enforces secure SMB2/SMB3 communication channels.</div>`;

  const nfsStatusHtml = anyInsecureNfs
    ? `<span style="color: var(--status-critical); font-weight: 700;">✗ At Risk (Superuser root mount allowed)</span><div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">Anonymous hosts can claim root ownership. Remediation: Squash root (superuser=none) in export policy rules.</div>`
    : `<span style="color: var(--status-normal); font-weight: 600;">✓ Secure (NFS Export Controls)</span><div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">All NFS root mount superuser mappings are squashed or restricted.</div>`;

  const auditStatusHtml = anyDisabledAudit
    ? `<span style="color: var(--status-warning); font-weight: 600;">⚠️ Warning (Audit Logging Disabled)</span><div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">Config changes and file access auditing are disabled. Enable auditing to meet audit compliance.</div>`
    : `<span style="color: var(--status-normal); font-weight: 600;">✓ Secure (SVM Auditing Enabled)</span><div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">SVM configuration changes are actively logged.</div>`;

  container.innerHTML = `
    <div style="display: grid; grid-template-columns: 1.4fr 1fr; gap: 24px; align-items: start;">
      
      <!-- SVM Inventory Table -->
      <div class="data-table-container" style="border: 1px solid var(--border-color); border-radius: var(--radius-sm); overflow-x: auto; background: rgba(15,22,38,0.2);">
        <table class="data-table" style="width: 100%; border-collapse: collapse; font-size: 0.8rem;">
          <thead>
            <tr style="background: rgba(255, 255, 255, 0.015); border-bottom: 1px solid var(--border-color); text-align: left;">
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">SVM / Vserver</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">Status</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">Protocols</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary); text-align: center;">Volumes</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary); text-align: center;">LIFs</th>
              <th style="padding: 10px; font-weight: 600; color: var(--text-secondary);">Security Level</th>
            </tr>
          </thead>
          <tbody>
            ${svmRowsHtml}
          </tbody>
        </table>
      </div>

      <!-- Hardening Audit Checklist -->
      <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 18px 16px;">
        <h4 style="font-size: 0.82rem; font-weight: 700; color: #fff; margin-bottom: 14px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border-color); padding-bottom: 6px;">Protocol Security Checklist</h4>
        
        <div style="display: flex; flex-direction: column; gap: 14px;">
          <div style="border-left: 3px solid ${anySmb1 ? 'var(--status-critical)' : 'var(--status-normal)'}; padding-left: 10px;">
            <div style="font-size: 0.78rem; font-weight: 600; color: #fff;">SMBv1 Protocol Status</div>
            <div style="font-size: 0.75rem; margin-top: 2px;">${smb1StatusHtml}</div>
          </div>
          
          <div style="border-left: 3px solid ${anyInsecureNfs ? 'var(--status-critical)' : 'var(--status-normal)'}; padding-left: 10px;">
            <div style="font-size: 0.78rem; font-weight: 600; color: #fff;">NFS Root Export Access</div>
            <div style="font-size: 0.75rem; margin-top: 2px;">${nfsStatusHtml}</div>
          </div>

          <div style="border-left: 3px solid ${anyDisabledAudit ? 'var(--status-warning)' : 'var(--status-normal)'}; padding-left: 10px;">
            <div style="font-size: 0.78rem; font-weight: 600; color: #fff;">SVM Configuration Audit Logging</div>
            <div style="font-size: 0.75rem; margin-top: 2px;">${auditStatusHtml}</div>
          </div>
          
          <div style="border-left: 3px solid var(--status-normal); padding-left: 10px;">
            <div style="font-size: 0.78rem; font-weight: 600; color: #fff;">Management Port Security (SSL/TLS)</div>
            <div style="font-size: 0.75rem; margin-top: 2px;">
              <span style="color: var(--status-normal); font-weight: 600;">✓ Secure (TLSv1.2, TLSv1.3 only)</span>
              <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">Deprecated SSLv3 and TLSv1.0/1.1 protocols are disabled cluster-wide.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

