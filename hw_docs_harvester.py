"""
Hardware documentation harvester for ARIA.

Pulls the current slot / port / module facts for every NetApp platform from NetApp's official
documentation source (the NetAppDocs AsciiDoc that publishes docs.netapp.com/us-en/ontap-systems)
and writes data/platform_hardware.json. The Technical Audit rear panel uses it to label slots with
their documented role, and tools/verify_rear_panels.py uses the same parser to check the drawings.

Only facts are stored (port names, slot numbers, roles, speeds, short evidence phrases, source URL),
never whole pages. Offline / dark-site safe: every network step is optional, failures leave the
existing file untouched, and the app works without it.

  python hw_docs_harvester.py            # refresh data/platform_hardware.json
  python hw_docs_harvester.py a20-30-50  # one platform directory, print only
"""
import json, os, re, sys, time, urllib.request
from datetime import datetime, timezone

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'platform_hardware.json')
REPO = 'NetAppDocs/ontap-systems'
RAW = 'https://raw.githubusercontent.com/%s/main/' % REPO
SITE = 'https://docs.netapp.com/us-en/ontap-systems/'
UA = 'ARIA-hardware-docs-harvester (+local desktop tool)'

# documentation directory -> model names it covers
PLATFORMS = {
    'a20-30-50': ['AFF A20', 'AFF A30', 'AFF A50'], 'c30-60': ['AFF C30', 'AFF C60'], 'fas50': ['FAS50'],
    'a70-90': ['AFF A70', 'AFF A90'], 'fas-70-90': ['FAS70', 'FAS90'], 'a1k': ['AFF A1K'],
    'a250': ['AFF A250'], 'c250': ['AFF C250'], 'fas500f': ['FAS500f'], 'a400': ['AFF A400'], 'c400': ['AFF C400'],
    'a800': ['AFF A800'], 'c800': ['AFF C800'], 'a900': ['AFF A900'], 'fas9500': ['FAS9500'], 'a700': ['AFF A700'],
    'fas9000': ['FAS9000'], 'a700s': ['AFF A700s'], 'a320': ['AFF A320'], 'a300': ['AFF A300'], 'fas8200': ['FAS8200'],
    'fas8300': ['FAS8300', 'FAS8700'], 'fas2800': ['FAS2820'], 'a150': ['AFF A150'], 'a220': ['AFF A220'],
    'c190': ['AFF C190'], 'fas2700': ['FAS2720', 'FAS2750'], 'afx-1k': ['AFX 1K'], 'afx-2k': ['AFX 2K'],
}
DOC_FILE = re.compile(r'(install|cable|setup|io-module|key-spec|hardware|overview|network|port)', re.I)
DOC_SKIP = re.compile(r'(replace|bootmedia|chassis|dimm|fan|psu|battery|nvdimm|rtc|hotswap|videos|worksheet|linkout)', re.I)

ROLES = [  # (role tag, regex)
    ('cluster/ha', r'cluster|\bHA\b|interconnect|mirroring'), ('management', r'management|wrench|BMC'),
    ('host/data', r'host|data network|data or host|client'), ('shelf/storage', r'shelf|NS224|NSM|IOM|SAS'),
    ('fc', r'\bFC\b|Fibre Channel'), ('ethernet', r'Ethernet|GbE|iSCSI|RoCE'),
]
PRIORITY = ['cluster/ha', 'shelf/storage', 'fc', 'host/data', 'ethernet', 'management']


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def _ports_in(line):
    """Port names mentioned in a line: eNx (Ethernet), Nx (FC/SAS after 'port'), with 'through' ranges."""
    eth, fc = set(), set()
    for m in re.finditer(r'\be(\d{1,2})([a-z])\b(?:\s*(?:through|to|-)\s*e?(\d{1,2})?([a-z])\b)?', line):
        s1, l1, s2, l2 = m.groups(); eth.add('e%s%s' % (s1, l1))
        if l2 and (not s2 or s2 == s1):
            eth.update('e%s%s' % (s1, chr(c)) for c in range(ord(l1), ord(l2) + 1))
    for m in re.finditer(r'\bports?\s+(\d{1,2})([a-d])(?:\s*(?:through|to|and)\s*(\d{1,2})?([a-d]))?', line):
        s1, l1, s2, l2 = m.groups(); fc.add('%s%s' % (s1, l1))
        if l2 and (not s2 or s2 == s1):
            fc.update('%s%s' % (s1, chr(c)) for c in range(ord(l1), ord(l2) + 1))
    return sorted(eth), sorted(fc)


def _slots_in(line):
    """Slot numbers the line names explicitly ("slot 4", "slots 2 and 4", "Slot A4 and B4")."""
    out = set()
    for m in re.finditer(r'\bslots?\s+((?:[AB]?\d{1,2})(?:\s*(?:,|and|&|or)\s*[AB]?\d{1,2})*)', line, re.I):
        out.update(int(x) for x in re.findall(r'\d{1,2}', m.group(1)))
    return sorted(x for x in out if x > 0)


def _clean(text):
    lines = []
    for ln in text.splitlines():
        t = ln.strip()
        if not t or t.startswith('//') or t.startswith('image:') or t.startswith('include::') or t.startswith(':'):
            continue
        t = re.sub(r'link:[^\[]*\[([^\]]*)\]', r'\1', t)
        t = re.sub(r'https?://\S+', '', t)
        t = re.sub(r'[*_`+^]', '', t)
        lines.append(t)
    return lines


