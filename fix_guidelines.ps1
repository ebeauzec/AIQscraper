$filePath = 'g:\My Drive\AntiGravity\AIQscraper\app.js'
$enc = [System.Text.Encoding]::UTF8

# Read all lines
$lines = [System.IO.File]::ReadAllLines($filePath, $enc)
Write-Host "Total lines: $($lines.Length)"
Write-Host "Line 14852 (index 14851): $($lines[14851])"
Write-Host "Line 14884 (index 14883): $($lines[14883])"

# The new content to replace lines 14852-14884 (1-indexed), i.e. indices 14851-14883
$newSection = @'
      ${(() => {
        const custNames = [...new Set(targetSystems.map(s => s.customerName).filter(Boolean))];
        const custLabel = custNames.length === 1 ? custNames[0] : custNames.length > 1 ? custNames.join(' / ') : 'Selected Account';
        const sysCount  = targetSystems.length;
        const sysNames  = targetSystems.map(s => s.systemName);
        const critHighRisks = allRisks.filter(r => r.severity === 'critical' || r.severity === 'high');
        const uniqueRiskDescs = [...new Map(critHighRisks.map(r => [r.description || r.shortName, r])).values()].slice(0, 4);
        const upgradeList = allUpgrades.slice(0, 6);
        const cveIds = [...new Set(allSecurityAdvisories.map(sa => { const m = (sa.id || sa.cve || '').match(/CVE-[0-9]{4}-[0-9]+/); return m ? m[0] : null; }).filter(Boolean))].slice(0, 5);
        const expiringItems = expiringContracts.slice(0, 5);
        const hasMC  = targetSystems.some(s => (s.platform || s.model || '').toLowerCase().includes('metrocluster')) || mcSystems.length > 0;
        const hasASA = targetSystems.some(s => (s.platform || s.model || '').toLowerCase().includes(' asa'));
        const hasVMware = allHypervisors.some(h => /vmware|esxi/i.test(h.type || h.hypervisorType || ''));
        const hasK8s    = allHypervisors.some(h => /kubernetes|trident|k8s/i.test(h.type || h.hypervisorType || ''));
        const showHyper = hasVMware || hasK8s;

        let secA = '<div style="margin-bottom:18px;">';
        secA += '<h4 style="font-size:0.95rem;color:var(--accent-cyan);margin-bottom:6px;">A. Pre-Change Assessment \u2014 ' + custLabel + '</h4>';
        secA += '<p style="font-size:0.85rem;line-height:1.4;color:var(--text-secondary);margin-bottom:10px;"><strong>' + sysCount + ' system' + (sysCount !== 1 ? 's' : '') + ' in scope:</strong> ' + sysNames.map(n => '<code style="font-size:0.78rem;background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:3px;">' + n + '</code>').join(' ') + '</p>';
        secA += '<ul style="margin-left:20px;font-size:0.85rem;color:var(--text-secondary);line-height:1.5;margin-top:6px;">';
        if (upgradeList.length > 0) {
          secA += '<li><strong>OS Upgrade Pre-checks</strong>: Before upgrading, run <code>system health alert show</code> and confirm zero HA takeover blocks on:<ul style="margin-top:4px;margin-left:16px;">' + upgradeList.map(u => '<li><code>' + u.systemName + '</code> \u2014 ' + (u.currentVersion || 'current') + ' \u2192 <strong>' + u.targetVersion + '</strong>' + (u.upgradeHops && u.upgradeHops.length > 1 ? ' (via ' + u.upgradeHops.join(' \u2192 ') + ')' : '') + '</li>').join('') + '</ul></li>';
        }
        if (critHighRisks.length > 0) {
          secA += '<li><strong>Outstanding Critical/High Risks (' + critHighRisks.length + ' total)</strong>: Resolve before scheduling maintenance:<ul style="margin-top:4px;margin-left:16px;">' + uniqueRiskDescs.map(r => '<li><code>' + r.systemName + '</code> \u2014 ' + (r.description || r.shortName || r.category) + '</li>').join('') + (critHighRisks.length > 4 ? '<li style="color:var(--text-muted);">\u2026and ' + (critHighRisks.length - 4) + ' more (see Section 2)</li>' : '') + '</ul></li>';
        }
        if (hasMC) {
          secA += '<li><strong>MetroCluster Change Protocol</strong>: For MC systems (' + (mcSystems.length > 0 ? mcSystems.join(', ') : 'in scope') + '), upgrade one site at a time. Validate <code>metrocluster check run</code> and <code>storage failover show</code> before proceeding to partner site. Confirm Mediator/Tiebreaker reachability post-change.</li>';
        }
        if (hasASA) {
          secA += '<li><strong>ASA SAN Pre-checks</strong>: Verify all LUN paths are active (<code>network interface show -role data</code>) and iSCSI/FC sessions are balanced before making configuration changes on ASA platforms in scope.</li>';
        }
        if (switchAlerts.length > 0) {
          const swNames = [...new Set(switchAlerts.map(sw => sw.systemName))];
          secA += '<li><strong>Switch Firmware (' + switchAlerts.length + ' alert' + (switchAlerts.length !== 1 ? 's' : '') + ')</strong>: Non-optimal switch status on ' + swNames.map(n => '<code>' + n + '</code>').join(', ') + '. Verify port redundancy with <code>show interface status</code> before ISSU upgrades.</li>';
        }
        secA += '<li><strong>Maintenance Window Scheduling</strong>: All disk replacement, firmware, and switch modifications should be scheduled during off-peak periods. Confirm with ' + custLabel + ' site contacts before booking windows.</li>';
        secA += '</ul></div>';

        let secB = '';
        if (showHyper) {
          secB = '<div style="margin-bottom:18px;"><h4 style="font-size:0.95rem;color:var(--accent-cyan);margin-bottom:6px;">B. Workload &amp; Hypervisor Environment</h4><p style="font-size:0.85rem;line-height:1.4;color:var(--text-secondary);">Active IQ telemetry indicates the following hypervisor workloads are attached to systems in scope:</p><ul style="margin-left:20px;font-size:0.85rem;color:var(--text-secondary);line-height:1.5;margin-top:6px;">';
          if (hasVMware) secB += '<li><strong>VMware ESXi</strong>: Confirm hosts use <code>VMW_PSP_RR</code> Round Robin with IOPS limit=1. Do not take ONTAP nodes offline without first migrating VM workloads via vMotion.</li>';
          if (hasK8s)   secB += '<li><strong>Kubernetes / Astra Trident</strong>: Coordinate Trident driver upgrades alongside any ONTAP changes. Validate PVC mounts with <code>kubectl get pvc --all-namespaces</code> before and after changes.</li>';
          secB += '</ul></div>';
        }

        const actions = [];
        const label = showHyper ? 'C' : 'B';
        if (critHighRisks.length > 0) {
          const critCount = critHighRisks.filter(r => r.severity === 'critical').length;
          const highCount = critHighRisks.filter(r => r.severity === 'high').length;
          const affected  = [...new Set(critHighRisks.map(r => r.systemName))];
          const sevStr = (critCount > 0 ? critCount + ' critical' : '') + (critCount > 0 && highCount > 0 ? ' and ' : '') + (highCount > 0 ? highCount + ' high' : '');
          actions.push('<strong>Remediate ' + sevStr + ' risk' + (critHighRisks.length !== 1 ? 's' : '') + '</strong> on ' + affected.map(n => '<code>' + n + '</code>').join(', ') + ' \u2014 raise internal change tickets referencing Section 2 remediation plans.');
        }
        if (cveIds.length > 0) {
          actions.push('<strong>Apply security patches</strong> for ' + cveIds.length + ' CVE' + (cveIds.length !== 1 ? 's' : '') + ' (' + cveIds.join(', ') + ') \u2014 review Section 3 for NetApp advisory links and fix version targets.');
        } else if (allSecurityAdvisories.length > 0) {
          actions.push('<strong>Review ' + allSecurityAdvisories.length + ' security bulletin' + (allSecurityAdvisories.length !== 1 ? 's' : '') + '</strong> in Section 3 and schedule micro-patches or workaround mitigations.');
        }
        if (upgradeList.length > 0) {
          const osTargets = [...new Set(upgradeList.map(u => u.targetVersion).filter(Boolean))];
          actions.push('<strong>Schedule OS upgrades</strong> for ' + upgradeList.length + ' system' + (upgradeList.length !== 1 ? 's' : '') + ' to ' + osTargets.join(' / ') + ' \u2014 complete pre-change checks above before booking windows with ' + custLabel + '.');
        }
        if (expiringItems.length > 0) {
          const soonest = expiringItems.slice().sort((a, b) => (a.daysRemaining || 0) - (b.daysRemaining || 0))[0];
          actions.push('<strong>Renew support contracts</strong> for ' + expiringItems.length + ' system' + (expiringItems.length !== 1 ? 's' : '') + ' \u2014 soonest: <code>' + soonest.systemName + '</code> in ' + soonest.daysRemaining + ' day' + (soonest.daysRemaining !== 1 ? 's' : '') + '. Coordinate with ' + custLabel + ' procurement contacts.');
        }
        if (allSupportCases.length > 0) {
          const openCases = allSupportCases.filter(c => (c.status || '').toLowerCase() !== 'closed');
          if (openCases.length > 0) actions.push('<strong>Follow up on ' + openCases.length + ' open support case' + (openCases.length !== 1 ? 's' : '') + '</strong> \u2014 verify resolution progress and confirm site access or part delivery with ' + custLabel + ' contacts (see Section 4).');
        }
        if (switchAlerts.length > 0) {
          const swn = [...new Set(switchAlerts.map(sw => sw.systemName))];
          actions.push('<strong>Resolve switch alerts</strong> on ' + swn.map(n => '<code>' + n + '</code>').join(', ') + ' \u2014 details in Section 6. Schedule ISSU firmware update during agreed maintenance window.');
        }
        if (actions.length === 0) actions.push('<strong>Continue routine monitoring</strong> \u2014 no critical actions outstanding. Schedule a follow-up Active IQ review in 30 days.');

        const secC = '<div><h4 style="font-size:0.95rem;color:var(--accent-cyan);margin-bottom:6px;">' + label + '. Priority Action Items for ' + custLabel + '</h4><ol style="margin-left:20px;font-size:0.85rem;color:var(--text-secondary);line-height:1.6;margin-top:6px;">' + actions.map(a => '<li>' + a + '</li>').join('') + '</ol></div>';
        return secA + secB + secC;
      })()}
'@

# Split newSection into lines
$newLines = $newSection -split "`r`n|`n"
# Remove the leading empty element if @' starts with newline
if ($newLines[0] -eq '') { $newLines = $newLines[1..($newLines.Length-1)] }
# Remove the trailing empty element if @' ends with newline  
if ($newLines[-1] -eq '') { $newLines = $newLines[0..($newLines.Length-2)] }

Write-Host "New section lines: $($newLines.Length)"

# Splice: keep lines before 14852 (index 14851), insert new, keep lines after 14884 (index 14883)
$before = $lines[0..14850]
$after  = $lines[14884..($lines.Length-1)]
$result = $before + $newLines + $after

Write-Host "Result lines: $($result.Length)"

[System.IO.File]::WriteAllLines($filePath, $result, $enc)
Write-Host "Done! File written."
