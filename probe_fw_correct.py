"""
Test corrected firmware queries using Meta type fields
"""
import json, ssl, urllib.request, urllib.error

with open('aiq_config.json', encoding='utf-8') as f:
    cache = json.load(f)
refresh_token = cache.get('refreshToken', '')

def _http_post_json(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return r.status, json.loads(r.read())

st, tok_resp = _http_post_json('https://api.activeiq.netapp.com/v1/tokens/accessToken', {'refresh_token': refresh_token})
access_token = tok_resp.get('access_token') or tok_resp.get('accessToken') or ''
print(f'Token OK ({len(access_token)} chars)')
headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {access_token}'}

def gql(query):
    req = urllib.request.Request('https://gql.aiq.netapp.com/graphql',
        data=json.dumps({'query': query}).encode(), headers=headers, method='POST')
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as ex:
        return 0, {'error': str(ex)}

# Introspect AutoUpdateSystemsSummary
print("=== AutoUpdateSystemsSummary fields ===")
st, r = gql('{ __type(name: "AutoUpdateSystemsSummary") { fields { name type { name kind ofType { name kind } } } } }')
for f in (r.get('data') or {}).get('__type', {}).get('fields') or []:
    t = f['type']
    tname = t.get('name') or (t.get('ofType') or {}).get('name')
    print(f'  {f["name"]}: {tname}')

# Correct systemFirmwares query using Meta fields
print("\n=== systemFirmwares (Meta fields) pageSize=10 ===")
st, r = gql("""{ systemFirmwares(pageSize: 10) {
  firmwareType firmwareVersion status priority creationDate
  systemsSummary { totalSystems upToDate notUpToDate }
} }""")
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('systemFirmwares') or []
    print(f"  Got {len(items)} items")
    for fw in items:
        print(f"  {json.dumps(fw)}")

# Correct driveFirmwares query
print("\n=== driveFirmwares (Meta fields) pageSize=10 ===")
st, r = gql("""{ driveFirmwares(pageSize: 10) {
  driveModel firmwareVersion status priority creationDate
  systemsSummary { totalSystems upToDate notUpToDate }
} }""")
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('driveFirmwares') or []
    print(f"  Got {len(items)} items")
    for fw in items[:10]:
        print(f"  {json.dumps(fw)}")

# Correct shelfFirmwares query
print("\n=== shelfFirmwares (Meta fields) pageSize=10 ===")
st, r = gql("""{ shelfFirmwares(pageSize: 10) {
  shelfModuleName firmwareVersion status priority creationDate
  systemsSummary { totalSystems upToDate notUpToDate }
} }""")
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('shelfFirmwares') or []
    print(f"  Got {len(items)} items")
    for fw in items[:10]:
        print(f"  {json.dumps(fw)}")

# Correct diskQualificationPackages query
print("\n=== diskQualificationPackages (Meta fields) pageSize=10 ===")
st, r = gql("""{ diskQualificationPackages(pageSize: 10) {
  version status priority creationDate
  systemsSummary { totalSystems upToDate notUpToDate }
} }""")
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('diskQualificationPackages') or []
    print(f"  Got {len(items)} items")
    for fw in items[:10]:
        print(f"  {json.dumps(fw)}")

# Test per-system firmware on a larger page
print("\n=== systems(pageSize=10) -> systemFirmware + motherboardFirmware + driveFirmware + shelves ===")
st, r = gql("""{ systems(pageSize: 10) { systems { serialNumber systemName ... on ONTAPSystem {
  systemFirmware { type currentVersion recommendedVersion autoUpdateEligible postingDate }
  motherboardFirmware { currentVersion recommendedVersion }
  diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
  driveFirmware { driveModel currentVersion recommendedVersion autoUpdateEligible postingDate }
  shelves { serialNumber shelfId hardwareModel { name }
    shelfFirmware { currentVersion recommendedVersion autoUpdateEligible postingDate
      hardwareModel { name } moduleHardwareModel { name }
    }
    drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } }
  }
} } } }""")
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    systems = (r.get('data') or {}).get('systems', {}).get('systems', [])
    print(f"  Systems returned: {len(systems)}")
    for s in systems[:3]:
        sfw = s.get('systemFirmware') or {}
        mbfw = s.get('motherboardFirmware') or {}
        dqp = s.get('diskQualificationPackage') or {}
        drivefw = s.get('driveFirmware') or []
        shelves = s.get('shelves') or []
        print(f"  SN {s.get('serialNumber')} {s.get('systemName','')}")
        print(f"    SP/BMC: {sfw.get('type','')} current={sfw.get('currentVersion','')} rec={sfw.get('recommendedVersion','')}")
        print(f"    Motherboard: current={mbfw.get('currentVersion','')} rec={mbfw.get('recommendedVersion','')}")
        print(f"    DQP: current={dqp.get('currentVersion','')} rec={dqp.get('recommendedVersion','')}")
        print(f"    Drive FW count: {len(drivefw) if isinstance(drivefw, list) else type(drivefw).__name__}")
        print(f"    Shelves: {len(shelves)}")
        for sh in shelves[:2]:
            shfw = sh.get('shelfFirmware') or {}
            drives = sh.get('drives') or {}
            print(f"      Shelf {sh.get('shelfId')} {sh.get('hardwareModel',{}).get('name','')}: fw={json.dumps(shfw)[:120]} drives={drives.get('totalCount',0)}")
