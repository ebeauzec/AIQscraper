import sqlite3, json

conn = sqlite3.connect('aiq_cache.db')
c = conn.cursor()
c.execute('SELECT result_json FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
row = c.fetchone()
conn.close()
data = json.loads(row[0])
systems = data.get('systems') or []

print('Total: %d' % len(systems))
live_sp = []
fleet_sp = []
catalog_sp = []
no_fw = []
for s in systems:
    sw = s.get('systemFirmware') or []
    fleet = s.get('fleetSpFirmwareMap') or {}
    if not sw:
        if fleet:
            fleet_sp.append(s.get('serialNumber'))
        else:
            no_fw.append(s.get('serialNumber'))
    else:
        fw0 = sw[0]
        if fw0.get('_fromCatalog'):
            catalog_sp.append(s.get('serialNumber'))
        elif fw0.get('_fromFleet'):
            fleet_sp.append(s.get('serialNumber'))
        else:
            live_sp.append(s.get('serialNumber'))

print('Live SP data: %d' % len(live_sp))
print('Fleet-only SP: %d' % len(fleet_sp))
print('Catalog SP: %d' % len(catalog_sp))
print('No FW data: %d' % len(no_fw))

# Show live SP details
print()
print('--- Live SP systems ---')
sn_to_sys = {s.get('serialNumber'): s for s in systems}
for sn in live_sp[:10]:
    s = sn_to_sys.get(sn, {})
    sw = s.get('systemFirmware') or []
    fleet = s.get('fleetSpFirmwareMap') or {}
    print('SN=%s' % sn)
    for fw in sw:
        print('  type=%s cur=%s rec=%s _fromFleet=%s _fromCatalog=%s' % (
            fw.get('type'), fw.get('currentVersion'), fw.get('recommendedVersion'),
            fw.get('_fromFleet'), fw.get('_fromCatalog')))
    if fleet:
        for k, v in fleet.items():
            print('  fleet[%s]=%s' % (k, v.get('firmwareVersion')))
    else:
        print('  fleet=(empty)')

# Now simulate _isCompFwCurrent for live SP systems
print()
print('--- isCompFwCurrent on live SP systems ---')
SHELF_REF = {'IOM12': '0411', 'IOM12B': '0411', 'IOM12C': '0411', 'NSM100': '0303', 'NSM100B': '0303'}

import re
def norm_fw_ver(v):
    if not v: return ''
    m = re.search(r'(?:^|\.)(\d{2,6})(?:\.|$)', v)
    if m: return m.group(1)
    m2 = re.search(r'(?:^|\.)([ 0-9A-Za-z]{4,6})(?:\.|$)', v)
    return m2.group(1).upper() if m2 else v.upper()

def is_comp_fw_current(sys):
    fleet_sp_map = sys.get('fleetSpFirmwareMap') or {}
    for fw in (sys.get('systemFirmware') or []):
        if fw.get('_fromFleet') or fw.get('_fromCatalog'):
            continue
        cur = fw.get('currentVersion') or ''
        if not cur:
            continue
        type_label = (fw.get('type') or 'SP').upper()
        fleet_entry = fleet_sp_map.get(type_label) or fleet_sp_map.get('SP')
        fleet_rec = (fleet_entry.get('firmwareVersion') or '') if fleet_entry else ''
        rec = fleet_rec or (fw.get('recommendedVersion') or '')
        if rec and cur != rec:
            return False, 'SP drift: type=%s cur=%s rec=%s (fleetRec=%s)' % (type_label, cur, rec, fleet_rec)
    for sh in (sys.get('shelves') or []):
        cur = sh.get('firmwareVersion') or ''
        if not cur: continue
        if sh.get('fromCatalog'): continue
        norm_cur = norm_fw_ver(cur)
        rec = sh.get('recommendedFirmwareVersion') or ''
        norm_rec = norm_fw_ver(rec) if rec else ''
        if norm_rec and norm_cur != norm_rec:
            return False, 'Shelf drift: mod=%s cur=%s(%s) rec=%s(%s)' % (sh.get('moduleType'), cur, norm_cur, rec, norm_rec)
        mk = (sh.get('moduleType') or '').replace('_','').replace(' ','').upper()
        ref_norm = SHELF_REF.get(mk) or SHELF_REF.get(mk[:-1] if mk.endswith(('B','C')) else mk)
        if ref_norm and norm_cur < ref_norm:
            return False, 'Shelf behind ref: mod=%s cur=%s(%s) ref=%s' % (sh.get('moduleType'), cur, norm_cur, ref_norm)
    return True, 'OK'

ok_c = fail_c = 0
for sn in live_sp:
    s = sn_to_sys.get(sn, {})
    is_ok, reason = is_comp_fw_current(s)
    if is_ok:
        ok_c += 1
    else:
        fail_c += 1
        print('FAIL SN=%s: %s' % (sn, reason))

print('Live SP summary: %d/%d current' % (ok_c, len(live_sp)))

# Also check full fleet
ok_all = 0
for s in systems:
    is_ok, _ = is_comp_fw_current(s)
    if is_ok: ok_all += 1
print('Full fleet: %d/%d current' % (ok_all, len(systems)))
