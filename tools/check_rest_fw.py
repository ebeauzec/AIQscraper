import json

d = json.load(open('schema_probe_results.json'))

# Print all keys containing 'rest' or 'firmware'
rest_keys = [k for k in d if 'rest_' in k.lower() or ('firmware' in k.lower() and not k.startswith('type_'))]
print('REST / firmware probe keys:')
for k in rest_keys:
    val = d[k]
    print(f'\n=== {k} ===')
    print(json.dumps(val, indent=2)[:800])

# Also check SystemFirmware type (returned by systemFirmware on ONTAPSystem)
sys_fw = d.get('type_SystemFirmware', {})
if sys_fw:
    print('\n=== type_SystemFirmware ===')
    print(json.dumps(sys_fw, indent=2)[:800])
    
# DiskQualificationPackage type
dqp = d.get('type_DiskQualificationPackage', {})
if dqp:
    print('\n=== type_DiskQualificationPackage ===')
    print(json.dumps(dqp, indent=2)[:800])
