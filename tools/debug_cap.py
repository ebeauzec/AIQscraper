"""
Debug: run TAM-like capacity query and print what comes back from s.get('capacity').
"""
import json, sys
from pathlib import Path
sys.path.insert(0, r'G:\My Drive\AntiGravity\AIQscraper')
from server import _http, _gql, REST_BASE

CONFIG_PATH = Path(r'G:\My Drive\AntiGravity\AIQscraper\aiq_config.json')
cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
refresh_token = cfg.get('refreshToken') or cfg.get('refresh_token', '')

status, raw = _http('POST', f'{REST_BASE}/v1/tokens/accessToken',
    {'Content-Type': 'application/json', 'Accept': 'application/json'},
    {'refresh_token': refresh_token})
token_data = json.loads(raw.decode('utf-8', errors='replace'))
token = token_data.get('access_token')
print(f'Token: {token[:12]}...')

# Use EXACT same SYSTEMS_FIELDS_TAM capacity block
FIELDS = """
  hostName systemId serialNumber type
  ... on ONTAPSystem {
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
query_text = '{ systems(pageSize: 3) { totalCount cursor systems {' + FIELDS + '} } }'
print('\nQuerying with TAM capacity fields...')
_, resp = _gql(token, query_text)
if not isinstance(resp, dict):
    print(f'Non-dict response: {type(resp)}, value: {str(resp)[:400]}')
    sys.exit(1)

if resp.get('errors'):
    print('GQL errors:', json.dumps(resp['errors'], indent=2))

sys_data = (resp.get('data') or {}).get('systems') or {}
page_systems = sys_data.get('systems') or []
print(f'Got {len(page_systems)} systems')
for s in page_systems:
    cap = s.get('capacity')
    phys = (cap or {}).get('physical') or {}
    print(f"\n  {s.get('serialNumber')} ({s.get('hostName')}) type={s.get('type')}")
    print(f"  s.keys() has 'capacity': {'capacity' in s}")
    print(f"  cap is None: {cap is None}")
    print(f"  cap: {json.dumps(cap, indent=4) if cap else 'NONE/EMPTY'}")
    raw_kib = phys.get('rawMarketingKiB')
    print(f"  rawMarketingKiB: {raw_kib}")
