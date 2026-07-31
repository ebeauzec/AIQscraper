"""
Debug the actual harvest transform by reading the cached systems and checking what
capacity fields are actually present (were they ever populated?).
"""
import sqlite3, json

conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute('SELECT result_json, harvested_at FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
row = cur.fetchone()
conn.close()

d = json.loads(row[0])
systems = d.get('systems', [])
print('Cache timestamp:', row[1])
print('Total systems:', len(systems))
print()

# Show ALL keys of first system
s = systems[0]
print('=== ALL KEYS of first system ===')
for k, v in s.items():
    if isinstance(v, (dict, list)):
        vstr = f'{type(v).__name__}(len={len(v)})' if hasattr(v, '__len__') else str(type(v))
    else:
        vstr = repr(v)[:80]
    print(f'  {k}: {vstr}')

print()
print('=== Capacity-related fields ===')
cap_fields = [k for k in s.keys() if 'cap' in k.lower() or 'raw' in k.lower() or 'used' in k.lower() or 'util' in k.lower() or 'monthly' in k.lower() or 'eff' in k.lower()]
for k in cap_fields:
    print(f'  {k}: {repr(s.get(k))[:120]}')

print()
# Verify 211715000458 (we know this has data from debug_harvest.py)
target = next((x for x in systems if x.get('serialNumber') == '211715000458'), None)
if target:
    print('=== System 211715000458 ===')
    print('clusterRawCapacityTB:', target.get('clusterRawCapacityTB'))
    print('clusterPhysicalUsedTB:', target.get('clusterPhysicalUsedTB'))
    print('capacityUsedKB:', target.get('capacityUsedKB'))
    print('clusterCapacityReportedOn:', target.get('clusterCapacityReportedOn'))
    print('clusterMonthlyCapacity:', target.get('clusterMonthlyCapacity'))
