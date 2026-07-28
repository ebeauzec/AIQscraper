import sqlite3, json

conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute('SELECT result_json FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
d = json.loads(cur.fetchone()[0])
conn.close()

systems = d.get('systems', [])
print(f"Total systems: {len(systems)}")

# Check AutoSupport status
asup_active = 0
asup_inactive = 0
for s in systems:
    asup_cfg = s.get('autoSupportStatus', '')
    if asup_cfg and asup_cfg.lower() in ('active', 'enabled', 'on'):
        asup_active += 1
    else:
        asup_inactive += 1

print(f"AutoSupport active: {asup_active}")
print(f"AutoSupport not active: {asup_inactive}")

# Check first system's AutoSupport-related fields
s = systems[0]
print(f"\nSN={s.get('serialNumber')} name={s.get('systemName')}")
print(f"  autoSupportStatus: {s.get('autoSupportStatus')}")
print(f"  autoSupportEnabled: {s.get('autoSupportEnabled')}")
# Check lastAsup
asup_last = s.get('lastAsupDate') or s.get('latestAsupDate')
print(f"  latestAsupDate: {asup_last}")

# More importantly: what does systemFirmware look like?
print(f"  systemFirmware: {s.get('systemFirmware')}")
print(f"  driveFirmware: {s.get('driveFirmware')}")
print(f"  shelves: {s.get('shelves')}")

# Any system with firmwareData would indicate TAM query succeeded
systems_with_fw = [s for s in systems if s.get('systemFirmware') and len(s.get('systemFirmware', [])) > 0]
print(f"\nSystems with non-empty systemFirmware: {len(systems_with_fw)}")
if systems_with_fw:
    print(f"  Example: SN={systems_with_fw[0].get('serialNumber')}")
    print(f"  systemFirmware: {systems_with_fw[0].get('systemFirmware')[:2]}")
