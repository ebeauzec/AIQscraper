// Active IQ Web Client - Core Application Logic
const API_BASE = "https://api.activeiq.netapp.com/v1";

// 1. Mock Data Definitions (For offline testing and developer previews)
const MOCK_SYSTEMS = [
  {
    serialNumber: "622001234567",
    systemName: "netapp-aff-01",
    clusterName: "NY-AFF-CLUSTER",
    customerName: "Global Bank Corp",
    ontapVersion: "9.12.1P4",
    platform: "AFF A400",
    status: "warning",
    risks: [
      {
        id: 101,
        severity: "high",
        category: "Hardware",
        description: "Single Controller Path Failure detected on SAS loop 1.",
        recommendation: "Inspect SAS cable connections on shelf 2, port 1B. Refer to KB1089201.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/Single_controller_path_errors"
      },
      {
        id: 102,
        severity: "medium",
        category: "Software",
        description: "Disk Shelf firmware is outdated (current: 0240, target: 0260).",
        recommendation: "Schedule a non-disruptive firmware upgrade using ONTAP System Manager.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/Disk_Shelves_and_Storage_Storage_Media/How_to_update_shelf_firmware"
      },
      {
        id: 103,
        severity: "low",
        category: "Best Practice",
        description: "Insecure HTTP management protocol enabled on Cluster LIF.",
        recommendation: "Disable HTTP and enforce HTTPS management access using command: 'system services web modify -http-enabled false'.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Protection_and_Security/Security/How_to_enable_HTTPS_and_disable_HTTP"
      }
    ],
    upgrades: {
      targetVersion: "9.13.1P8",
      urgency: "Recommended",
      benefits: "Fixes 12 critical security vulnerabilities and improves volume throughput efficiency by 8%."
    },
    contracts: {
      status: "warning",
      endDate: "2026-08-01", // ~26 days from local time 2026-07-06
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
    }
  },
  {
    serialNumber: "622009876543",
    systemName: "netapp-fas-02",
    clusterName: "LN-FAS-CLUSTER",
    customerName: "Euro Logistics Ltd",
    ontapVersion: "9.9.1P15",
    platform: "FAS8300",
    status: "critical",
    risks: [
      {
        id: 201,
        severity: "critical",
        category: "Hardware",
        description: "Multiple drive failures predicted on aggregate 'aggr1_data'. Spare count is 0.",
        recommendation: "Immediate replacement of drive in Bay 12, Shelf 1. Order replacement spare.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Systems/Disk_Shelves_and_Storage_Storage_Media/Predictive_drive_failure_troubleshooting"
      },
      {
        id: 202,
        severity: "high",
        category: "Software",
        description: "ONTAP 9.9.1 is approaching End of Version Support.",
        recommendation: "Plan OS migration to ONTAP 9.12.1 or 9.13.1 within 60 days.",
        kbLink: "https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/ONTAP_software_support_lifecycle"
      }
    ],
    upgrades: {
      targetVersion: "9.11.1P12",
      urgency: "Required",
      benefits: "Restores full technical support status and resolves critical NVRAM logging memory bug."
    },
    contracts: {
      status: "critical",
      endDate: "2026-07-01", // Expired 5 days ago
      daysRemaining: -5,
      supportLevel: "SupportEdge Standard"
    },
    lifecycle: {
      eoaDate: "2024-12-31",
      eosDate: "2029-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "2.1:1",
      logicalUsedTB: 450.2,
      physicalUsedTB: 214.4,
      spaceSavedTB: 235.8,
      fabricPoolTieredTB: 0.0 // CSM Opportunity
    }
  },
  {
    serialNumber: "622005556666",
    systemName: "netapp-c190-03",
    clusterName: "SGP-CLUSTER",
    customerName: "Asia Tech Inc",
    ontapVersion: "9.14.1P2",
    platform: "AFF C190",
    status: "normal",
    risks: [],
    upgrades: {
      targetVersion: "Up to Date",
      urgency: "None",
      benefits: "System is running latest stable version."
    },
    contracts: {
      status: "normal",
      endDate: "2027-09-15",
      daysRemaining: 436,
      supportLevel: "SupportEdge Premium 2hr"
    },
    lifecycle: {
      eoaDate: "2026-12-31",
      eosDate: "2031-12-31",
      isNearEos: false
    },
    fieldActions: [],
    efficiency: {
      ratio: "5.5:1",
      logicalUsedTB: 85.0,
      physicalUsedTB: 15.4,
      spaceSavedTB: 69.6,
      fabricPoolTieredTB: 45.2
    }
  }
];

// 2. Global State Variable
let state = {
  currentTab: "overview",
  mockMode: true,
  systems: [...MOCK_SYSTEMS],
  selectedSystem: null,
  activeSearchQuery: ""
};

// 3. Storage Helpers
function loadConfig() {
  const mockModeVal = localStorage.getItem("aiq_mock_mode");
  state.mockMode = mockModeVal === null ? true : mockModeVal === "true";
  
  const refresh = localStorage.getItem("aiq_refresh_token") || "";
  const access = localStorage.getItem("aiq_access_token") || "";
  const expiry = localStorage.getItem("aiq_token_expiry") || "";
  
  return { refresh, access, expiry };
}

