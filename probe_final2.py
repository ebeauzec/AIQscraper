"""
Discover all ONTAPSystem fields and test final working firmware query
"""
import json, ssl, urllib.request, urllib.error

with open('aiq_config.json', encoding='utf-8') as f:
    cache = json.load(f)
refresh_token = cache.get('refreshToken', '')

def _post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return r.status, json.loads(r.read())

st, tok = _post('https://api.activeiq.netapp.com/v1/tokens/accessToken', {'refresh_token': refresh_token})
token = tok.get('access_token') or tok.get('accessToken') or ''
headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}

def gql(q):
    req = urllib.request.Request('https://gql.aiq.netapp.com/graphql',
        data=json.dumps({'query': q}).encode(), headers=headers, method='POST')
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

# All ONTAPSystem fields
print('All ONTAPSystem fields:')
st, r = gql('{ __type(name: "ONTAPSystem") { fields { name } } }')
flds = (r.get('data') or {}).get('__type', {}).get('fields') or []
for f in flds:
    print(f'  {f["name"]}')

# Test working systems query with confirmed fields
print()
print('Working per-system firmware + shelves query:')
q = """{ systems(pageSize: 5) { systems {
  serialNumber
  ... on ONTAPSystem {
    systemFirmware { type currentVersion recommendedVersion }
    motherboardFirmware { currentVersion recommendedVersion }
    diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
    shelves {
      shelfId
      hardwareModel { name }
      drives {
        totalCount
        drives { firmwareRevision vendor hardwareModel { name } }
      }
    }
  }
} } }"""
st, r = gql(q)
print(f'HTTP {st}')
if r.get('errors'):
    for e in r['errors']:
        print(f'  ERR: {e["message"][:300]}')
else:
    systems = (r.get('data') or {}).get('systems', {}).get('systems', [])
    print(f'Systems: {len(systems)}')
    for s in systems:
        sfw = s.get('systemFirmware') or {}
        mbfw = s.get('motherboardFirmware') or {}
        dqp = s.get('diskQualificationPackage') or {}
        shelves = s.get('shelves') or []
        print(f'  SN {s.get("serialNumber")}: SP={sfw.get("type","")}/{sfw.get("currentVersion","")} MB={mbfw.get("currentVersion","")} DQP={dqp.get("currentVersion","")} shelves={len(shelves)}')
        for sh in shelves[:2]:
            drives = sh.get('drives') or {}
            dlist = drives.get('drives') or []
            print(f'    Shelf {sh.get("shelfId")} {sh.get("hardwareModel",{}).get("name","")}: {drives.get("totalCount",0)} drives')
            for d in dlist[:3]:
                print(f'      {d.get("hardwareModel",{}).get("name","")} fw={d.get("firmwareRevision","")} vendor={d.get("vendor","")}')
