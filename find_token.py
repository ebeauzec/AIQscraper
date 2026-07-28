import sqlite3, json
conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in cur.fetchall()])
# Try to find token
try:
    cur.execute("SELECT * FROM token_cache LIMIT 1")
    row = cur.fetchone()
    if row:
        print("Token row:", row)
except Exception as e:
    print("No token_cache table:", e)
try:
    cur.execute("SELECT * FROM auth_cache LIMIT 1")
    row = cur.fetchone()
    if row:
        print("Auth row columns:", [d[0] for d in cur.description])
        d = dict(zip([d[0] for d in cur.description], row))
        for k,v in d.items():
            if 'token' in k.lower():
                print(f"  {k}: {str(v)[:60]}...")
except Exception as e:
    print("No auth_cache table:", e)
conn.close()
