"""
Probe GQL schema for all firmware-related types to discover what's changed.
"""
import json, ssl, urllib.request, urllib.error

with open('aiq_config.json', encoding='utf-8') as f:
    cfg = json.load(f)
refresh_token = cfg.get('refreshToken', '')

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

def probe_type(type_name):
    q = '{ __type(name: "' + type_name + '") { fields { name type { name kind ofType { name kind } } } } }'
    st, r = gql(q)
    flds = (r.get('data') or {}).get('__type', {})
    if not flds:
        print(f'  (type not found or no fields)')
        return
    for f in (flds.get('fields') or []):
        t = f['type']
        tn = t.get('name') or (t.get('ofType') or {}).get('name') or '?'
        print(f'  {f["name"]}: {tn} ({t.get("kind")})')

types_to_probe = [
    'DrivesSummary', 'FirmwareVersion', 'MotherboardFirmware',
    'ShelfHardwareModel', 'ShelfModuleHardwareModel',
    'DriveHardwareModel', 'DiskQualificationPackage',
    'SystemFirmware', 'DriveFirmware', 'ShelfFirmware',
]

for t in types_to_probe:
    print(f'\n=== {t} ===')
    probe_type(t)

# Also try to fetch a live system with all available firmware fields
print('\n=== Live system firmware query ===')
q = '''{
  systems(pageSize: 3) {
    systems {
      serialNumber
      hostName
      ... on ONTAPSystem {
        systemFirmware { type currentVersion recommendedVersion autoUpdateEligible postingDate }
        motherboardFirmware { currentVersion recommendedVersion }
        diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
        drivesSummary { totalCount }
        shelves {
          shelfId
          serialNumber
          hardwareModel { name endOfAvailability endOfHwSupport }
          moduleHardwareModel { name }
          drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } }
        }
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
    print(f'  Systems: {len(systems)}')
    for s in systems[:2]:
        print(f'\n  SN={s.get("serialNumber")} host={s.get("hostName")}')
        sfw = s.get('systemFirmware') or {}
        mbfw = s.get('motherboardFirmware') or {}
        dqp = s.get('diskQualificationPackage') or {}
        ds = s.get('drivesSummary') or {}
        shelves = s.get('shelves') or []
        print(f'    SP/BMC: type={sfw.get("type")} cur={sfw.get("currentVersion")} rec={sfw.get("recommendedVersion")} autoUpdate={sfw.get("autoUpdateEligible")}')
        print(f'    Motherboard: cur={mbfw.get("currentVersion")} rec={mbfw.get("recommendedVersion")}')
        print(f'    DQP: cur={dqp.get("currentVersion")} rec={dqp.get("recommendedVersion")} autoUpdate={dqp.get("autoUpdateEligible")}')
        print(f'    DrivesSummary: totalCount={ds.get("totalCount")}')
        print(f'    Shelves: {len(shelves)}')
        for sh in shelves[:3]:
            drives = sh.get('drives') or {}
            drv_list = drives.get('drives') or []
            print(f'      Shelf {sh.get("shelfId")} model={sh.get("hardwareModel",{}).get("name")} module={sh.get("moduleHardwareModel",{}).get("name")}')
            print(f'        drives total={drives.get("totalCount")} returned={len(drv_list)}')
            for d in drv_list[:3]:
                print(f'          Drive: model={d.get("hardwareModel",{}).get("name")} fw={d.get("firmwareRevision")} vendor={d.get("vendor")}')
