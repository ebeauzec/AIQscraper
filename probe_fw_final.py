"""
Final targeted firmware probe - discover exact working fields
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

# Discover actual fields on AutoUpdateSystemsSummary
print("=== AutoUpdateSystemsSummary actual fields ===")
st, r = gql('{ __type(name: "AutoUpdateSystemsSummary") { fields { name } } }')
flds = (r.get('data') or {}).get('__type', {}).get('fields') or []
print(f"  Fields: {[f['name'] for f in flds]}")

# Discover ONTAPSystem fields related to firmware
print("\n=== ONTAPSystem firmware-related fields ===")
st, r = gql('{ __type(name: "ONTAPSystem") { fields { name type { name kind ofType { name kind } } } } }')
flds = (r.get('data') or {}).get('__type', {}).get('fields') or []
for f in flds:
    if any(x in f['name'].lower() for x in ('firmware', 'drive', 'shelf', 'disk', 'bios', 'sp')):
        t = f['type']
        tname = t.get('name') or (t.get('ofType') or {}).get('name')
        print(f"  {f['name']}: {tname} ({t.get('kind')})")

# Discover Shelf fields
print("\n=== Shelf fields ===")
st, r = gql('{ __type(name: "Shelf") { fields { name type { name kind ofType { name kind } } } } }')
flds = (r.get('data') or {}).get('__type', {}).get('fields') or []
for f in flds:
    t = f['type']
    tname = t.get('name') or (t.get('ofType') or {}).get('name')
    print(f"  {f['name']}: {tname} ({t.get('kind')})")

# Discover Drive fields
print("\n=== Drive fields ===")
st, r = gql('{ __type(name: "Drive") { fields { name type { name kind ofType { name kind } } } } }')
flds = (r.get('data') or {}).get('__type', {}).get('fields') or []
for f in flds:
    t = f['type']
    tname = t.get('name') or (t.get('ofType') or {}).get('name')
    print(f"  {f['name']}: {tname} ({t.get('kind')})")

# systemFirmwares without systemsSummary
print("\n=== systemFirmwares(pageSize:10) - no systemsSummary ===")
st, r = gql('{ systemFirmwares(pageSize: 10) { firmwareType firmwareVersion status priority creationDate } }')
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('systemFirmwares') or []
    print(f"  Got {len(items)} items")
    for fw in items:
        print(f"  {json.dumps(fw)}")

# driveFirmwares without systemsSummary
print("\n=== driveFirmwares(pageSize:10) - no systemsSummary ===")
st, r = gql('{ driveFirmwares(pageSize: 10) { driveModel firmwareVersion status priority creationDate } }')
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('driveFirmwares') or []
    print(f"  Got {len(items)} items")
    for fw in items[:10]:
        print(f"  {json.dumps(fw)}")

# shelfFirmwares without systemsSummary
print("\n=== shelfFirmwares(pageSize:10) - no systemsSummary ===")
st, r = gql('{ shelfFirmwares(pageSize: 10) { shelfModuleName firmwareVersion status priority creationDate } }')
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('shelfFirmwares') or []
    print(f"  Got {len(items)} items")
    for fw in items[:10]:
        print(f"  {json.dumps(fw)}")

# diskQualificationPackages without systemsSummary
print("\n=== diskQualificationPackages(pageSize:10) - no systemsSummary ===")
st, r = gql('{ diskQualificationPackages(pageSize: 10) { version status priority creationDate } }')
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('diskQualificationPackages') or []
    print(f"  Got {len(items)} items")
    for fw in items[:10]:
        print(f"  {json.dumps(fw)}")

# Per-system firmware - using the confirmed-working query from probe_fw_root.py section G
print("\n=== systems(pageSize:5) -> all firmware fields ===")
st, r = gql("""{ systems(pageSize: 5) { systems { serialNumber ... on ONTAPSystem {
  systemFirmware { type currentVersion recommendedVersion autoUpdateEligible postingDate }
  motherboardFirmware { currentVersion recommendedVersion }
  diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
  driveFirmware { driveModel currentVersion recommendedVersion autoUpdateEligible postingDate }
  shelves { serialNumber shelfId hardwareModel { name }
    drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } }
  }
} } } }""")
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    systems = (r.get('data') or {}).get('systems', {}).get('systems', [])
    print(f"  Systems: {len(systems)}")
    for s in systems[:3]:
        sfw = s.get('systemFirmware') or {}
        mbfw = s.get('motherboardFirmware') or {}
        dqp = s.get('diskQualificationPackage') or {}
        drfw = s.get('driveFirmware') or []
        shelves = s.get('shelves') or []
        print(f"\n  SN {s.get('serialNumber')}")
        print(f"    SP/BMC: type={sfw.get('type','')} cur={sfw.get('currentVersion','')} rec={sfw.get('recommendedVersion','')}")
        print(f"    Motherboard: cur={mbfw.get('currentVersion','')} rec={mbfw.get('recommendedVersion','')}")
        print(f"    DQP: cur={dqp.get('currentVersion','')} rec={dqp.get('recommendedVersion','')}")
        print(f"    Drive FW entries: {len(drfw) if isinstance(drfw, list) else type(drfw).__name__}")
        if isinstance(drfw, list):
            for d in drfw[:3]:
                print(f"      Drive: {d.get('driveModel','')} cur={d.get('currentVersion','')} rec={d.get('recommendedVersion','')}")
        print(f"    Shelves: {len(shelves)}")
        for sh in shelves[:2]:
            drives = sh.get('drives') or {}
            print(f"      Shelf {sh.get('shelfId')} {sh.get('hardwareModel',{}).get('name','')}: {drives.get('totalCount',0)} drives")
            for d in (drives.get('drives') or [])[:2]:
                print(f"        Drive: {d.get('hardwareModel',{}).get('name','')} fw={d.get('firmwareRevision','')} vendor={d.get('vendor','')}")
