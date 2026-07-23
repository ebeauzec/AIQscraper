import sqlite3, json, re

SHELF_REF = {'IOM12': '0411', 'IOM12B': '0411', 'IOM12C': '0411', 'NSM100': '0303', 'NSM100B': '0303'}

def norm_fw_ver(v):
    if not v:
        return ''
    m = re.search(r'(?:^|\.)(\d{2,6})(?:\.|$)', v)
    if m:
        return m.group(1)
    m2 = re.search(r'(?:^|\.)([0-9A-Za-z]{4,6})(?:\.|$)', v)
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
            return False, 'SP drift: type=%s cur=%s rec=%s' % (type_label, cur, rec)
    for sh in (sys.get('shelves') or []):
        cur = sh.get('firmwareVersion') or ''
        if not cur:
            continue
        if sh.get('fromCatalog'):
            continue
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

conn = sqlite3.connect('aiq_cache.db')
c = conn.cursor()
c.execute('SELECT result_json FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
row = c.fetchone()
conn.close()
data = json.loads(row[0])
systems = data.get('systems') or []
print('Total systems: %d' % len(systems))
ok_c = 0
fail_c = 0
for s in systems:
    is_ok, reason = is_comp_fw_current(s)
    if is_ok:
        ok_c += 1
    else:
        fail_c += 1
        sn = s.get('serialNumber','?')
        model = s.get('model','?')
        print('FAIL: SN=%s model=%s' % (sn, model))
        print('      %s' % reason)
        for sh in (s.get('shelves') or []):
            print('      Shelf: mod=%s cur=%s rec=%s fromCatalog=%s' % (sh.get('moduleType'), sh.get('firmwareVersion'), sh.get('recommendedFirmwareVersion'), sh.get('fromCatalog')))
        for fw in (s.get('systemFirmware') or []):
            print('      SP: type=%s cur=%s rec=%s _fromFleet=%s _fromCatalog=%s' % (fw.get('type'), fw.get('currentVersion'), fw.get('recommendedVersion'), fw.get('_fromFleet'), fw.get('_fromCatalog')))
print('Summary: %d/%d current (%d%%)' % (ok_c, len(systems), ok_c*100//len(systems) if systems else 0))
