"""
Probe GQL schema for StorageGRID-related types: grid topology (sites, nodes),
ILM (policies/rules), tenants, and anything else beyond the grid-capacity
fields this app already harvests (gridId, gridName, installedNodeCount,
licenseCapacity, gridCapacity -- see server.py's ESERIES_CAP_FIELDS).

Must be run from an environment with a real aiq_config.json (refreshToken)
and network access to api.activeiq.netapp.com / gql.aiq.netapp.com -- it
cannot be run from the cloud session that wrote it (no token, no network
path to those hosts from here; see CLAUDE.md's 2026-10-02 handoff).

Usage: python tools/probe_storagegrid_schema.py
(run from the repo root, same as the other tools/probe_*.py scripts)
"""
import json, ssl, urllib.request, urllib.error

with open('aiq_config.json', encoding='utf-8') as f:
    cfg = json.load(f)
refresh_token = cfg.get('refreshToken') or cfg.get('refresh_token', '')


def post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return r.status, json.loads(r.read())


st, tok = post('https://api.activeiq.netapp.com/v1/tokens/accessToken', {'refresh_token': refresh_token})
token = tok.get('access_token', '')
print(f'Token OK ({len(token)} chars)')
headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}

GQL_URL = 'https://gql.aiq.netapp.com/graphql'


def gql(query):
    req = urllib.request.Request(GQL_URL,
        data=json.dumps({'query': query}).encode(), headers=headers, method='POST')
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def probe_type(type_name, depth2=True):
    inner = 'name kind ofType { name kind }' if depth2 else 'name kind'
    q = '{ __type(name: "' + type_name + '") { kind fields { name type { ' + inner + ' } } } }'
    st, r = gql(q)
    if r.get('errors'):
        print(f'  ERROR: {r["errors"][0].get("message","")[:200]}')
        return None
    t = (r.get('data') or {}).get('__type')
    if not t:
        print('  (type not found)')
        return None
    print(f'  kind={t.get("kind")}')
    for f in (t.get('fields') or []):
        ft = f['type']
        tn = ft.get('name') or (ft.get('ofType') or {}).get('name') or '?'
        print(f'  {f["name"]}: {tn} ({ft.get("kind")})')
    return t


# ── 1. Full schema type-name sweep, filtered by keyword ──
# This is the part that doesn't require guessing exact type names: list
# EVERY type in the schema whose name contains one of these substrings, so
# a type like "GridTopologySite" or "InformationLifecycleRule" turns up
# even if the exact name doesn't match common StorageGRID/Grid-Manager
# terminology below.
print('\n=== 1. Schema-wide type names matching storagegrid/ilm/tenant/site/bucket/node/alarm ===')
st, r = gql('{ __schema { types { name kind } } }')
if r.get('errors'):
    print(f'  ERROR: {r["errors"][0].get("message","")[:300]}')
else:
    all_types = (r.get('data') or {}).get('__schema', {}).get('types', [])
    print(f'  Total types in schema: {len(all_types)}')
    keywords = ['storagegrid', 'grid', 'ilm', 'tenant', 'site', 'bucket', 'node', 'alarm',
                'topology', 'policy', 'lifecycle', 'erasure', 'replication', 's3']
    matches = sorted({t['name'] for t in all_types
                       if t.get('name') and not t['name'].startswith('__')
                       and any(k in t['name'].lower() for k in keywords)})
    for name in matches:
        print(f'  - {name}')

# ── 2. The StorageGrid type itself, full field list ──
print('\n=== 2. StorageGrid (full field list) ===')
sg_type = probe_type('StorageGrid')

# ── 3. Plausible related type names (Grid Manager domain terms) ──
# Probed whether or not they showed up in step 1, in case naming differs
# from what step 1's keyword list catches.
print('\n=== 3. Plausible related types (ILM / topology / tenant) ===')
candidate_types = [
    'StorageGridNode', 'GridNode', 'Node',
    'StorageGridSite', 'GridSite',
    'IlmPolicy', 'ILMPolicy', 'InformationLifecycleManagementPolicy',
    'IlmRule', 'ILMRule',
    'StorageGridTenant', 'Tenant',
    'S3Bucket', 'Bucket',
    'StorageGridAlarm', 'Alarm',
    'ErasureCodingProfile',
    'StorageGridCertificate',
]
for t in candidate_types:
    print(f'\n--- {t} ---')
    probe_type(t, depth2=False)

# ── 4. Live sample: every currently-known-safe StorageGrid field, plus the
#      __typename, against a few real systems, to confirm (not just schema
#      presence) that any newly found fields actually carry data ──
print('\n=== 4. Live StorageGrid sample (first 3 grids found) ===')
# NOTE: adjust the query below once step 1-3 reveal what's actually there --
# this only requests what's already known-good (server.py's ESERIES_CAP_FIELDS)
# as a baseline connectivity check, not a claim about what's new.
q = '''{
  systems(pageSize: 20) {
    systems {
      serialNumber
      systemName
      ... on StorageGrid {
        gridId gridName installedNodeCount licenseCapacity
      }
    }
  }
}'''
st, r = gql(q)
print(f'HTTP {st}')
if r.get('errors'):
    for e in r['errors']:
        print(f'  ERROR: {e.get("message","")[:300]}')
else:
    systems = (r.get('data') or {}).get('systems', {}).get('systems', [])
    grids = [s for s in systems if s.get('gridId') is not None]
    print(f'  Systems returned: {len(systems)}, StorageGrid grids among them: {len(grids)}')
    for g in grids[:3]:
        print(f'    {g}')
