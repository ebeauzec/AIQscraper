import json
from pathlib import Path

data = json.loads(Path('schema_probe_results.json').read_text(encoding='utf-8'))

targets = [
    'type_Drives', 'type_Drive', 'type_Bays', 'type_Bay',
    'type_ShelfModuleHardwareModel', 'type_ShelfHardwareModel',
    'type_GroupByDevice', 'type_GroupByDeviceNode', 'type_FirmwareVersion',
    'type_ShelfFirmware', 'type_DiskFirmware',
]

for tname in targets:
    if tname not in data:
        print(f'=== {tname} === NOT FOUND')
        continue
    obj = data[tname]
    print(f'=== {tname} ===')
    for f in obj.get('fields', []):
        t = f.get('type', {})
        inner = t.get('ofType') or {}
        inner2 = inner.get('ofType') or {}
        tname2 = t.get('name') or inner.get('name') or inner2.get('name') or '?'
        print(f"  {f['name']} -> {tname2}")
    print()

# Also look for any probe results that succeeded with firmware data
print("=== Probe hits with firmware ===")
for k, v in data.items():
    if 'probe_' in k and 'error' not in str(v) and ('firmware' in k.lower() or 'drive' in k.lower()):
        print(k, '->', str(v)[:300])
