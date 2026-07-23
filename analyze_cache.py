"""
Probe the last harvest's raw GQL response to understand why capacity is zero.
Looks at the raw result_json to check if 'capacity' field exists per system.
"""
import sqlite3
import json

conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute("SELECT result_json FROM harvest_cache LIMIT 1")
row = cur.fetchone()
conn.close()

data = json.loads(row[0])
systems = data.get('systems', [])

zero_cap = 0
has_cap = 0
no_shelves = 0
has_shelves = 0
has_live_drive_fw = 0

type_counts = {}
for s in systems:
    st = s.get('systemType', 'unknown')
    type_counts[st] = type_counts.get(st, 0) + 1
    
    raw_tb = s.get('clusterRawCapacityTB', 0)
    if raw_tb and raw_tb > 0:
        has_cap += 1
    else:
        zero_cap += 1
    
    shelves = s.get('shelves', [])
    if shelves:
        has_shelves += 1
    else:
        no_shelves += 1
    
    dfw = s.get('driveFirmware', [])
    live = [d for d in dfw if not d.get('_fromCatalog') and not d.get('_fromFleet')]
    if live:
        has_live_drive_fw += 1

print(f"System types: {type_counts}")
print(f"Capacity: {has_cap} have data, {zero_cap} are zero")
print(f"Shelves:  {has_shelves} have shelves, {no_shelves} have none")
print(f"Live drive FW: {has_live_drive_fw} have it")

# Show the first 3 systems that DO have capacity data
print("\nSystems WITH capacity:")
count = 0
for s in systems:
    if s.get('clusterRawCapacityTB', 0) > 0:
        print(f"  {s['serialNumber']} ({s.get('systemName')}) [{s.get('model')}]")
        print(f"    rawTB={s['clusterRawCapacityTB']}  usedTB={s['clusterPhysicalUsedTB']}")
        count += 1
        if count >= 3:
            break

if count == 0:
    print("  NONE - all systems have zero capacity")

# Show any system with shelves
print("\nSystems WITH shelves:")
count = 0
for s in systems:
    if s.get('shelves'):
        sh = s['shelves'][0]
        print(f"  {s['serialNumber']} ({s.get('systemName')}): {len(s['shelves'])} shelves")
        print(f"    First shelf: id={sh.get('shelfId')} serial={sh.get('serialNumber')} fw={sh.get('firmwareVersion')}")
        count += 1
        if count >= 3:
            break

if count == 0:
    print("  NONE - no systems have shelf data")
