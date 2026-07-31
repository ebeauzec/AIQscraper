import json
d = json.load(open('schema_probe_results.json'))
print('Top-level keys in schema_probe_results:', list(d.keys())[:20])

# Print all keys
for k in list(d.keys())[:5]:
    val = d[k]
    if isinstance(val, dict):
        print(f'\n{k} (dict): subkeys={list(val.keys())[:10]}')
    elif isinstance(val, list):
        print(f'\n{k} (list): len={len(val)}, first={json.dumps(val[0])[:200] if val else "empty"}')
    else:
        print(f'\n{k}: {str(val)[:200]}')
