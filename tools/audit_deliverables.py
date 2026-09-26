"""Deliverable consistency audit (local, parallel).

Generates every Action Planner deliverable for every customer scope (plus the whole fleet) in
N headless browsers at once against a running ARIA server, writes them to audit_out/, and flags:
placeholder or invented-figure phrases, NaN/undefined, numbers that disagree between documents
of one scope (ARP, open cases, lapsed contracts), and other customers' names.
Known benign hits: an account's own ASP / site names that contain another customer's name.

Usage:  ARIA_URL=http://127.0.0.1:8080/ python tools/audit_deliverables.py [workers]
Needs:  pip install playwright && playwright install chromium
"""
import json, re, sys, os, time
from multiprocessing import Pool
from playwright.sync_api import sync_playwright

URL = os.environ.get('ARIA_URL', 'http://127.0.0.1:8080/')
OUT = os.environ.get('ARIA_AUDIT_OUT', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'audit_out'))
WORKERS = int(sys.argv[1]) if len(sys.argv) > 1 else 12

GEN = """(cust) => { const ts = cust ? state.systems.filter(s=>s.customerName===cust) : state.systems; const R=[],U=[],C=[],K=[];
ts.forEach(sys=>{ (sys.risks||[]).forEach(r=>R.push({systemName:sys.systemName,serialNumber:sys.serialNumber,...r}));
 if(sys.upgrades&&sys.upgrades.targetVersion!=="Up to Date")U.push({systemName:sys.systemName,serialNumber:sys.serialNumber,platform:sys.platform,currentVersion:sys.ontapVersion,...sys.upgrades});
 (sys.supportCases||[]).forEach(sc=>K.push({systemName:sys.systemName,customerName:sys.customerName,serialNumber:sys.serialNumber,...sc})); });
 try { const d = compileExtendedDeliverables(ts,R,U,C,K,'Customer: '+(cust||'All')); const o={}; for (const [k,v] of Object.entries(d)) if (typeof v==='string') o[k]=v; return o; } catch(e) { return {__error: e.message + ' ' + (e.stack||'').split('\\n')[1]}; } }"""

FORBIDDEN = [r'all tenants', r'unpatched CVE', r'Real date reported', r'Review vendor alignment', r'validated for your fleet',
             r'ARIA enrichment', r'\bNaN\b', r'undefined', r'\[object', r'\b9999d\b', r'N/A:1', r'\(estimated\)', r'DR Partner',
             r'this tool', r'\bInfinity\b', r'null%', r'Fleet Sustainability Score', r'\$X', r'kW avoided', r'kg/year', r'illustrative', r'est\. \$', r'Real date', r'(?<![\w.])-\d+ system', r'\(0d\)', r'(?<![\d<])0d runway']

def work(args):
    idx, custs = args
    res = {}
    time.sleep(idx * 4)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(URL)
        pg.wait_for_function('typeof state !== "undefined" && state.systems && state.systems.length > 0', timeout=400000)
        time.sleep(2)
        allc = pg.evaluate('[...new Set(state.systems.map(s=>s.customerName))]')
        for c in custs:
            key = c if c != '__ALL__' else None
            d = pg.evaluate('(' + GEN + ')(' + json.dumps(key) + ')')
            res[c] = d
        b.close()
    return res

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(URL)
        pg.wait_for_function('typeof state !== "undefined" && state.systems && state.systems.length > 0', timeout=400000)
        time.sleep(2)
        custs = pg.evaluate('[...new Set(state.systems.map(s=>s.customerName))]')
        b.close()
    custs = ['__ALL__'] + custs
    chunks = [(i, custs[i::WORKERS]) for i in range(WORKERS)]
    t0 = time.time()
    with Pool(WORKERS) as pool:
        parts = pool.map(work, chunks)
    docs = {}
    for r in parts: docs.update(r)
    print(f'generated {len(docs)} scopes in {time.time()-t0:.0f}s')
    os.makedirs(OUT, exist_ok=True)
    issues = []
    names = [c for c in custs if c != '__ALL__']
    for c, d in docs.items():
        if '__error' in d:
            issues.append((c, 'ERROR', d['__error'])); continue
        safe = re.sub(r'[^A-Za-z0-9]+', '_', c)[:40]
        os.makedirs(os.path.join(OUT, safe), exist_ok=True)
        for k, v in d.items():
            open(os.path.join(OUT, safe, k + '.txt'), 'w', encoding='utf-8').write(v)
        for k, v in d.items():
            for pat in FORBIDDEN:
                m = re.search(r'^.*' + pat + r'.*$', v, re.M | re.I if pat.startswith('this') else re.M)
                if m: issues.append((c, k, f'{pat}: {m.group(0).strip()[:120]}'))
        if c != '__ALL__':
            for k, v in d.items():
                for o in names:
                    if o != c and len(o) > 8 and o not in c and c not in o and re.search(r'(?<![A-Za-z])' + re.escape(o) + r'(?![A-Za-z])', v):
                        issues.append((c, k, f'leaks customer name: {o}'))
            # cross-document agreement
            allt = '\n'.join(d.values())
            arp = set(re.findall(r'ARP (?:Coverage|Protection):\s+(?:\d+% \()?(\d+)/(\d+)', allt))
            if len(arp) > 1: issues.append((c, 'ALL', f'ARP fractions disagree: {sorted(arp)}'))
            oc = set(re.findall(r'Open cases: (\d+)', allt)) | set(re.findall(r'Open support cases: (\d+)', allt))
            if len(oc) > 1: issues.append((c, 'ALL', f'open case counts disagree: {sorted(oc)}'))
            lp = set(re.findall(r'LAPSED SUPPORT CONTRACTS \((\d+)\)', allt))
            if len(lp) > 1: issues.append((c, 'ALL', f'lapsed counts disagree: {sorted(lp)}'))
    from collections import Counter
    cnt = Counter((k, re.sub(r'\d+', 'N', m)[:60]) for c, k, m in issues)
    print('issues:', len(issues))
    for (k, m), n in cnt.most_common(40): print(f'{n:4d}  {k:22s} {m}')
    json.dump(issues, open(os.path.join(OUT, '_issues.json'), 'w'), indent=1)

if __name__ == '__main__':
    main()
