"""
Live probe using the server's own OAuth flow to get a valid access token first.
"""
import json, http.client, ssl
from pathlib import Path

cfg = json.loads(Path('aiq_config.json').read_text(encoding='utf-8'))
refresh_token = cfg.get('refreshToken', '')

def http_req(method, host, path, headers=None, body=None):
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, context=ctx, timeout=20)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, raw.decode('utf-8', errors='replace')

# Get a fresh access token
print("Getting access token...")
token_st, token_raw = http_req("POST", "api.activeiq.netapp.com",
    "/v1/tokens/accessToken",
    headers={"Content-Type": "application/json", "Accept": "application/json"},
    body=json.dumps({"refreshToken": refresh_token}).encode()
)
print(f"Token request: HTTP {token_st}")
if token_st != 200:
    print("Token response:", token_raw[:300])
    exit()

tdata = json.loads(token_raw)
access_token = tdata.get('access_token') or tdata.get('accessToken', '')
print(f"Got token: {access_token[:30]}... ({len(access_token)} chars)")

def gql(query, token):
    body = json.dumps({"query": query}).encode()
    st, raw = http_req("POST", "api.activeiq.netapp.com", "/graphql",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        body=body
    )
    return st, json.loads(raw) if raw else {}

SN = '211715000458'
SN2 = '211839000195'

# Test A: system shelves with shelfFirmware  
print(f"\n=== A: system shelves with shelfFirmware (SN={SN}) ===")
st, r = gql(f"""{{
  systems(filter: {{serialNumbers: ["{SN}"]}}) {{
    systems {{
      serialNumber
      ... on ONTAPSystem {{
        shelves {{
          serialNumber shelfId
          hardwareModel {{ name endOfAvailability endOfHwSupport }}
          moduleHardwareModel {{ name }}
          shelfFirmware {{
            currentVersion recommendedVersion autoUpdateEligible
          }}
        }}
      }}
    }}
  }}
}}""", access_token)
print(f"HTTP {st}")
if r.get('errors'):
    print("ERROR:", r['errors'][0]['message'][:300])
else:
    syss = (r.get('data') or {}).get('systems', {}).get('systems', [])
    for s in syss:
        shelves = s.get('shelves', [])
        print(f"Shelves: {len(shelves)}")
        for sh in shelves[:4]:
            print(f"  {json.dumps(sh)[:400]}")

# Test B: cluster shelves with shelfFirmware
print("\n=== B: cluster shelves with shelfFirmware ===")
st, r = gql("""{ clusters(pageSize: 2) { clusters { name shelves {
  serialNumber shelfId
  hardwareModel { name endOfAvailability endOfHwSupport }
  moduleHardwareModel { name }
  shelfFirmware { currentVersion recommendedVersion autoUpdateEligible postingDate }
}}}}""", access_token)
print(f"HTTP {st}")
if r.get('errors'):
    print("ERROR:", r['errors'][0]['message'][:300])
else:
    clusters = (r.get('data') or {}).get('clusters', {}).get('clusters', [])
    for cl in clusters:
        shelves = cl.get('shelves', [])
        print(f"Cluster {cl.get('name')}: {len(shelves)} shelves")
        for sh in shelves[:3]:
            print(f"  {json.dumps(sh)[:500]}")

# Test C: systemFirmware on systems
print("\n=== C: systemFirmware ===")
st, r = gql(f"""{{
  systems(filter: {{serialNumbers: ["{SN}", "{SN2}"]}}) {{
    systems {{
      serialNumber
      ... on ONTAPSystem {{
        systemFirmware {{ type currentVersion recommendedVersion autoUpdateEligible postingDate }}
        diskQualificationPackage {{ currentVersion recommendedVersion autoUpdateEligible }}
      }}
    }}
  }}
}}""", access_token)
print(f"HTTP {st}")
if r.get('errors'):
    print("ERROR:", r['errors'][0]['message'][:300])
else:
    for s in (r.get('data') or {}).get('systems', {}).get('systems', []):
        fw = s.get('systemFirmware', [])
        dqp = s.get('diskQualificationPackage', {})
        print(f"SN {s.get('serialNumber')}: fw={json.dumps(fw)}, dqp={json.dumps(dqp)}")

# Test D: tamOsVersions
print("\n=== D: tamOsVersions bundled firmwares ===")
st, r = gql("""{ tamOsVersions(filter: {osVersions: ["9.16.1P11"]}) {
  osVersion
  bundledSystemFirmwares { type version biosVersion systemModel }
  bundledDriveFirmwares { driveModel version }
  bundledShelfFirmwares { shelfName shelfModuleName firmwareType shelfModuleFirmwareVersion sysShelfModuleFirmwareVersion }
}}""", access_token)
print(f"HTTP {st}")
if r.get('errors'):
    print("ERROR:", r['errors'][0]['message'][:300])
else:
    vers = (r.get('data') or {}).get('tamOsVersions', [])
    for v in vers[:1]:
        sfws = v.get('bundledSystemFirmwares', [])
        dfws = v.get('bundledDriveFirmwares', [])
        shelffws = v.get('bundledShelfFirmwares', [])
        print(f"OS {v.get('osVersion')}:")
        print(f"  System FW ({len(sfws)}): {json.dumps(sfws[:5])}")
        print(f"  Drive FW ({len(dfws)}): {json.dumps(dfws[:5])}")
        print(f"  Shelf FW ({len(shelffws)}): {json.dumps(shelffws[:5])}")
