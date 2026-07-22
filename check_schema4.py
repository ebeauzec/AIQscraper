import json
d = json.load(open('schema_probe_results.json'))

# Examine root queries
root_queries = d.get('root_queries', [])
print(f'Root queries ({len(root_queries)}):')
for q in root_queries:
    name = q.get('name', '')
    args = [a['name'] for a in q.get('args', [])]
    ret_type = q.get('type', {}).get('name') or q.get('type', {}).get('ofType', {}).get('name', '')
    print(f'  {name}({", ".join(args)}) -> {ret_type}')

print()

# Examine ONTAPSystem fields
ontap = d.get('type_ONTAPSystem', {})
fields = ontap.get('fields', [])
print(f'ONTAPSystem fields ({len(fields)}):')
for f in fields:
    name = f.get('name', '')
    ftype = f.get('type', {})
    type_name = ftype.get('name') or ftype.get('ofType', {}).get('name', '')
    print(f'  {name}: {type_name}')

print()

# Shelf fields
shelf = d.get('type_Shelf', {})
fields = shelf.get('fields', [])
print(f'Shelf fields ({len(fields)}):')
for f in fields:
    name = f.get('name', '')
    ftype = f.get('type', {})
    type_name = ftype.get('name') or ftype.get('ofType', {}).get('name', '')
    print(f'  {name}: {type_name}')

print()

# ShelfFirmware fields
sf = d.get('type_ShelfFirmware', {})
fields = sf.get('fields', [])
print(f'ShelfFirmware fields ({len(fields)}):')
for f in fields:
    print(f'  {f.get("name")}: {json.dumps(f.get("type"))}')

print()

# FirmwareVersion fields (motherboard firmware)
fv = d.get('type_FirmwareVersion', {})
fields = fv.get('fields', [])
print(f'FirmwareVersion fields ({len(fields)}):')
for f in fields:
    print(f'  {f.get("name")}: {json.dumps(f.get("type"))}')
