"""
Rear-panel coverage check for the Technical Audit drawings (app.js, _buildControllerBackplate).

For each ONTAP platform, reads NetApp's own install/cabling/setup text (the NetAppDocs/ontap-systems
AsciiDoc on GitHub, the same pages as docs.netapp.com/us-en/ontap-systems/<platform>/), extracts every
port name the text mentions (e2a, e4a through e4d, 2a through 2d, ...), feeds them to the drawing as if
Active IQ had reported them, and lists the ones the drawing has no position for.

Expected leftovers (documented, not drawing errors): e0a/e0b on the A20-A50/A70/A90/A1K/A900 pages are
NS224 shelf-module ports; 0a/0b/3a/3d are fixed SAS ports that are drawn but not "reported"; the
A250 page's e4a-e4d is an error in the web text (the 2024 PDF says 1a-1d / e1a-e1d).

Usage:  ARIA_URL=http://127.0.0.1:8080/ python tools/verify_rear_panels.py   (needs playwright + curl)
"""
import json, os, re, subprocess
from playwright.sync_api import sync_playwright

URL = os.environ.get('ARIA_URL', 'http://127.0.0.1:8080/')
RAW = 'https://raw.githubusercontent.com/NetAppDocs/ontap-systems/main/'
DIRS = {  # doc directory -> platform strings to test
    'a700': ['aff-a700'], 'fas9000': ['fas9000'], 'a900': ['aff-a900'], 'fas9500': ['fas9500'], 'a400': ['aff-a400'],
    'c400': ['aff-c400'], 'a800': ['aff-a800'], 'c800': ['aff-c800'], 'a250': ['aff-a250'], 'c250': ['aff-c250'],
    'fas500f': ['fas500f'], 'fas2800': ['fas2820'], 'a150': ['aff-a150'], 'a220': ['aff-a220'], 'c190': ['aff-c190'],
    'fas2700': ['fas2720'], 'a320': ['aff-a320'], 'a20-30-50': ['aff-a20', 'aff-a30', 'aff-a50'], 'c30-60': ['aff-c30', 'aff-c60'],
    'fas50': ['fas50'], 'a70-90': ['aff-a70', 'aff-a90'], 'a1k': ['aff-a1k'], 'fas-70-90': ['fas70', 'fas90'],
}

def curl(url):
    return subprocess.run(['curl', '-s', url], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout

def tokens(directory, tree):
    files = [x['path'] for x in tree if x['path'].startswith(directory + '/') and x['path'].endswith('.adoc')
             and re.search(r'install|cable|setup|io-module|key-spec|hardware|overview|network|port', x['path'], re.I)
             and not re.search(r'replace|bootmedia|chassis|dimm|fan|psu|battery|nvdimm|rtc|hotswap', x['path'], re.I)]
    txt = '\n'.join(curl(RAW + f) for f in files)
    eth, fc = set(), set()
    for m in re.finditer(r'\be(\d{1,2})([a-z])\b(?:\s*(?:through|to|-)\s*e?(\d{1,2})?([a-z])\b)?', txt):
        s1, l1, s2, l2 = m.groups(); eth.add(f'e{s1}{l1}')
        if l2 and (not s2 or s2 == s1):
            eth.update(f'e{s1}{chr(c)}' for c in range(ord(l1), ord(l2) + 1))
    for m in re.finditer(r'\bports?\s+(\d{1,2})([a-d])(?:\s*(?:through|to)\s*(\d{1,2})?([a-d]))?', txt):
        s1, l1, s2, l2 = m.groups(); fc.add(f'{s1}{l1}')
        if l2:
            fc.update(f'{s1}{chr(c)}' for c in range(ord(l1), ord(l2) + 1))
    return sorted(eth), sorted(fc)

JS = r"""(jobs)=>jobs.map(j=>{const mk=(n,t)=>({name:n,type:t,status:'online',details:{speed:'10 Gbps'}});
  const ports=[mk('e0M','mgmt'),...j.eth.map(n=>mk(n,/^e0[ab]$|^e\d+a$/.test(n)?'cluster':'data')),...j.fc.map(n=>mk(n,'fc'))];
  const s={platform:j.plat,systemName:'x-01',serialNumber:'x'};let h='';try{h=_buildControllerBackplate(s,ports,j.plat,false,false,false)}catch(e){return {plat:j.plat,err:e.message}}
  const m=h.match(/Other reported ports \(no position on this drawing\): ((?:<code[^>]*>[^<]*<\/code>(?:, )?)+)/);
  return {plat:j.plat,unplaced:m?[...m[1].matchAll(/<code[^>]*>([^<]*)<\/code>/g)].map(x=>x[1]):[]}})"""

if __name__ == '__main__':
    tree = json.loads(curl('https://api.github.com/repos/NetAppDocs/ontap-systems/git/trees/main?recursive=1'))['tree']
    jobs = []
    for d, plats in DIRS.items():
        eth, fc = tokens(d, tree)
        jobs += [{'dir': d, 'plat': p, 'eth': eth, 'fc': fc} for p in plats]
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(URL)
        pg.wait_for_function('typeof _buildControllerBackplate === "function"', timeout=120000)
        for r in pg.evaluate(JS, jobs):
            print(r['plat'], r.get('err') or ('all placed' if not r['unplaced'] else 'no position for: ' + ', '.join(r['unplaced'])))
        b.close()
