"""Probe DriveSummary and available drive firmware fields."""
import json, sys
sys.path.insert(0, '.')
from server import _http, _gql, REST_BASE

cfg = json.loads(open('aiq_config.json').read())
_, tok_raw = _http('POST', REST_BASE+'/v1/tokens/accessToken',
    {'Content-Type': 'application/json', 'Accept': 'application/json'},
    {'refresh_token': cfg['refreshToken']})
token = json.loads(tok_raw)['access_token']
print(f'Token OK ({len(token)} chars)')

def gq(q):
    _, r = _gql(token, q)
    return r

def probe_type(tn):
    q = '{ __type(name: "' + tn + '") { fields { name type { name kind ofType { name kind } } } } }'
    r = gq(q)
    fields = ((r.get('data') or {}).get('__type') or {}).get('fields') or []
    if not fields:
        print(f'  (type not found)')
        return
    for f in fields:
        t = f['type']
        tname = t.get('name') or (t.get('ofType') or {}).get('name') or '?'
        print(f'  {f["name"]}: {tname} ({t["kind"]})')

print('\n=== DriveSummary ===')
probe_type('DriveSummary')

print('\n=== DrivesSummary ===')
probe_type('DrivesSummary')

# Live query - drivesSummary with subfields probe
print('\n=== ONTAPSystem -> drivesSummary subfields ===')
# First see what fields drivesSummary accepts
for subfield in ['totalCount', 'count', 'drives', 'items', 'summary', 'versions', 'firmwares']:
    q = '{ systems(pageSize: 1) { systems { serialNumber ... on ONTAPSystem { drivesSummary { ' + subfield + ' } } } } }'
    r = gq(q)
    if r.get('errors'):
        print(f'  {subfield}: ERROR - {r["errors"][0]["message"][:100]}')
    else:
        s = ((r.get('data') or {}).get('systems', {}).get('systems') or [{}])[0]
        ds = s.get('drivesSummary') or {}
        print(f'  {subfield}: OK -> {json.dumps(ds)[:120]}')

# Try drives with full subfields
print('\n=== systems shelves drives firmware ===')
q = '''{ systems(pageSize: 3) { systems { serialNumber ... on ONTAPSystem {
  systemFirmware { type currentVersion recommendedVersion autoUpdateEligible postingDate }
  motherboardFirmware { currentVersion recommendedVersion }
  diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
  shelves {
    shelfId serialNumber
    hardwareModel { name endOfAvailability endOfHwSupport }
    moduleHardwareModel { name }
    drives { totalCount drives { firmwareRevision vendor hardwareModel { name type } } }
  }
} } } }'''
r = gq(q)
if r.get('errors'):
    for e in r['errors']:
        print(f'  ERROR: {e["message"][:300]}')
else:
    systems = ((r.get('data') or {}).get('systems', {}).get('systems') or [])
    print(f'Systems: {len(systems)}')
    for s in systems[:2]:
        sfw = s.get('systemFirmware') or {}
        mbfw = s.get('motherboardFirmware') or {}
        dqp = s.get('diskQualificationPackage') or {}
        shelves = s.get('shelves') or []
        print(f'\n  SN={s.get("serialNumber")}')
        print(f'    SP/BMC: type={sfw.get("type")} cur={sfw.get("currentVersion")} rec={sfw.get("recommendedVersion")} autoUpdate={sfw.get("autoUpdateEligible")}')
        print(f'    Motherboard: cur={mbfw.get("currentVersion")} rec={mbfw.get("recommendedVersion")}')
        print(f'    DQP: cur={dqp.get("currentVersion")} rec={dqp.get("recommendedVersion")} autoUpdate={dqp.get("autoUpdateEligible")}')
        print(f'    Shelves: {len(shelves)}')
        # Collect all unique drive firmware versions
        drive_fw_map = {}  # model -> {fw_versions}
        for sh in shelves:
            drives = sh.get('drives') or {}
            for d in (drives.get('drives') or []):
                m = (d.get('hardwareModel') or {}).get('name', 'unknown')
                fw = d.get('firmwareRevision', '')
                if m not in drive_fw_map:
                    drive_fw_map[m] = set()
                drive_fw_map[m].add(fw)
        print(f'    Unique drive models: {len(drive_fw_map)}')
        for model, fwv in list(drive_fw_map.items())[:5]:
            print(f'      {model}: fw versions = {fwv}')
