import sqlite3, json

conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute('SELECT result_json FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
row = cur.fetchone()
d = json.loads(row[0])
systems = d.get('systems', [])

has_sp = sum(1 for s in systems if s.get('spFirmwareBaseline'))
has_disk = sum(1 for s in systems if s.get('diskFirmwareBaselines'))
has_shelf = sum(1 for s in systems if s.get('shelfFirmwareBaselines'))
print(f'Total systems: {len(systems)}')
print(f'Has spFirmwareBaseline: {has_sp}')
print(f'Has diskFirmwareBaselines: {has_disk}')
print(f'Has shelfFirmwareBaselines: {has_shelf}')

for s in systems:
    if s.get('spFirmwareBaseline') or s.get('diskFirmwareBaselines'):
        sn = s['serialNumber']
        model = s['model']
        os = s['osVersion']
        print(f'SN={sn} model={model} os={os}')
        print(f'  spFW: {json.dumps(s.get("spFirmwareBaseline"))}')
        print(f'  diskFW count: {len(s.get("diskFirmwareBaselines", []))}')
        print(f'  shelfFW count: {len(s.get("shelfFirmwareBaselines", []))}')
        break

# Check tamOsVersions in the cache
tam_os = d.get('tamOsVersions', [])
print(f'\ntamOsVersions entries: {len(tam_os)}')
if tam_os:
    v = tam_os[0]
    sfws = v.get("bundledSystemFirmwares", [])
    dfws = v.get("bundledDriveFirmwares", [])
    shelfws = v.get("bundledShelfFirmwares", [])
    print(f'  First entry os={v.get("osVersion")}')
    print(f'  bundledSystemFirmwares ({len(sfws)}): {json.dumps(sfws[:3])}')
    print(f'  bundledDriveFirmwares count: {len(dfws)}, sample: {json.dumps(dfws[:2])}')
    print(f'  bundledShelfFirmwares count: {len(shelfws)}, sample: {json.dumps(shelfws[:2])}')

conn.close()
