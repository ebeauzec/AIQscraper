import sqlite3, json

conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute('SELECT result_json, harvested_at FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
row = cur.fetchone()
conn.close()

d = json.loads(row[0])
systems = d.get('systems', [])
print("Cache timestamp:", row[1])
print("Total systems:", len(systems))
print()

# Capacity distribution
zero_raw = [s for s in systems if not s.get('clusterRawCapacityTB')]
nonzero_raw = [s for s in systems if s.get('clusterRawCapacityTB')]

print("Systems with clusterRawCapacityTB > 0 :", len(nonzero_raw))
print("Systems with clusterRawCapacityTB == 0 :", len(zero_raw))
print()

if nonzero_raw:
    print("=== Sample systems WITH capacity ===")
    for s in nonzero_raw[:8]:
        sn = s.get('serialNumber', '')
        raw = s.get('clusterRawCapacityTB', 0)
        used = s.get('clusterPhysicalUsedTB', 0)
        usable = s.get('clusterUsableCapacityTB', 0)
        util = s.get('clusterCapacityUtilPct', 0)
        print(f"  {sn:20s}  raw={raw:8.2f}TB  used={used:8.2f}TB  usable={usable:8.2f}TB  util={util}%")

if zero_raw:
    print()
    print("=== Sample systems WITHOUT capacity (still zero) ===")
    for s in zero_raw[:8]:
        sn = s.get('serialNumber', '')
        model = s.get('model', '')
        print(f"  {sn:20s}  model={model}")

# Check monthly capacity data
monthly_count = sum(1 for s in systems if s.get('clusterMonthlyCapacity'))
print()
print("Systems with clusterMonthlyCapacity data:", monthly_count)

# Runway calculation feasibility
runway_possible = [s for s in systems if s.get('clusterRawCapacityTB') and s.get('clusterMonthlyCapacity')]
print("Systems with BOTH raw capacity AND monthly data (runway-ready):", len(runway_possible))

# Summary stats
total_raw_tb = sum(s.get('clusterRawCapacityTB') or 0 for s in systems)
total_used_tb = sum(s.get('clusterPhysicalUsedTB') or 0 for s in systems)
print()
print(f"Fleet total raw:  {total_raw_tb:.2f} TB")
print(f"Fleet total used: {total_used_tb:.2f} TB")
if total_raw_tb:
    print(f"Fleet avg util:   {total_used_tb/total_raw_tb*100:.1f}%")
