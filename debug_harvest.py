"""
Standalone harvest debug: calls the harvest function directly and checks if
capacity is populated in the result. Prints detailed debug around capacity extraction.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, r'G:\My Drive\AntiGravity\AIQscraper')
from server import _http, _gql, REST_BASE

CONFIG_PATH = Path(r'G:\My Drive\AntiGravity\AIQscraper\aiq_config.json')
cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
refresh_token = cfg.get('refreshToken') or cfg.get('refresh_token', '')

# Get token
status, raw = _http('POST', f'{REST_BASE}/v1/tokens/accessToken',
    {'Content-Type': 'application/json', 'Accept': 'application/json'},
    {'refresh_token': refresh_token})
token_data = json.loads(raw.decode('utf-8', errors='replace'))
token = token_data.get('access_token')
print(f'Token: {token[:12]}...')

# Use exact same query as SYSTEMS_FIELDS_TAM
FIELDS = """
  hostName systemId serialNumber osVersion recommendedOSVersion
  type platformType productType ageInYears serviceTier
  techRefreshStatus incumbentResellerCompany
  isFabricPool hasPvr
  customer { id name }
  site { id name city countryCode postalCode state }
  hardwareModel { name modelRevision endOfAvailability endOfSupport }
  ... on ONTAPSystem {
    isMetroCluster isAllFlashOptimized operatingMode
    propensityCategory serviceProcessorIPAddress
    capacity {
      physical { rawMarketingKiB usedKiB usedWithoutSnapshotsKiB usablePerformanceTierKiB qoqUtilizationPercentage yoyUtilizationPercentage utilizationPercentage }
      logical { usedKiB usedWithoutSnapshotsClonesKiB }
      efficiency {
        ratio { efficiencyRatio dataReductionRatio withSnapshotRatio }
        saved { savedKiB deDuplicationSavedKiB compactionSavedKiB }
      }
      reportedOn
    }
    monthlyCapacity {
      month
      physical { rawMarketingKiB usedKiB utilizationPercentage qoqUtilizationPercentage }
      logical { usedKiB }
      efficiency { ratio { efficiencyRatio dataReductionRatio } }
    }
  }
"""

query_text = '{ systems(pageSize: 5) { totalCount cursor systems {' + FIELDS + '} } }'
print('\nRunning full TAM systems query (5 systems)...')
_, resp = _gql(token, query_text)

if not isinstance(resp, dict):
    print(f'Non-dict: {type(resp)}')
    sys.exit(1)

if resp.get('errors'):
    print('GQL errors:', json.dumps(resp['errors'][:2], indent=2))
    sys.exit(1)

sys_data = (resp.get('data') or {}).get('systems') or {}
page_systems = sys_data.get('systems') or []
print(f'Total in scope: {sys_data.get("totalCount")}')
print(f'Systems on page: {len(page_systems)}')

print('\n--- Capacity extraction (mirroring server.py transform) ---')
nonzero = 0
for s in page_systems:
    serial = s.get('serialNumber', '')
    cap = s.get('capacity') or {}
    cap_phys = cap.get('physical') or {}
    raw_kib = cap_phys.get('rawMarketingKiB') or 0
    used_kib = cap_phys.get('usedKiB') or 0
    usbl_kib = cap_phys.get('usablePerformanceTierKiB') or 0
    util_pct = cap_phys.get('utilizationPercentage') or 0
    monthly = s.get('monthlyCapacity') or []
    
    raw_tb = round(raw_kib / (1024**3), 3) if raw_kib else 0
    used_tb = round(used_kib / (1024**3), 3) if used_kib else 0
    
    status_str = "✓ HAS DATA" if raw_kib > 0 else "✗ ZERO"
    print(f'  {serial:20s} ({s.get("hostName","")}) {status_str}')
    print(f'    cap keys: {list(cap.keys())}')
    print(f'    cap_phys: rawKiB={raw_kib}, usedKiB={used_kib}, util={util_pct:.4f}%')
    print(f'    => clusterRawCapacityTB={raw_tb}, clusterPhysicalUsedTB={used_tb}')
    print(f'    monthly: {len(monthly)} months')
    if raw_kib > 0:
        nonzero += 1

print(f'\nSystems with non-zero rawKiB: {nonzero}/{len(page_systems)}')
