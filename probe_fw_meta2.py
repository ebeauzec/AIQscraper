"""
Introspect the firmware Meta types and test corrected queries
"""
import json, ssl, urllib.request

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

# Introspect the Meta types to discover actual field names
for typename in ['SystemFirmwareMeta', 'DriveFirmwareMeta', 'ShelfFirmwareMeta', 'DiskQualificationPackageMeta',
                 'SystemFirmware', 'DriveFirmware', 'ShelfFirmware', 'DiskQualificationPackage']:
    st, r = gql(f'{{ __type(name: "{typename}") {{ fields {{ name type {{ name kind ofType {{ name kind }} }} }} }} }}')
    fields = (r.get('data') or {}).get('__type', {}).get('fields') or []
    if fields:
        print(f'--- {typename} ---')
        for f in fields:
            t = f['type']
            tname = t.get('name') or (t.get('ofType') or {}).get('name')
            print(f'  {f["name"]}: {tname} ({t.get("kind")})')
    else:
        errs = r.get('errors', [])
        print(f'--- {typename}: NO FIELDS or error: {[e.get("message","")[:100] for e in errs]}')

# Test systemFirmwares with correct field structure (no cursor/totalCount)
print("\n=== systemFirmwares minimal query ===")
st, r = gql('{ systemFirmwares(pageSize: 5) { type currentVersion recommendedVersion autoUpdateEligible postingDate } }')
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('systemFirmwares') or []
    print(f"  Got {len(items)} items")
    for fw in items[:5]:
        print(f"  {json.dumps(fw)}")

# Test driveFirmwares
print("\n=== driveFirmwares minimal query ===")
st, r = gql('{ driveFirmwares(pageSize: 5) { currentVersion recommendedVersion autoUpdateEligible driveModel } }')
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('driveFirmwares') or []
    print(f"  Got {len(items)} items")
    for fw in items[:5]:
        print(f"  {json.dumps(fw)}")

# Test shelfFirmwares
print("\n=== shelfFirmwares minimal query ===")
st, r = gql('{ shelfFirmwares(pageSize: 5) { currentVersion recommendedVersion autoUpdateEligible postingDate } }')
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('shelfFirmwares') or []
    print(f"  Got {len(items)} items")
    for fw in items[:5]:
        print(f"  {json.dumps(fw)}")

# Test diskQualificationPackages
print("\n=== diskQualificationPackages minimal query ===")
st, r = gql('{ diskQualificationPackages(pageSize: 5) { currentVersion recommendedVersion autoUpdateEligible } }')
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    items = (r.get('data') or {}).get('diskQualificationPackages') or []
    print(f"  Got {len(items)} items")
    for fw in items[:5]:
        print(f"  {json.dumps(fw)}")

# Test drives with firmwareRevision - try different approach
print("\n=== drives query: systems -> shelves -> drives ===")
st, r = gql("""{ systems(pageSize: 2) { systems { serialNumber ... on ONTAPSystem {
  shelves { serialNumber shelfId hardwareModel { name }
    shelfFirmware { currentVersion recommendedVersion }
    drives { totalCount drives { firmwareRevision vendor hardwareModel { name } diskType } }
  }
} } } }""")
print(f"HTTP {st}")
if r.get('errors'):
    for e in r['errors']:
        print(f"  ERROR: {e.get('message','')[:200]}")
else:
    systems = (r.get('data') or {}).get('systems', {}).get('systems', [])
    for s in systems:
        shelves = s.get('shelves', [])
        print(f"  SN {s.get('serialNumber')}: {len(shelves)} shelves")
        for sh in shelves[:3]:
            drives = sh.get('drives', {})
            dlist = drives.get('drives', [])
            shfw = sh.get('shelfFirmware')
            print(f"    Shelf {sh.get('shelfId')} {sh.get('hardwareModel',{}).get('name','')} - {drives.get('totalCount',0)} drives - shelfFW={json.dumps(shfw)[:80]}")
            for d in dlist[:2]:
                print(f"      Drive: {d.get('hardwareModel',{}).get('name','')} fw={d.get('firmwareRevision','')} type={d.get('diskType','')}")
