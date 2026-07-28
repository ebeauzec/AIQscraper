import sqlite3, json

conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()

# Get the latest harvest
cur.execute("SELECT result_json FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1")
row = cur.fetchone()
if not row:
    print("No harvest data found")
    conn.close()
    exit()

data = json.loads(row[0])
systems = data.get('systems', [])
print(f"Total systems: {len(systems)}")

# Check first system with firmware data
for s in systems[:5]:
    print(f"\nSystem: {s.get('systemName')} / {s.get('serialNumber')}")
    print(f"  osVersion: {s.get('osVersion')}")
    fw = s.get('systemFirmware', [])
    print(f"  systemFirmware count: {len(fw)}")
    if fw:
        print(f"  systemFirmware[0]: {fw[0]}")
    print(f"  spFirmwareBaseline: {s.get('spFirmwareBaseline')}")
    print(f"  biosVersion: {s.get('biosVersion')}")
    shb = s.get('shelfFirmwareBaselines', [])
    print(f"  shelfFirmwareBaselines count: {len(shb)}")
    if shb:
        print(f"  shelfFirmwareBaselines[0]: {shb[0]}")
    shelves = s.get('shelves', [])
    print(f"  shelves count: {len(shelves)}")
    if shelves:
        print(f"  shelves[0]: {shelves[0]}")

conn.close()