def parse_platform(directory, files):
    """files: {path: text}. Returns the structured facts for one documentation directory.

    Ports get their roles from any line that names them; slots only get a role from lines that name
    the slot explicitly, so a label on the drawing always rests on a sentence that says it."""
    facts = {'models': PLATFORMS.get(directory, []), 'keySpecs': {}, 'slots': {}, 'ports': {}, 'modules': [], 'slotTable': {}, 'sources': []}
    for path, text in files.items():
        facts['sources'].append(SITE + path.replace('.adoc', '.html'))
        module = ''
        for ln in _clean(text):
            if re.match(r'^\.[^\s.]', ln) and len(ln) < 140:
                module = ln.lstrip('.').strip()
                if re.search(r'port|module', module, re.I) and module not in facts['modules']:
                    facts['modules'].append(module)
            m = re.match(r'(Form Factor|PCIe Expansion Slots):\s*(.+)', ln)
            if m:
                facts['keySpecs'][m.group(1)] = m.group(2)
            m = re.match(r'Protocol:\s*(.+?);\s*Ports:\s*(\d+)', ln)
            if m:
                facts['keySpecs'].setdefault('IO protocols', []).append('%s x%s (per HA pair)' % (m.group(1), m.group(2)))
            eth, fc = _ports_in(ln)
            slots = _slots_in(ln)
            roles = [tag for tag, rx in ROLES if re.search(rx, ln, re.I)]
            if not (eth or fc or slots) or not roles:
                continue
            ev = ln[:170]
            speed = sorted({x.strip() for x in re.findall(r'(\d[\d/]*\s*GbE|\d+\s*Gb/?s?\s*FC|12\s*Gb/?s\s*SAS)', ln + ' ' + module)})
            for pn in list(eth) + list(fc):
                e = facts['ports'].setdefault(pn, {'roles': [], 'evidence': [], 'speed': []})
                e['roles'] = sorted(set(e['roles']) | set(roles))
                e['speed'] = sorted(set(e['speed']) | set(speed))
                if ev not in e['evidence'] and len(e['evidence']) < 2:
                    e['evidence'].append(ev)
            for sn in slots:
                e = facts['slots'].setdefault(str(sn), {'roles': [], 'ports': [], 'evidence': []})
                e['roles'] = sorted(set(e['roles']) | set(roles))
                e['ports'] = sorted(set(e['ports']) | set(p for p in list(eth) + list(fc) if re.match(r'e?%d[a-z]$' % sn, p)))
                if ev not in e['evidence'] and len(e['evidence']) < 2:
                    e['evidence'].append(ev)
        # "I/O slot numbering" tables (AFX): icon_round_N callouts followed by the slot's role
        for m in re.finditer(r'icon_round_(\d+)\.svg\[[^\]]*\]\s*(?:\n\s*image::[^\n]*icon_round_(\d+)\.svg\[[^\]]*\]\s*)?\n\|\s*([^\n|]+)', text):
            a, b, role = m.group(1), m.group(2), m.group(3).strip()
            for k in ([a] + ([b] if b else [])):
                facts['slotTable'][k] = re.sub(r'[*()]', '', role).strip()
    if not facts['slotTable']:
        del facts['slotTable']
    # one short display label per slot: the most specific role, plus the module speed when the text gives one
    for sn, e in facts['slots'].items():
        role = next((r for r in PRIORITY if r in e['roles']), e['roles'][0] if e['roles'] else '')
        sp = sorted({x for q in e['ports'] for x in facts['ports'].get(q, {}).get('speed', [])})
        e['label'] = (role.upper() + (' ' + sp[0] if sp else '')) if role else ''
    return facts


def harvest(only=None, log=print):
    """Fetch and parse; returns the full document, or None when the source is unreachable."""
    try:
        tree = json.loads(_get('https://api.github.com/repos/%s/git/trees/main?recursive=1' % REPO, 40))['tree']
    except Exception as e:
        log('  [HWDOCS] documentation tree unreachable (%s) - keeping existing data' % e)
        return None
    doc = {'fetchedAt': datetime.now(timezone.utc).isoformat()[:19] + 'Z', 'source': 'NetApp documentation (NetAppDocs/ontap-systems, docs.netapp.com/us-en/ontap-systems)', 'platforms': {}}
    for d in PLATFORMS:
        if only and d != only:
            continue
        paths = [x['path'] for x in tree if x['path'].startswith(d + '/') and x['path'].endswith('.adoc') and DOC_FILE.search(x['path']) and not DOC_SKIP.search(x['path'])]
        files = {}
        for p in paths[:14]:
            try:
                files[p] = _get(RAW + p)
            except Exception:
                continue
            time.sleep(0.15)
        if files:
            doc['platforms'][d] = parse_platform(d, files)
            log('  [HWDOCS] %-10s %2d pages, %2d slots, %2d ports' % (d, len(files), len(doc['platforms'][d]['slots']), len(doc['platforms'][d]['ports'])))
    return doc


def refresh(log=print):
    """Harvest everything and write data/platform_hardware.json (never raises)."""
    try:
        doc = harvest(log=log)
        if not doc or not doc['platforms']:
            return {'updated': False}
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        tmp = OUT_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
        os.replace(tmp, OUT_PATH)
        log('  [HWDOCS] platform_hardware.json updated: %d platform documents' % len(doc['platforms']))
        return {'updated': True, 'platforms': len(doc['platforms'])}
    except Exception as e:
        log('  [HWDOCS] refresh failed: %s' % e)
        return {'updated': False, 'error': str(e)}


if __name__ == '__main__':
    if len(sys.argv) > 1:
        r = harvest(only=sys.argv[1])
        print(json.dumps(r['platforms'] if r else None, indent=1)[:6000])
    else:
        print(refresh())
