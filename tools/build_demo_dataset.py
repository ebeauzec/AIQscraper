#!/usr/bin/env python3
"""Build data/demo_dataset.json -- the anonymized, real-shaped telemetry ARIA's
Demo (mock) mode uses to show every feature.

The hand-written MOCK_SYSTEMS in app.js only carry a small subset of the fields a
real Active IQ harvest returns (no firmware, shelves, ports, licenses, ASUP history,
SVM/LIF detail, TAM recommendations, sites, OS catalogue...). Rather than invent
those, this tool copies real structures from a live harvest and strips everything
that identifies the source account:

  * customer / site / host / cluster / contact / reseller names, e-mails, phones
  * serial numbers, licence serials, ASUP ids, MAC / IP / WWPN addresses
  * vserver, LIF, ipspace and broadcast-domain names (rebuilt generically)

Only technical values survive: firmware versions, drive/shelf models, licence
packages, port roles, protocol mixes, ASUP cadence, score histories, generic
Active IQ risk/recommendation catalogue text and NetApp's public OS catalogue.
Dates are kept as-is and shifted to "now" at load time (see harvestedAt).

Usage:
    python tools/build_demo_dataset.py [harvest.json]

With no argument the live server's cached harvest is fetched from
http://localhost:8080/api/harvest. A final scan fails the build if any identifying
token from the source harvest is still present in the output.
"""
import json
import os
import random
import re
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'demo_dataset.json')
RNG = random.Random(20260921)

COMMON = ['productType', 'systemState', 'techRefreshStatus', 'serviceTier', 'marketingType',
          'storageConfiguration', 'operatingMode', 'propensityCategory', 'hasPvr', 'serviceLevel',
          'systemType', 'asupStatus', 'asupTransport', 'asupOnDemand', 'asupHistory', 'asupByType',
          'sustainabilityScores', 'autoUpdateSettings', 'autoUpdateEnabled', 'personality']
ONTAP_ONLY = ['isAllFlashOptimized', 'isARPEnabled', 'isFabricPool', 'systemFirmware',
              'motherboardFirmware', 'diskQualificationPackage', 'recommendedDriveFirmwares',
              'recommendedShelfFirmwares', 'shelves', 'networkPorts', 'aggregateDetail', 'licenses',
              'consistencyGroupCount', 'storageUnitCount']

GENERIC_WORDS = {
    'aff', 'asa', 'fas', 'com', 'one', 'series', 'support', 'system', 'systems', 'health', 'tech', 'exp', 'rep',
    'clus', 'clust', 'ntap', 'center', 'centre', 'dept', 'applied', 'choice', 'art', 'bay', 'communications',
    'tele', 'telecom', 'net', 'org', 'local', 'corp', 'inc', 'ltd', 'llc', 'cluster', 'node', 'data', 'nas', 'san',
    'svm', 'prod', 'production', 'backup', 'test', 'company', 'group', 'limited', 'services', 'solutions',
    'technologies', 'corporation', 'the', 'and', 'for', 'storage', 'default', 'mgmt', 'management', 'replication',
    'netapp', 'netapp.com', 'unknown', 'customer', 'n/a', 'none', 'enterprise', 'international', 'global', 'national', 'only', 'public', 'home',
    'hosting', 'information', 'environments', 'environment', 'private', 'cloud', 'hybrid', 'digital', 'network',
    'networks', 'security', 'infrastructure', 'general', 'primary', 'secondary', 'disaster', 'recovery',
}


def family(s):
    p, m = str(s.get('platformType') or ''), str(s.get('model') or '')
    st = str(s.get('systemType') or '').upper()
    if (s.get('productType') or '') == 'SWApp' or m.lower().startswith(('sg', 'storagegrid')):
        return 'storagegrid'
    if st in ('EFILER',) or re.match(r'^(28|29|40|57|60)\d{2}$|^600$', m) or s.get('eseriesCapacity'):
        return 'eseries'
    if st == 'CLOUDONTAP' or m.upper() == 'CLOUD':
        return 'cvo'
    return 'ontap'


