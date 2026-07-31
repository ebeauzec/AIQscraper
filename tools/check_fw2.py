import sqlite3, json
conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute('SELECT result_json FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
row = cur.fetchone()
d = json.loads(row[0])
conn.close()

tam_os = d.get('tamOsVersions', [])
print('tamOsVersions count:', len(tam_os))

# Show sample entry with firmware
for ov in tam_os:
    sfws = ov.get('bundledSystemFirmwares', [])
    dfws = ov.get('bundledDriveFirmwares', [])
    shfws = ov.get('bundledShelfFirmwares', [])
    if sfws or dfws or shfws:
        osv = ov.get('osVersion')
        print('  OS', osv, ':', 'systemFW='+str(len(sfws)), 'driveFW='+str(len(dfws)), 'shelfFW='+str(len(shfws)))
        if sfws:
            print('    SP/BMC:', json.dumps(sfws[:3]))
        if dfws:
            print('    Drives (first 3):', json.dumps(dfws[:3]))
        if shfws:
            print('    Shelves (first 3):', json.dumps(shfws[:3]))
        break

print()
# Show what systems have vs what tamOsVersions has
systems = d.get('systems', [])
for sys in systems[:5]:
    sn = sys.get('serialNumber')
    osv = sys.get('osVersion') or sys.get('ontapVersion', '')
    fw = sys.get('systemFirmware', [])
    dqp = sys.get('diskQualificationPackage', {})
    print('SN', sn, 'OS', osv, 'fw_count='+str(len(fw)), 'dqp='+str(bool(dqp)))
