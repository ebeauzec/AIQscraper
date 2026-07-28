"""Validate corrected firmware GQL query with drivesSummary."""
import json, sys
sys.path.insert(0, '.')
from server import _http, _gql, REST_BASE

cfg = json.loads(open('aiq_config.json').read())
_, tok_raw = _http('POST', REST_BASE+'/v1/tokens/accessToken',
    {'Content-Type': 'application/json', 'Accept': 'application/json'},
    {'refresh_token': cfg['refreshToken']})
token = json.loads(tok_raw)['access_token']

q = """{
  systems(pageSize: 5) {
    systems {
      serialNumber hostName
      ... on ONTAPSystem {
        systemFirmware { type currentVersion recommendedVersion autoUpdateEligible postingDate }
        motherboardFirmware { currentVersion recommendedVersion postingDate }
        diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
        drivesSummary {
          driveModel model count
          firmware { currentVersion recommendedVersion autoUpdateEligible postingDate }
        }
        shelves {
          shelfId serialNumber
          hardwareModel { name endOfAvailability endOfHwSupport }
          moduleHardwareModel { name }
          drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } }
        }
      }
    }
  }
}"""

_, r = _gql(token, q)
if r.get('errors'):
    for e in r['errors']:
        print('ERROR:', e['message'][:200])
    sys.exit(1)

systems = ((r.get('data') or {}).get('systems', {}).get('systems') or [])
print(f'Systems: {len(systems)}')
for s in systems[:3]:
    sfw = s.get('systemFirmware') or {}
    mbfw = s.get('motherboardFirmware') or {}
    dqp = s.get('diskQualificationPackage') or {}
    dsums = s.get('drivesSummary') or []
    shelves = s.get('shelves') or []
    sn = s.get('serialNumber')
    host = s.get('hostName')
    print(f'\nSN={sn} host={host}')
    sptype = sfw.get('type')
    spcur = sfw.get('currentVersion')
    sprec = sfw.get('recommendedVersion')
    spdate = sfw.get('postingDate')
    spauto = sfw.get('autoUpdateEligible')
    print(f'  SP/BMC [{sptype}]: cur={spcur} rec={sprec} autoUpdate={spauto} date={spdate}')
    print(f'    DOWNREV={spcur != sprec and bool(sprec)}')
    mbcur = mbfw.get('currentVersion')
    mbrec = mbfw.get('recommendedVersion')
    print(f'  Motherboard: cur={mbcur} rec={mbrec} DOWNREV={mbcur != mbrec and bool(mbrec)}')
    dqpcur = dqp.get('currentVersion')
    dqprec = dqp.get('recommendedVersion')
    dqpauto = dqp.get('autoUpdateEligible')
    print(f'  DQP: cur={dqpcur} rec={dqprec} autoUpdate={dqpauto} DOWNREV={dqpcur != dqprec and bool(dqprec)}')
    print(f'  drivesSummary: {len(dsums)} models')
    downrev_drives = 0
    for d in dsums:
        fw = d.get('firmware') or {}
        dcur = fw.get('currentVersion')
        drec = fw.get('recommendedVersion')
        downrev = bool(drec) and dcur != drec
        if downrev:
            downrev_drives += 1
        model = d.get('driveModel') or d.get('model')
        flag = ' *** DOWNREV ***' if downrev else ''
        print(f'    {model} x{d.get("count")}: cur={dcur} rec={drec}{flag}')
    print(f'  Total downrev drive models: {downrev_drives}/{len(dsums)}')
    print(f'  Shelves: {len(shelves)}')