# ── identity tokens -----------------------------------------------------------------
def identity_tokens(systems):
    raw = set()
    for s in systems:
        for k in ('customerName', 'domesticParentName', 'nagpName', 'siteName', 'systemName', 'clusterName',
                  'contactFirstName', 'contactLastName', 'salesRepName', 'csmName', 'samName', 'aspName',
                  'resellerCompany', 'asupDomain', 'siteCity'):
            v = s.get(k)
            if isinstance(v, str) and v.strip():
                raw.add(v.strip())
        for k in ('contactEmail', 'salesRepEmail', 'csmEmail', 'samEmail'):
            v = s.get(k)
            if isinstance(v, str) and '@' in v:
                raw.add(v.split('@')[1])
                raw.add(v.split('@')[0])
    toks = set()
    for v in raw:
        if v.lower() not in GENERIC_WORDS:
            toks.add(v.lower())
        for t in re.split(r'[^A-Za-z0-9]+', v):
            if len(t) >= 3 and t.lower() not in GENERIC_WORDS and not t.isdigit():
                toks.add(t.lower())
    code_like = re.compile(r'^([a-z]{1,3}\d{1,4}[a-z]?|\d+[a-z]{0,2}|n\d+|c\d+|a\d+k?|[a-z]\d{2,4})$')
    return {t for t in toks if len(t) >= 4 and not code_like.match(t)}


# ── fake-value factories -------------------------------------------------------------
class Fake:
    def __init__(self):
        self.n = 0

    def serial(self, prefix='SHF'):
        self.n += 1
        return f'{prefix}{700000000 + self.n * 37:012d}'

    def mac(self):
        return '02:de:%02x:%02x:%02x:%02x' % tuple(RNG.randrange(256) for _ in range(4))

    def ip(self):
        return '10.%d.%d.%d' % (RNG.randrange(20, 60), RNG.randrange(0, 250), RNG.randrange(2, 250))

    def wwpn(self):
        return '20:%02x:00:a0:98:de:%02x:%02x' % (RNG.randrange(8, 32), RNG.randrange(256), RNG.randrange(256))


F = Fake()


def scrub_shelves(shelves):
    out = []
    for sh in (shelves or [])[:8]:
        sh = json.loads(json.dumps(sh))
        sh['serialNumber'] = F.serial('SHF')
        out.append(sh)
    return out


def scrub_ports(np):
    if not np or not np.get('networkPorts'):
        return np or {}
    domains, spaces = {}, {}
    ports = []
    for p in np['networkPorts']:
        p = dict(p)
        p['macAddress'] = F.mac()
        bd = p.get('broadcastDomain')
        if bd:
            low = bd.lower()
            prole = (p.get('role') or '').upper()
            role = ('Cluster' if 'cluster' in low or prole == 'CLUSTER' else
                    'Mgmt' if 'mgmt' in low or 'man' in low or prole in ('NODE_MGMT', 'CLUSTER_MGMT') else
                    'replication' if 'repl' in low or bd.lower().endswith('dr') else 'data')
            domains.setdefault(bd, f'{role}_bd{len(domains) + 1}' if role != 'Cluster' else 'Cluster')
            p['broadcastDomain'] = domains[bd]
        ips = p.get('ipspaceName')
        if ips and ips not in ('Default', 'Cluster'):
            spaces.setdefault(ips, f'ipspace_{len(spaces) + 1}')
            p['ipspaceName'] = spaces[ips]
        ports.append(p)
    return {'totalCount': np.get('totalCount', len(ports)), 'networkPorts': ports}


def scrub_licenses(lic):
    m, out = {}, []
    for l in (lic or []):
        l = dict(l)
        k = l.get('licenseSerialNumber')
        if k not in m:
            m[k] = '1-81-%019d' % (len(m) + 1)
        l['licenseSerialNumber'] = m[k]
        out.append(l)
    return out


