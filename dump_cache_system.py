"""
Dump the raw GQL system object stored in harvest cache to check why capacity is zero.
"""
import sqlite3, json

conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()

# Get the raw harvest result
cur.execute('SELECT result_json, harvested_at FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
row = cur.fetchone()
print(f"Cache time: {row[1]}")
d = json.loads(row[0])
systems = d.get('systems', [])

# Find the first non-ASUP system
s = next((x for x in systems if x.get('serialNumber') and
          not x['serialNumber'].startswith(('ASUP','ES-'))), None)

if s:
    sn = s.get('serialNumber')
    print(f"\nSystem: {s.get('systemName')} ({sn})")
    print(f"clusterRawCapacityTB    = {s.get('clusterRawCapacityTB')}")
    print(f"clusterPhysicalUsedTB   = {s.get('clusterPhysicalUsedTB')}")
    print(f"clusterUsableCapacityTB = {s.get('clusterUsableCapacityTB')}")
    print()

    # Look for any capacity-like fields
    print("=== All keys in this system object: ===")
    for k, v in s.items():
        if v not in (None, '', [], {}, 0):
            if isinstance(v, (dict, list)):
                print(f"  {k}: {str(v)[:120]}")
            else:
                print(f"  {k}: {v}")

conn.close()
