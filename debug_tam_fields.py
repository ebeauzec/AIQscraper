"""Check TAM field string in server.py"""
with open(r'G:\My Drive\AntiGravity\AIQscraper\server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find SYSTEMS_FIELDS_TAM (not TAM_SAFE)
start_marker = 'SYSTEMS_FIELDS_TAM = '
start_idx = content.find(start_marker)
print(f'Found at char {start_idx}')

# Find the triple-quote opening
tq_start = content.find('"""', start_idx) + 3
tq_end = content.find('"""', tq_start)
tam_fields = content[tq_start:tq_end]
print(f'TAM field length: {len(tam_fields)}')
print(f'Has "capacity": {"capacity" in tam_fields}')
print(f'Has "monthlyCapacity": {"monthlyCapacity" in tam_fields}')
print(f'Last 200 chars: {repr(tam_fields[-200:])}')

# Count braces
opens = tam_fields.count('{')
closes = tam_fields.count('}')
print(f'Open braces: {opens}, Close braces: {closes}, Balance: {opens - closes}')
