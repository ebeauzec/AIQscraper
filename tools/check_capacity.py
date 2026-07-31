import sqlite3
import json

conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()

cur.execute("SELECT result_json FROM harvest_cache LIMIT 1")
row = cur.fetchone()
conn.close()

data = json.loads(row[0])
print("Top-level keys:", list(data.keys()))

systems = data.get('systems', [])
print(f"Systems count: {len(systems)}")

# Check capacity for first 5 systems
for s in systems[:5]:
    serial = s.get('serialNumber', '')
    name = s.get('systemName', '')
    raw_tb = s.get('clusterRawCapacityTB', 'MISSING')
    used_tb = s.get('clusterPhysicalUsedTB', 'MISSING')
    cap_kb = s.get('capacityUsedKB', 'MISSING')
    model = s.get('model', '')
    drive_fw = s.get('driveFirmware', [])
    shelf_list = s.get('shelves', [])
    print(f"\n  {serial} ({name}) [{model}]")
    print(f"    rawTB={raw_tb}  usedTB={used_tb}  capUsedKB={cap_kb}")
    print(f"    driveFirmware entries: {len(drive_fw)}")
    if drive_fw:
        print(f"    First drive fw: {drive_fw[0]}")
    print(f"    Shelves: {len(shelf_list)}")
    if shelf_list:
        sh = shelf_list[0]
        print(f"    First shelf: {sh.get('shelfId')} fw={sh.get('firmwareVersion')} recFW={sh.get('recommendedFirmwareVersion')}")
