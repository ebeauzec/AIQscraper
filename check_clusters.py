import sqlite3
import json

conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute("SELECT result_json FROM harvest_cache LIMIT 1")
row = cur.fetchone()
conn.close()

data = json.loads(row[0])

clusters = data.get('clusters', [])
print(f"Clusters count: {len(clusters)}")
for cl in clusters[:5]:
    name = cl.get('name', '')
    cap_tb = cl.get('rawCapacityTB', cl.get('capacityRawTB', 'N/A'))
    phys_used = cl.get('physicalUsedTB', 'N/A')
    monthly = cl.get('monthlyCapacity', [])
    shelves = cl.get('shelves', [])
    print(f"\n  {name}")
    print(f"    rawCapacityTB={cap_tb}  physicalUsedTB={phys_used}")
    print(f"    monthlyCapacity entries: {len(monthly)}")
    print(f"    shelves: {len(shelves)}")
    if shelves:
        sh = shelves[0]
        print(f"    First shelf: {sh}")

# Check what keys clusters have
if clusters:
    print(f"\nCluster keys: {list(clusters[0].keys())}")
