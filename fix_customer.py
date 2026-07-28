content = open('app.js', 'r', encoding='utf-8').read()
old = 's.customerName || s.customer_name || s.accountName || s.account_name || "customer"'
new = 's.customerName || s.customer_name || s.accountName || s.account_name || null'
count = content.count(old)
print(f'Occurrences: {count}')
if count:
    content = content.replace(old, new)
    open('app.js', 'w', encoding='utf-8').write(content)
    print('Done')
