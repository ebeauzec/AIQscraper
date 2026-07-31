import json
d = json.load(open('schema_probe_results.json'))
queries = d.get('rootQueries', {})
fw_keys = [k for k in queries if any(x in k.lower() for x in ('firmware', 'shelf', 'drive', 'disk', 'sp', 'bmc', 'mainboard', 'motherboard'))]
print('Firmware/shelf/drive root queries:', fw_keys)
for k in fw_keys[:20]:
    q = queries[k]
    args = q.get('args', [])
    arg_names = [a['name'] for a in args]
    print(f'  {k}: args={arg_names}')

# Also check ONTAPSystem type for shelves
types = d.get('types', {})
ontap = types.get('ONTAPSystem', {})
if ontap:
    fields = ontap.get('fields', [])
    fw_fields = [f['name'] for f in fields if any(x in f['name'].lower() for x in ('firmware', 'shelf', 'drive', 'disk', 'sp', 'bmc'))]
    print('\nONTAPSystem firmware-related fields:', fw_fields)