function saveConfig(refresh, access, expiry) {
  localStorage.setItem("aiq_refresh_token", refresh);
  localStorage.setItem("aiq_access_token", access);
  localStorage.setItem("aiq_token_expiry", expiry);
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

  // Token valid for at least 5 more minutes?
  if (access && expiry > (Date.now() / 1000) + 300) {
    return access;
  }

  // Swap refresh token for new access/refresh pair
  const response = await fetch(`${API_BASE}/tokens/accessToken`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh })
  });

  if (!response.ok) {
    throw new Error("Authentication failed. Please verify your Refresh Token in Settings.");
  }

  const data = await response.json();
  const newExpiry = (Date.now() / 1000) + 3600; // 1 hour validity
  saveConfig(data.refresh_token, data.access_token, newExpiry.toString());
  return data.access_token;
}

// Global API Fetch wrapper with auto-rotation
async function callActiveIQAPI(endpoint) {
  if (state.mockMode) {
    // Return mock results based on endpoint signatures
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

// Simulate API endpoints when in Mock Mode
function simulateMockAPIResponse(endpoint) {
  // Simple endpoint matching
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
  
  // Collect aggregated stats based on state.systems
  const logicalSum = state.systems.reduce((acc, sys) => acc + sys.efficiency.logicalUsedTB, 0);
  const physicalSum = state.systems.reduce((acc, sys) => acc + sys.efficiency.physicalUsedTB, 0);
  const savedSum = state.systems.reduce((acc, sys) => acc + sys.efficiency.spaceSavedTB, 0);
  const tieredSum = state.systems.reduce((acc, sys) => acc + sys.efficiency.fabricPoolTieredTB, 0);

  // Destroy existing charts to prevent canvas ghosting on redraw
  if (efficiencyChartInstance) efficiencyChartInstance.destroy();
  if (capacityChartInstance) capacityChartInstance.destroy();

  if (typeof Chart === "undefined") {
    console.warn("Chart.js library not loaded yet.");
    return;
  }

  // 1. Efficiency Chart (Savings Breakdown)
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

  // 2. Capacity & Tiering Chart (Cloud vs On-Prem)
  capacityChartInstance = new Chart(ctxCap, {
    type: 'bar',
    data: {
      labels: state.systems.map(s => s.systemName),
      datasets: [
        {
          label: 'On-Prem Flash Storage (TB)',
          data: state.systems.map(s => (s.efficiency.physicalUsedTB - s.efficiency.fabricPoolTieredTB).toFixed(1)),
          backgroundColor: 'rgba(79, 172, 254, 0.7)',
          borderColor: '#4facfe',
          borderWidth: 1
        },
        {
          label: 'FabricPool Tiered to Cloud (TB)',
          data: state.systems.map(s => s.efficiency.fabricPoolTieredTB.toFixed(1)),
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

function updateOverviewKpis() {
  const totalSystems = state.systems.length;
  const criticalRisksCount = state.systems.reduce((acc, sys) => 
    acc + sys.risks.filter(r => r.severity === 'critical').length, 0);
  const warningRisksCount = state.systems.reduce((acc, sys) => 
    acc + sys.risks.filter(r => r.severity === 'high' || r.severity === 'medium').length, 0);
  const expiringContracts = state.systems.filter(sys => sys.contracts.daysRemaining <= 90).length;

  document.getElementById("kpiTotalSystems").innerText = totalSystems;
  document.getElementById("kpiCriticalRisks").innerText = criticalRisksCount;
  document.getElementById("kpiWarningRisks").innerText = warningRisksCount;
  document.getElementById("kpiContracts").innerText = expiringContracts;
  
  // Set KPI colors based on values
  document.getElementById("kpiCriticalRisks").style.color = criticalRisksCount > 0 ? "var(--status-critical)" : "var(--status-normal)";
  document.getElementById("kpiWarningRisks").style.color = warningRisksCount > 0 ? "var(--status-warning)" : "var(--status-normal)";
  document.getElementById("kpiContracts").style.color = expiringContracts > 0 ? "var(--status-warning)" : "var(--status-normal)";
}

function renderOverviewTable() {
  const tbody = document.getElementById("overviewTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const query = state.activeSearchQuery.toLowerCase();
  const filteredSystems = state.systems.filter(sys => 
    sys.systemName.toLowerCase().includes(query) || 
    sys.serialNumber.toLowerCase().includes(query) ||
    sys.clusterName.toLowerCase().includes(query) ||
    sys.customerName.toLowerCase().includes(query)
  );

  if (filteredSystems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No matching systems found.</td></tr>`;
    return;
  }

  filteredSystems.forEach(sys => {
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.onclick = () => selectSystem(sys.serialNumber);
    
    // Status Badge
    let statusBadge = `<span class="badge normal">Healthy</span>`;
    if (sys.status === "critical") statusBadge = `<span class="badge critical">Critical</span>`;
    else if (sys.status === "warning") statusBadge = `<span class="badge warning">Warning</span>`;

    // Contract status End Date
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

function renderTAMTab() {
  const sys = state.selectedSystem || state.systems[0];
  const container = document.getElementById("tamViewContainer");
  if (!container || !sys) return;

  // Header Details
  document.getElementById("tamActiveSystem").innerHTML = `
    <strong>System</strong>: ${sys.systemName} (S/N: ${sys.serialNumber}) | <strong>ONTAP</strong>: ${sys.ontapVersion}
  `;

  // Render Risk Table
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
            <div style="color: var(--text-secondary); font-size: 0.8rem;">${r.recommendation}</div>
          </td>
          <td>
            <a class="external-link" href="${r.kbLink}" target="_blank">
              View KB <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
            </a>
          </td>
        </tr>
      `;
    });
  }

  // Render Upgrade Section
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
      <div style="margin-bottom: 8px;">Target Version: <strong style="color: var(--accent-cyan);">${sys.upgrades.targetVersion}</strong></div>
      <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;">${sys.upgrades.benefits}</p>
    `;
  }

  document.getElementById("tamRisksTableBody").innerHTML = riskRows;
}

function renderSAMTab() {
  const sys = state.selectedSystem || state.systems[0];
  const container = document.getElementById("samViewContainer");
  if (!container || !sys) return;

  document.getElementById("samActiveSystem").innerHTML = `
    <strong>System</strong>: ${sys.systemName} (S/N: ${sys.serialNumber}) | <strong>Platform</strong>: ${sys.platform}
  `;

  // 1. Contract & Warranty card
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

  // 2. Hardware Lifecycle Card
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

  // 3. Field Actions Table
  let faRows = "";
  if (sys.fieldActions.length === 0) {
    faRows = `<tr><td colspan="2" style="text-align: center; color: var(--text-muted);">No outstanding field actions. System is up to date.</td></tr>`;
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
}

function renderCSMTab() {
  const sys = state.selectedSystem || state.systems[0];
  const container = document.getElementById("csmViewContainer");
  if (!container || !sys) return;

  document.getElementById("csmActiveSystem").innerHTML = `
    <strong>System</strong>: ${sys.systemName} (S/N: ${sys.serialNumber}) | <strong>Customer</strong>: ${sys.customerName}
  `;

  // Render Efficiency Metrics Card
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

  // Render FabricPool Cloud Adoption Card
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

  // Adoption Checklist
  const checklist = [
    { name: "ONTAP 9.10+ Upgrade", completed: parseFloat(sys.ontapVersion.substring(0,4)) >= 9.10 },
    { name: "Storage Efficiency Enabled", completed: parseFloat(sys.efficiency.ratio.split(":")[0]) > 1.5 },
    { name: "Cloud FabricPool Configured", completed: fpTiered > 0 },
    { name: "Active Service Contracts", completed: sys.contracts.daysRemaining > 0 },
    { name: "Risk Remediation Actioned", completed: sys.risks.length === 0 }
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

function renderSettingsTab() {
  const { refresh } = loadConfig();
  document.getElementById("settingsRefreshToken").value = refresh;
  document.getElementById("settingsMockModeToggle").checked = state.mockMode;
}

// Global active status visual indicators
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

// 6. Navigation Actions & Switch tabs
function switchTab(tabId) {
  state.currentTab = tabId;
  
  // Update sidebar active link state
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.remove("active");
    if (item.getAttribute("data-tab") === tabId) {
      item.classList.add("active");
    }
  });

  // Update visible tab view panels
  document.querySelectorAll(".tab-content").forEach(content => {
    content.classList.remove("active");
  });
  const activeContent = document.getElementById(tabId + "Tab");
  if (activeContent) activeContent.classList.add("active");

  // Trigger tab-specific drawing routines
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
  } else if (tabId === "settings") {
    renderSettingsTab();
  }
}

function selectSystem(serialNumber) {
  const sys = state.systems.find(s => s.serialNumber === serialNumber);
  if (sys) {
    state.selectedSystem = sys;
    // Redirect to TAM page to view the selected system details
    switchTab("tam");
  }
}

// 7. Save Credentials Settings
function saveSettings() {
  const refresh = document.getElementById("settingsRefreshToken").value.trim();
  const mockChecked = document.getElementById("settingsMockModeToggle").checked;

  saveConfig(refresh, "", "0"); // Reset access token when refresh token is edited
  setMockMode(mockChecked);
  
  alert("Settings updated successfully! Persisted in browser localStorage.");
  switchTab("overview");
}

// 8. Search filter updates
function handleSearch(e) {
  state.activeSearchQuery = e.target.value;
  renderOverviewTable();
}

// 9. CSV Report Exporters
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

// 10. Initialization on Load
window.onload = function() {
  loadConfig();
  updateStatusIndicators();
  switchTab("overview");

  // Bind Listeners
  document.getElementById("searchInput").addEventListener("input", handleSearch);
  
  // Set up resize handler to redraw charts cleanly
  window.addEventListener('resize', () => {
    if (state.currentTab === "overview") {
      renderCharts();
    }
  });
};