def scrub_asup(hist):
    out = []
    for i, a in enumerate(hist or []):
        a = dict(a)
        a['asupId'] = re.sub(r'\D', '', str(a.get('receivedDate', '')))[:14] + '%02d' % (i % 100)
        subj = a.get('subject') or ''
        a['subject'] = re.sub(r'\bfrom\s+\S+', 'from cluster', subj)
        out.append(a)
    return out


def scrub_vservers(vs, node_names):
    """Rebuild vservers with generic names; nodes become {{nodeN}} tokens."""
    idx = {n: i + 1 for i, n in enumerate(sorted(node_names))}
    out, n_data = [], 0
    for v in vs or []:
        if v.get('type') != 'DATA':
            continue
        n_data += 1
        lifs = []
        protos = set()
        for j, l in enumerate(v.get('logicalInterfaces') or []):
            l = json.loads(json.dumps(l))
            dp = (l.get('serviceConfiguration') or {}).get('dataProtocols') or []
            protos.update(dp)
            l['name'] = f'lif_{n_data}_{j + 1}'
            if l.get('ipAddress'):
                l['ipAddress'] = F.ip()
            if l.get('worldWidePortName'):
                l['worldWidePortName'] = F.wwpn()
            fc = l.get('failoverConfiguration') or {}
            for key in ('homeNode', 'currentNode'):
                node = fc.get(key) or {}
                hn = node.get('hostName')
                if hn:
                    fc[key] = {'hostName': '{{node%d}}' % idx.get(hn, 1), 'serialNumber': '{{serial}}'}
            l['failoverConfiguration'] = fc
            lifs.append(l)
        kind = 'san' if protos and protos <= {'FCP', 'ISCSI', 'NVME_TCP', 'NVME_FC'} else 'nas' if protos & {'NFS', 'CIFS'} else 'data'
        out.append({'id': '00000000-0000-0000-0000-%012d' % n_data, 'name': f'svm_{kind}_{n_data}',
                    'type': 'DATA', 'subType': v.get('subType'), 'logicalInterfaces': lifs[:16]})
        if n_data >= 5:
            break
    return out


def build_profile(s, fam):
    p = {'_family': fam, '_sourceModel': s.get('model')}
    for k in COMMON:
        if s.get(k) not in (None, '', [], {}):
            p[k] = s[k]
    if fam in ('ontap', 'cvo', 'storagegrid', 'eseries'):
        for k in ONTAP_ONLY:
            if fam in ('storagegrid', 'eseries') and k not in ('shelves', 'licenses'):
                continue
            if s.get(k) not in (None, '', [], {}):
                p[k] = s[k]
    if 'shelves' in p:
        p['shelves'] = scrub_shelves(p['shelves'])
        models = {d['hardwareModel']['name'] for sh in p['shelves'] for d in (sh.get('drives') or {}).get('drives', [])
                  if (d.get('hardwareModel') or {}).get('name')}
        if 'recommendedDriveFirmwares' in p:
            p['recommendedDriveFirmwares'] = {k: v for k, v in p['recommendedDriveFirmwares'].items() if k in models}
    if 'networkPorts' in p:
        p['networkPorts'] = scrub_ports(p['networkPorts'])
    if 'licenses' in p:
        p['licenses'] = scrub_licenses(p['licenses'])
    for k in ('asupHistory', 'asupByType'):
        if k in p:
            p[k] = scrub_asup(p[k])
    if fam in ('ontap', 'cvo'):
        nodes = [x['systemName'] for x in ALL if x.get('clusterName') == s.get('clusterName') and x.get('systemName')]
        vs = scrub_vservers(s.get('vservers'), nodes or [s.get('systemName')])
        if vs:
            p['vservers'] = vs
    p['_bulletinCount'] = 0
    return p


