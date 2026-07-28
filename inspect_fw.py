import json

with open('firmware_real_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('Top-level keys:', list(data.keys()))
print()

# Check for systemFirmware in systems
if 'systemFirmware' in data:
    print('systemFirmware:', json.dumps(data['systemFirmware'])[:1000])

# Check osVersions structure
if 'osVersions' in data:
    ov = data['osVersions']
    if isinstance(ov, dict):
        inner = ov.get('osVersions', ov)
        if isinstance(inner, dict):
            versions = inner.get('osVersions', [])
        elif isinstance(inner, list):
            versions = inner
        else:
            versions = []
    elif isinstance(ov, list):
        versions = ov
    else:
        versions = []
    
    print(f'OS versions count: {len(versions)}')
    if versions:
        v = versions[0]
        print('First version keys:', list(v.keys()))
        sfws = v.get('bundledSystemFirmwares', [])
        dfws = v.get('bundledDriveFirmwares', [])
        shelffws = v.get('bundledShelfFirmwares', [])
        print(f'  bundledSystemFirmwares ({len(sfws)}):')
        for f in sfws[:5]:
            print(f'    {json.dumps(f)}')
        print(f'  bundledDriveFirmwares ({len(dfws)}): (first 3)')
        for f in dfws[:3]:
            print(f'    {json.dumps(f)}')
        print(f'  bundledShelfFirmwares ({len(shelffws)}): (first 3)')
        for f in shelffws[:3]:
            print(f'    {json.dumps(f)}')

# Look for live per-system firmware data (Test C result)
if 'systems' in data:
    systems = data['systems']
    if isinstance(systems, dict):
        systems_list = systems.get('systems', [])
    elif isinstance(systems, list):
        systems_list = systems
    else:
        systems_list = []
    print(f'\nSystems with systemFirmware: {len([s for s in systems_list if s.get("systemFirmware")])}')
    print(f'Systems with shelves: {len([s for s in systems_list if s.get("shelves")])}')

# Check for test A/B/C/D results in the data
for key in ['testA', 'testB', 'testC', 'testD', 'shelves', 'clusters', 'firmware']:
    if key in data:
        print(f'\nFound key "{key}": {json.dumps(data[key])[:400]}')
