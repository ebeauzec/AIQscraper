import sqlite3, json

conn = sqlite3.connect("aiq_cache.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])
for table in tables:
    name = table[0]
    cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
    print(f"  {name}: {[c[1] for c in cols]}")

# Try to get harvest data
try:
    row = conn.execute("SELECT payload FROM harvest_cache ORDER BY ts DESC LIMIT 1").fetchone()
    if row:
        data = json.loads(row[0])
        systems = data.get("systems", [])
        print(f"\nTotal systems in cache: {len(systems)}")
        for s in systems[:3]:
            name = s.get("systemName", "?")
            osv = s.get("osVersion", "?")
            fw = s.get("systemFirmware", [])
            spfw = s.get("spFirmwareBaseline", {})
            bios = s.get("biosVersion", "")
            print(f"  {name} | ONTAP {osv} | systemFirmware: {fw} | spBaseline: {spfw} | bios: {bios}")
except Exception as e:
    print("Error reading harvest_cache:", e)

conn.close()
