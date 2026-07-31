import sqlite3
import json

conn = sqlite3.connect('aiq_cache.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# List tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{t}]")
    cnt = cur.fetchone()[0]
    print(f"  {t}: {cnt} rows")

# Check if there's a cache blob table
if 'cache' in tables:
    cur.execute("SELECT key, length(value) FROM cache LIMIT 10")
    for r in cur.fetchall():
        print(f"  cache key: {r[0]}  value_len: {r[1]}")

# Check for systems data
if 'harvest' in tables:
    cur.execute("SELECT key, length(value) as vlen FROM harvest LIMIT 5")
    for r in cur.fetchall():
        print(f"  harvest key: {r[0]}  len: {r[1]}")

# Check for main data blob
for t in tables:
    cur.execute(f"SELECT * FROM [{t}] LIMIT 2")
    cols = [c[0] for c in cur.description]
    print(f"\n  [{t}] columns: {cols}")
    rows = cur.fetchall()
    for row in rows:
        row_dict = dict(zip(cols, row))
        # Don't print huge blobs
        for k, v in row_dict.items():
            if isinstance(v, (bytes, str)) and len(str(v)) > 200:
                row_dict[k] = f"<{len(str(v))} chars>"
        print(f"    {row_dict}")

conn.close()
