"""
Print the exact GQL query that server.py sends during harvest, to check
if capacity fields are actually included in the query text.
"""
import sys
sys.path.insert(0, r'G:\My Drive\AntiGravity\AIQscraper')

# Import server and extract the FIELDS strings
# We need to simulate what _do_full_harvest does to build the field strings
import server as srv
import json
from pathlib import Path

# Read config to get token
CONFIG_PATH = Path(r'G:\My Drive\AntiGravity\AIQscraper\aiq_config.json')
cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
refresh_token = cfg.get('refreshToken') or cfg.get('refresh_token', '')

from server import _http, _gql, REST_BASE

status, raw = _http('POST', f'{REST_BASE}/v1/tokens/accessToken',
    {'Content-Type': 'application/json', 'Accept': 'application/json'},
    {'refresh_token': refresh_token})
token_data = json.loads(raw.decode('utf-8', errors='replace'))
token = token_data.get('access_token')
print(f'Token: {token[:12]}...')

# Now replicate the query construction from _do_full_harvest
# The field strings are defined inside _do_full_harvest, so we need to reproduce them
# Let me grab the actual field strings from the function

import inspect
src = inspect.getsource(srv._do_full_harvest)

# Find SYSTEMS_FIELDS_TAM definition in source
idx_tam = src.find('SYSTEMS_FIELDS_TAM = """')
idx_tam_end = src.find('# ── TAM_SAFE:')
if idx_tam >= 0:
    tam_section = src[idx_tam:idx_tam+2000]
    print('\n=== SYSTEMS_FIELDS_TAM (first 500 chars) ===')
    # Extract the actual string value
    start = tam_section.find('"""') + 3
    end = tam_section.find('"""', start)
    tam_fields = tam_section[start:end]
    print(repr(tam_fields[:200]))
    print('...')
    print(repr(tam_fields[-100:]))
    
    # Build the exact query
    query_text = """{\n  systems(pageSize: 2) {\n    totalCount cursor\n    systems {""" + tam_fields + """\n    }\n  }\n}"""
    
    print('\n=== ASSEMBLED QUERY (capacity section only) ===')
    cap_idx = query_text.find('capacity')
    if cap_idx >= 0:
        print(query_text[cap_idx-50:cap_idx+300])
    else:
        print('WARNING: "capacity" not found in assembled query!')
    
    print('\n=== Running query ===')
    _, resp = _gql(token, query_text)
    if not isinstance(resp, dict):
        print('Non-dict response:', type(resp))
        sys.exit(1)
    if resp.get('errors'):
        print('GQL ERRORS:', json.dumps(resp['errors'][:2], indent=2))
    else:
        sys_data = (resp.get('data') or {}).get('systems') or {}
        page = sys_data.get('systems') or []
        print(f'Got {len(page)} systems')
        for s in page:
            cap = s.get('capacity') or {}
            phys = cap.get('physical') or {}
            print(f"  {s.get('serialNumber')}: capacity key present={('capacity' in s)}, rawKiB={phys.get('rawMarketingKiB')}")
else:
    print('Could not find SYSTEMS_FIELDS_TAM in source')