def pick_profiles(systems, fam, want, need):
    pool = [s for s in systems if family(s) == fam and all(s.get(k) for k in need)]
    RNG.shuffle(pool)
    seen_model, picked = set(), []
    for s in pool:
        m = s.get('model')
        if m in seen_model and len(picked) < want // 2:
            continue
        seen_model.add(m)
        picked.append(s)
        if len(picked) >= want:
            break
    if len(picked) < want:
        for s in pool:
            if s not in picked:
                picked.append(s)
            if len(picked) >= want:
                break
    return picked


def scrub_text(s):
    s = re.sub(r'\b\d{1,3}(\.\d{1,3}){3}\b', '10.0.0.1', s)
    s = re.sub(r'\S+@\S+', 'admin@example.com', s)
    return s


def main():
    global ALL
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if src:
        d = json.load(open(src, encoding='utf-8'))
    else:
        d = json.load(urllib.request.urlopen('http://localhost:8080/api/harvest', timeout=300))
    ALL = d['systems']
    toks = identity_tokens(ALL)
    now = datetime.now(timezone.utc).isoformat()

    profiles = {
        'ontap': [build_profile(s, 'ontap') for s in pick_profiles(ALL, 'ontap', 18, ['shelves', 'networkPorts', 'licenses', 'vservers', 'asupHistory'])],
        'cvo': [build_profile(s, 'cvo') for s in pick_profiles(ALL, 'cvo', 2, [])],
        'eseries': [build_profile(s, 'eseries') for s in pick_profiles(ALL, 'eseries', 4, ['asupHistory'])],
        'storagegrid': [build_profile(s, 'storagegrid') for s in pick_profiles(ALL, 'storagegrid', 4, [])],
    }

    # Risk / case pools (Active IQ catalogue text; identifying rows dropped by the scan below)
    seen, risk_pool = set(), []
    for s in ALL:
        for r in s.get('risks') or []:
            if r.get('riskId') in seen:
                continue
            seen.add(r.get('riskId'))
            r = json.loads(json.dumps(r))
            r['_family'] = family(s)
            risk_pool.append(r)
    RNG.shuffle(risk_pool)
    risk_pool = risk_pool[:220]

    case_pool = []
    for c in d.get('cases') or []:
        c = {k: c.get(k) for k in ('symptom', 'description', 'status', 'priority', 'highestPriority', 'created',
                                    'lastUpdated', 'closed', 'type', 'category', 'subCategory', 'caseReceivedVia')}
        c['symptom'] = scrub_text(c.get('symptom') or '')
        c['reporterContact'] = {'name': 'Customer Contact'}
        case_pool.append(c)
    RNG.shuffle(case_pool)
    case_pool = case_pool[:60]

    # Root datasets
    acct = d['tamRecommendations'][0].get('accountId') if d.get('tamRecommendations') else None
    def first_acct(rows):
        return [r for r in rows if r.get('accountId') == acct] or rows

    def tag(rows):
        out = []
        for r in rows:
            r = dict(r)
            r['accountId'] = 'demo-account'
            r['accountLabel'] = 'Demo Account'
            out.append(r)
        return out

    tam_recs = tag(first_acct(d.get('tamRecommendations') or []))
    tam_sust = tag(first_acct(d.get('tamSustainability') or []))
    tam_hs = tag(first_acct(d.get('tamOfficialHealthScore') or []))
    cust_recs = [c['recommendations'] for c in (d.get('tamCustomerRecommendations') or []) if c.get('recommendations')]
    cust_hs = [c.get('overallHealthScore') for c in (d.get('tamCustomerHealthScores') or []) if c.get('overallHealthScore') is not None]

    ontap_versions = [v for v in d.get('tamOsVersions') or [] if v.get('osType') == 'ONTAP']
    other_versions = [v for v in d.get('tamOsVersions') or [] if v.get('osType') != 'ONTAP']
    def rel(v):
        m = re.match(r'(\d+)\.(\d+)(?:P(\d+))?', v.get('osVersion') or '')
        return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else (0, 0, 0)
    ontap_versions.sort(key=rel, reverse=True)
    os_versions = []
    for i, v in enumerate(ontap_versions):
        v = dict(v)
        if i >= 60:  # keep bundled firmware catalogues for the newest releases only
            for k in ('bundledSystemFirmwares', 'bundledDriveFirmwares', 'bundledShelfFirmwares', 'bundledSecurityFiles'):
                v[k] = []
        os_versions.append(v)
    for v in other_versions:
        v = dict(v)
        v['bundledDriveFirmwares'] = (v.get('bundledDriveFirmwares') or [])[:40]
        os_versions.append(v)

    global_risks = []
    for r in d.get('risks') or []:
        global_risks.append({'id': r.get('riskId') or 0, 'severity': (r.get('severity') or 'medium').lower(),
                             'category': r.get('category') or 'General',
                             'description': r.get('shortName') or r.get('riskDetail') or 'Risk identified',
                             'recommendation': r.get('potentialImpact') or 'Review and remediate.'})
    RNG.shuffle(global_risks)
    global_risks = global_risks[:320]

    out = {'meta': {'builtAt': now, 'harvestedAt': now,
                    'note': 'Anonymized structures derived from a real Active IQ harvest. No customer identifiers.'},
           'profiles': profiles, 'riskPool': risk_pool, 'casePool': case_pool,
           'roots': {'tamRecommendations': tam_recs, 'tamSustainability': tam_sust, 'tamOfficialHealthScore': tam_hs,
                     'customerRecommendationSets': cust_recs[:14], 'customerHealthScores': cust_hs,
                     'tamOsVersions': os_versions, 'globalRisks': global_risks}}

    # ── leak scan: fail the build on any surviving identifier ────────────────────────
    blob = json.dumps(out, ensure_ascii=False)
    low = blob.lower()
    leaks = sorted(t for t in toks if re.search(r'(?<![a-z0-9])' + re.escape(t) + r'(?![a-z0-9])', low))
    ipv4 = set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', blob))
    ipv4 = {i for i in ipv4 if not i.startswith('10.0.0.') and not re.match(r'^\d+\.\d+\.\d+\.\d+$', i) is None and
            i.split('.')[0] == '10'}
    emails = set(re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', blob))
    print('profiles:', {k: len(v) for k, v in profiles.items()}, 'risks:', len(risk_pool), 'cases:', len(case_pool),
          'osVersions:', len(os_versions), 'globalRisks:', len(global_risks), 'size KB:', len(blob) // 1024)
    if leaks or emails:
        print('LEAKING IDENTIFIERS:', leaks[:40], list(emails)[:10])
        # Drop offending pool rows automatically and re-check
        def dirty(x):
            t = json.dumps(x, ensure_ascii=False).lower()
            return any(re.search(r'(?<![a-z0-9])' + re.escape(tok) + r'(?![a-z0-9])', t) for tok in leaks)
        out['riskPool'] = [r for r in out['riskPool'] if not dirty(r)]
        out['casePool'] = [c for c in out['casePool'] if not dirty(c)]
        out['roots']['globalRisks'] = [r for r in out['roots']['globalRisks'] if not dirty(r)]
        out['roots']['tamRecommendations'] = [r for r in out['roots']['tamRecommendations'] if not dirty(r)]
        out['roots']['customerRecommendationSets'] = [
            [r for r in rs if not dirty(r)] for rs in out['roots']['customerRecommendationSets']]
        for fam_, plist in out['profiles'].items():
            out['profiles'][fam_] = [p for p in plist if not dirty(p)]
        blob = json.dumps(out, ensure_ascii=False)
        low = blob.lower()
        leaks = sorted(t for t in toks if re.search(r'(?<![a-z0-9])' + re.escape(t) + r'(?![a-z0-9])', low))
        print('after dropping dirty rows -> remaining leaks:', leaks[:40])
        if leaks:
            print('BUILD FAILED: identifiers remain; not writing output')
            sys.exit(2)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(blob)
    print('wrote', OUT, len(blob) // 1024, 'KB')


if __name__ == '__main__':
    main()
