"""
Match new partners only — runs the same v5e model as partner_match.py
but on the 342 new partners from new_partners_raw.json.
Outputs new_partners_matched.json in the same schema as dashboard_data.json.
"""
import json, re, os, sys
from collections import Counter, defaultdict

BASE = '/sessions/dreamy-ecstatic-heisenberg/partner-outreach'

# ── LOAD MODEL DATA ──
with open(f'{BASE}/firms_inventory.json') as f:
    firms_inv = json.load(f)
with open(f'{BASE}/target_firms_full.json') as f:
    target_firms = json.load(f)
with open(f'{BASE}/chambers_rankings.json') as f:
    ch_data = json.load(f)
with open(f'{BASE}/firm_ppp.json') as f:
    firm_ppp_data = json.load(f)
with open(f'{BASE}/feeder_scores.json') as f:
    feeder_scores = json.load(f)

supp_path = f'{BASE}/supplemental_firms.json'
supplemental_firms = []
if os.path.exists(supp_path):
    with open(supp_path) as f:
        supplemental_firms = json.load(f)
    print(f"Loaded {len(supplemental_firms)} supplemental firms")

SIGNED_NAMES = {tf['name'] for tf in target_firms}
RANKINGS = ch_data['rankings']
ALIASES  = ch_data['aliases']

# ── LOAD NEW PARTNERS ──
with open(f'{BASE}/new_partners_raw.json') as f:
    new_partners = json.load(f)
print(f"Processing {len(new_partners)} new partners")

# ── BIO HOOK EXTRACTION ──
_bio_hook_patterns = [
    r'(?:focuses?\s+(?:her|his|their)\s+practice\s+on|focus(?:es|ing)?\s+on)\s+(.+?)(?:\.|,\s*(?:with|including|and\s+has))',
    r'(?:specializ(?:es|ing)\s+in)\s+(.+?)(?:\.|,\s*(?:with|including|and))',
    r'(?:concentrat(?:es|ing)\s+(?:her|his|their)\s+practice\s+(?:in|on))\s+(.+?)(?:\.|,)',
    r'(?:practice\s+(?:is\s+)?(?:focused|centered|concentrated)\s+(?:on|in))\s+(.+?)(?:\.|,)',
    r'(?:represents?\s+clients\s+in)\s+(.+?)(?:\.|,\s*(?:with|including|and))',
    r'(?:advises?\s+(?:clients\s+)?(?:on|in))\s+(.+?)(?:\.|,\s*(?:with|including))',
]

for p in new_partners:
    bio = p.get('bio', '') or p.get('jaide', '') or ''
    if not bio:
        p['bio_hook'] = ''
        continue
    bio_clean = re.sub(r'"[^"]*"', ' ', bio)
    bio_clean = re.sub(r'\u201c[^\u201d]*\u201d', ' ', bio_clean)
    bio_clean = re.sub(r'Chambers\s+USA\s+\d{4}', ' ', bio_clean)
    hook = ''
    for pattern in _bio_hook_patterns:
        m = re.search(pattern, bio_clean, re.I)
        if m:
            hook = m.group(1).strip()[:120]
            break
    p['bio_hook'] = hook
    p['full_bio'] = bio_clean

hook_count = sum(1 for p in new_partners if p.get('bio_hook'))
print(f"Bio hooks extracted: {hook_count}/{len(new_partners)}")

# ── BUILD MOVE MATRIX ──
import glob, pandas as pd

direct_moves = defaultdict(Counter)
practice_dest = defaultdict(Counter)
dest_total_inbound = Counter()

def parse_moves(moves_str):
    if not moves_str or str(moves_str) == 'nan':
        return []
    parts = re.split(r'\s*->\s*', str(moves_str))
    firms = []
    for part in parts:
        firm = re.sub(r'\s*\([^)]*\)\s*$', '', part).strip()
        if firm:
            firms.append(firm)
    return firms

def ingest_lateral_moves(df, label):
    count = 0
    for _, row in df.iterrows():
        firms = parse_moves(row.get('Lateral Moves'))
        practice = str(row.get('Practice Areas', ''))
        for i in range(len(firms) - 1):
            src, dst = firms[i], firms[i+1]
            direct_moves[src][dst] += 1
            dest_total_inbound[dst] += 1
            count += 1
            if practice and practice != 'nan':
                for pa in practice.split(','):
                    pa = pa.strip()
                    if pa:
                        practice_dest[pa][dst] += 1
    print(f"  [{label}] {count} moves from {len(df)} records")
    return count

total = 0
attrition_path = '/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/TO TRAIN MODEL ON ATTRITION.xlsx'
try:
    total += ingest_lateral_moves(pd.read_excel(attrition_path), 'Attrition training')
except FileNotFoundError:
    print("  [Attrition training] Not found, skipping")

attorneys_files = glob.glob('/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/Attorneys*.xlsx')
for af in attorneys_files:
    try:
        total += ingest_lateral_moves(pd.read_excel(af), f'Attorneys')
    except Exception as e:
        print(f"  [Attorneys] Error: {e}")

linkedin_path = '/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/LINKEDIN CONNECTED PARTNERS.xlsx'
try:
    ldf = pd.read_excel(linkedin_path)
    if 'Lateral Moves' in ldf.columns:
        total += ingest_lateral_moves(ldf, 'LinkedIn')
except FileNotFoundError:
    pass

print(f"  TOTAL: {total} moves parsed")

# ── NORMALIZE HELPERS ──
_norm_cache = {}
def _normalize_for_match(name):
    if name in _norm_cache: return _norm_cache[name]
    if not name:
        _norm_cache[name] = ''
        return ''
    n = name.strip()
    n = re.sub(r'\s*(LLP|LLC|PC|PLLC|PA|LP|LTD|P\.C\.|P\.A\.|L\.L\.P\.)\s*$', '', n, flags=re.I)
    n = re.sub(r',\s*$', '', n).strip().lower()
    _norm_cache[name] = n
    return n

norm_moves = defaultdict(Counter)
for raw_src, dests in direct_moves.items():
    sn = _normalize_for_match(raw_src)
    for raw_dst, cnt in dests.items():
        dn = _normalize_for_match(raw_dst)
        norm_moves[sn][dn] += cnt

_all_src_norms = list(norm_moves.keys())
norm_practice_dest = {}
norm_practice_total = {}
for pa, dest_counts in practice_dest.items():
    nd = Counter()
    for raw_dst, cnt in dest_counts.items():
        nd[_normalize_for_match(raw_dst)] += cnt
    norm_practice_dest[pa] = nd
    norm_practice_total[pa] = sum(nd.values())

_feeder_cache = {}
def find_direct_moves_from(source_firm, dest_firm):
    key = (source_firm, dest_firm)
    if key in _feeder_cache: return _feeder_cache[key]
    src_norm = _normalize_for_match(source_firm)
    dst_norm = _normalize_for_match(dest_firm)
    total = norm_moves.get(src_norm, {}).get(dst_norm, 0)
    if total == 0 and src_norm and dst_norm:
        for sn in _all_src_norms:
            if src_norm in sn or sn in src_norm:
                for dn, cnt in norm_moves[sn].items():
                    if dst_norm in dn or dn in dst_norm:
                        total += cnt
    _feeder_cache[key] = total
    return total

_prac_dest_cache = {}
def get_practice_dest_score(practice, dest_firm):
    key = (practice, dest_firm)
    if key in _prac_dest_cache: return _prac_dest_cache[key]
    dst_norm = _normalize_for_match(dest_firm)
    total_score = 0
    for pa in practice.split(','):
        pa = pa.strip()
        if not pa or pa == 'nan': continue
        nd = norm_practice_dest.get(pa)
        if not nd: continue
        total_in_practice = norm_practice_total[pa]
        if total_in_practice == 0: continue
        firm_count = nd.get(dst_norm, 0)
        if firm_count == 0:
            for dn, cnt in nd.items():
                if dst_norm in dn or dn in dst_norm:
                    firm_count += cnt
        if firm_count > 0:
            pct = firm_count / total_in_practice
            total_score = max(total_score, pct)
    _prac_dest_cache[key] = total_score
    return total_score

# ── CHAMBERS HELPERS ──
def normalize_firm(name):
    if not name: return None
    n = name.strip()
    if n in RANKINGS: return n
    if n in ALIASES: return ALIASES[n]
    stripped = re.sub(r'\s*(LLP|LLC|PC|PLLC|PA|LP|LTD|P\.C\.|P\.A\.|L\.L\.P\.)\s*$','',n,flags=re.I).strip()
    if stripped in RANKINGS: return stripped
    if stripped in ALIASES: return ALIASES[stripped]
    return None

def get_all_bands(firm_name):
    canonical = normalize_firm(firm_name)
    if not canonical or canonical not in RANKINGS: return {}
    return RANKINGS[canonical]

def get_band(firm_name, practice):
    canonical = normalize_firm(firm_name)
    if not canonical or canonical not in RANKINGS: return None
    pa = practice.split(',')[0].strip()
    if pa in RANKINGS[canonical]: return RANKINGS[canonical][pa]
    pa_lower = pa.lower()
    for key in RANKINGS[canonical]:
        if key.lower() in pa_lower or pa_lower in key.lower():
            return RANKINGS[canonical][key]
    return None

def band_label(band):
    if band is None: return "Not ranked"
    return f"Band {band}"

PRACTICE_MAP_BROAD = {
    'litigation': ['Litigation', 'Litigation Trial Lawyers'],
    'corporate': ['Corporate', 'Corporate/M&A'],
    'real estate': ['Real Estate'],
    'intellectual property': ['Intellectual Property'],
    'ip': ['Intellectual Property'],
    'banking': ['Banking', 'Banking & Finance'],
    'finance': ['Banking', 'Banking & Finance'],
    'labor & employment': ['Labor & Employment'],
    'labor and employment': ['Labor & Employment'],
    'employment': ['Labor & Employment'],
    'health care': ['Health Care', 'Healthcare'],
    'healthcare': ['Health Care', 'Healthcare'],
    'bankruptcy': ['Bankruptcy', 'Bankruptcy/Restructuring'],
    'restructuring': ['Bankruptcy', 'Bankruptcy/Restructuring'],
    'tax': ['Tax'],
    'energy': ['Energy & Natural Resources'],
    'environment': ['Environment'],
    'antitrust': ['Antitrust'],
    'privacy': ['Privacy & Data Security'],
    'data security': ['Privacy & Data Security'],
    'securities': ['Securities Litigation', 'Securities Regulation'],
    'insurance': ['Insurance'],
    'government': ['Government Contracts'],
    'government contracts': ['Government Contracts'],
    'immigration': ['Immigration'],
    'life sciences': ['Life Sciences'],
    'private equity': ['Private Equity'],
    'capital markets': ['Capital Markets'],
    'project finance': ['Projects'],
    'food': ['Food & Beverages'],
    'sports': ['Sports Law'],
    'cannabis': ['Cannabis Law'],
    'construction': ['Construction'],
    'franchising': ['Franchising'],
    'appellate': ['Appellate Law'],
    'international trade': ['International Trade'],
    'international arbitration': ['International Arbitration'],
    'erisa': ['ERISA Litigation'],
    'product liability': ['Product Liability'],
    'hedge funds': ['Hedge Funds'],
    'investment funds': ['Investment Funds'],
    'startups': ['Startups & Emerging Companies'],
    'emerging companies': ['Startups & Emerging Companies'],
    'venture capital': ['Startups & Emerging Companies'],
    'transportation': ['Transportation'],
    'public finance': ['Public Finance'],
    'native american': ['Native American Law'],
    'trusts & estates': ['Tax Corporate & Finance', 'Tax'],
    'trusts and estates': ['Tax Corporate & Finance', 'Tax'],
    'estate planning': ['Tax Corporate & Finance', 'Tax'],
    'entertainment': ['Sports Law', 'Advertising'],
    'media': ['Advertising'],
    'data privacy': ['Privacy & Data Security'],
    'cybersecurity': ['Privacy & Data Security'],
    'fda': ['Life Sciences', 'Food & Beverages Regulatory & Litigation'],
    'telecommunications': ['International Trade'],
    'environmental': ['Environment'],
}

BIO_KEYWORD_TO_CHAMBERS = {
    'm&a': ['Corporate/M&A', 'Corporate'],
    'mergers and acquisitions': ['Corporate/M&A', 'Corporate'],
    'mergers': ['Corporate/M&A', 'Corporate'],
    'acquisitions': ['Corporate/M&A', 'Corporate'],
    'private equity': ['Private Equity', 'Corporate/M&A'],
    'buyout': ['Private Equity'],
    'leveraged buyout': ['Private Equity'],
    'fund formation': ['Private Equity', 'Investment Funds', 'Hedge Funds'],
    'investment fund': ['Investment Funds', 'Hedge Funds', 'Registered Funds'],
    'hedge fund': ['Hedge Funds'],
    'venture capital': ['Startups & Emerging Companies', 'Corporate/M&A'],
    'emerging companies': ['Startups & Emerging Companies'],
    'startup': ['Startups & Emerging Companies'],
    'capital markets': ['Capital Markets'],
    'securities offering': ['Capital Markets', 'Securities Regulation'],
    'debt and equity': ['Capital Markets', 'Banking & Finance'],
    'ipo': ['Capital Markets'],
    'corporate governance': ['Corporate/M&A', 'Corporate'],
    'compliance': ['Corporate Crime & Investigations', 'Financial Services Regulation'],
    'executive compensation': ['Employee Benefits'],
    'erisa': ['ERISA Litigation'],
    'derivatives': ['Derivatives'],
    'fintech': ['Financial Services Regulation'],
    'financial services': ['Financial Services Regulation', 'Banking & Finance'],
    'banking regulation': ['Financial Services Regulation'],
    'securities litigation': ['Securities Litigation'],
    'securities class action': ['Securities Litigation'],
    'shareholder': ['Securities Litigation', 'Corporate/M&A'],
    'product liability': ['Product Liability'],
    'mass tort': ['Product Liability'],
    'products liability': ['Product Liability'],
    'class action': ['Litigation Trial Lawyers', 'Litigation', 'Product Liability'],
    'white collar': ['Corporate Crime & Investigations', 'FCPA'],
    'investigation': ['Corporate Crime & Investigations', 'FCPA'],
    'fcpa': ['FCPA', 'Corporate Crime & Investigations'],
    'antitrust': ['Antitrust'],
    'patent': ['Intellectual Property'],
    'trademark': ['Intellectual Property'],
    'copyright': ['Intellectual Property'],
    'trade secret': ['Intellectual Property'],
    'international arbitration': ['International Arbitration'],
    'arbitration': ['International Arbitration'],
    'appellate': ['Appellate Law'],
    'e-discovery': ['E-Discovery'],
    'false claims': ['False Claims Act'],
    'qui tam': ['False Claims Act'],
    'insurance': ['Insurance'],
    'environmental': ['Environment'],
    'privacy': ['Privacy & Data Security'],
    'data security': ['Privacy & Data Security'],
    'data breach': ['Privacy & Data Security'],
    'cybersecurity': ['Privacy & Data Security'],
    'commercial litigation': ['Litigation Trial Lawyers', 'Litigation'],
    'commercial disputes': ['Litigation Trial Lawyers', 'Litigation'],
    'complex commercial': ['Litigation Trial Lawyers', 'Litigation'],
    'complex litigation': ['Litigation Trial Lawyers', 'Litigation'],
    'securities fraud': ['Securities Litigation'],
    'financial litigation': ['Securities Litigation', 'Financial Services Regulation'],
    'financial regulatory': ['Financial Services Regulation'],
    'government enforcement': ['Corporate Crime & Investigations', 'FCPA'],
    'regulatory enforcement': ['Corporate Crime & Investigations', 'Financial Services Regulation'],
    'doj': ['Corporate Crime & Investigations', 'FCPA'],
    'sec enforcement': ['Securities Litigation', 'Securities Regulation'],
    'labor and employment': ['Labor & Employment'],
    'labor & employment': ['Labor & Employment'],
    'employment litigation': ['Labor & Employment'],
    'employment discrimination': ['Labor & Employment'],
    'wrongful termination': ['Labor & Employment'],
    'wage and hour': ['Labor & Employment'],
    'nlrb': ['Labor & Employment'],
    'osha': ['Occupational Safety and Health'],
    'occupational safety': ['Occupational Safety and Health'],
    'media': ['First Amendment Litigation'],
    'first amendment': ['First Amendment Litigation'],
    'defamation': ['First Amendment Litigation'],
    'construction litigation': ['Construction'],
    'construction dispute': ['Construction'],
    'construction defect': ['Construction'],
    'insurance coverage': ['Insurance Dispute Resolution: Policyholder', 'Insurance'],
    'insurance defense': ['Insurance Dispute Resolution: Insurer', 'Insurance'],
    'policyholder': ['Insurance Dispute Resolution: Policyholder'],
    'reinsurance': ['Insurance Dispute Resolution: Insurer'],
    'medical malpractice': ['Healthcare', 'Product Liability'],
    'toxic tort': ['Environment', 'Product Liability'],
    'superfund': ['Environment'],
    'clean air': ['Environment'],
    'clean water': ['Environment'],
    'chapter 11': ['Bankruptcy/Restructuring'],
    'chapter 7': ['Bankruptcy/Restructuring'],
    'distressed debt': ['Bankruptcy/Restructuring', 'Private Credit'],
    'distressed': ['Bankruptcy/Restructuring'],
    'workout': ['Bankruptcy/Restructuring'],
    'creditors rights': ['Bankruptcy/Restructuring'],
    'debtor in possession': ['Bankruptcy/Restructuring'],
    'special situations': ['Bankruptcy/Restructuring', 'Private Credit'],
    'real estate': ['Real Estate', 'REITs'],
    'reit': ['REITs', 'Real Estate'],
    'construction': ['Construction'],
    'energy': ['Energy & Natural Resources', 'Oil & Gas'],
    'oil and gas': ['Oil & Gas', 'Energy & Natural Resources'],
    'oil & gas': ['Oil & Gas', 'Energy & Natural Resources'],
    'offshore': ['Offshore Energy'],
    'mining': ['Mining & Metals'],
    'transportation': ['Transportation'],
    'shipping': ['Transportation'],
    'maritime': ['Transportation'],
    'aviation': ['Transportation'],
    'healthcare': ['Healthcare', 'Health Care'],
    'health care': ['Healthcare', 'Health Care'],
    'pharmaceutical': ['Life Sciences'],
    'life science': ['Life Sciences'],
    'biotech': ['Life Sciences'],
    'food': ['Food & Beverages'],
    'beverage': ['Food & Beverages'],
    'cannabis': ['Cannabis Law'],
    'gaming': ['Gaming & Licensing'],
    'sports': ['Sports Law'],
    'entertainment': ['Leisure & Hospitality'],
    'hospitality': ['Leisure & Hospitality'],
    'hotel': ['Leisure & Hospitality', 'Real Estate'],
    'franchise': ['Franchising'],
    'government contract': ['Government Contracts'],
    'procurement': ['Government Contracts'],
    'immigration': ['Immigration'],
    'international trade': ['International Trade'],
    'trade compliance': ['International Trade'],
    'sanctions': ['International Trade'],
    'tax': ['Tax'],
    'bankruptcy': ['Bankruptcy/Restructuring'],
    'restructuring': ['Bankruptcy/Restructuring'],
    'insolvency': ['Bankruptcy/Restructuring'],
    'creditor': ['Bankruptcy/Restructuring'],
    'debtor': ['Bankruptcy/Restructuring'],
    'public finance': ['Public Finance'],
    'municipal': ['Public Finance'],
    'project finance': ['Projects'],
    'infrastructure': ['Projects'],
    'retail': ['Retail'],
    'native american': ['Native American Law'],
    'tribal': ['Native American Law'],
}

def _get_bio_chambers_keys(bio_hook, full_bio=''):
    text = ((bio_hook or '') + ' ' + (full_bio or '')).lower()
    if not text.strip(): return None
    matched = set()
    for keyword, chambers_cats in BIO_KEYWORD_TO_CHAMBERS.items():
        if keyword in text:
            matched.update(chambers_cats)
    return list(matched) if matched else None

def _firm_breadth_dampener(firm_bands):
    n = len(firm_bands)
    if n >= 30: return 0.70
    if n >= 20: return 0.85
    return 1.0

BROAD_CATS = {'Litigation', 'Litigation Trial Lawyers', 'Corporate', 'Corporate/M&A'}

def chambers_practice_score(partner_practice, firm_name, bio_hook='', full_bio=''):
    if not partner_practice: return 0
    areas = [p.strip() for p in partner_practice.split(',')]
    firm_bands = get_all_bands(firm_name)
    if not firm_bands: return 0
    bio_keys = _get_bio_chambers_keys(bio_hook, full_bio=full_bio)
    dampener = _firm_breadth_dampener(firm_bands)
    best_score = 0
    for area in areas:
        area_lower = area.strip().lower()
        broad_ranked = False
        chambers_keys = PRACTICE_MAP_BROAD.get(area_lower, [])
        for ck in chambers_keys:
            if ck in firm_bands and firm_bands[ck] is not None:
                broad_ranked = True
                break
        if not broad_ranked:
            for fk, fv in firm_bands.items():
                if fv is not None and (area_lower in fk.lower() or fk.lower() in area_lower):
                    broad_ranked = True
                    break
        if not broad_ranked: continue
        base_score = 20
        bio_bonus = 0
        if bio_keys:
            specific_keys = [k for k in bio_keys if k not in BROAD_CATS]
            for ck in specific_keys:
                if ck in firm_bands and firm_bands[ck] is not None:
                    bio_bonus = 10
                    break
        score = int((base_score + bio_bonus) * dampener)
        best_score = max(best_score, score)
    if bio_keys:
        specific_bio_keys = [k for k in bio_keys if k not in BROAD_CATS]
        for ck in specific_bio_keys:
            if ck in firm_bands and firm_bands[ck] is not None:
                bio_promoted_score = int(20 * dampener)
                best_score = max(best_score, bio_promoted_score)
                break
    return best_score

# ── GEOGRAPHY ──
firm_cities = {}
for entry in firms_inv:
    firm_cities[entry['firm']] = [c.strip() for c in entry['cities']]
for sf in supplemental_firms:
    firm_cities[sf['name']] = sf['cities']

def normalize_city(city):
    if not city: return ''
    c = city.strip()
    aliases = {
        'Washington, D.C.': 'Washington, DC', 'Washington DC': 'Washington, DC',
        'DC': 'Washington, DC', 'NYC': 'New York', 'New York City': 'New York',
        'New York, NY': 'New York', 'LA': 'Los Angeles', 'SF': 'San Francisco',
        'Philly': 'Philadelphia', 'Phila': 'Philadelphia',
        'Washington': 'Washington, DC',
        # Metro area mappings
        'Roseland': 'New York', 'Florham Park': 'New York', 'White Plains': 'New York', 'Princeton': 'New York',
        'Fort Lauderdale': 'Miami', 'Coral Gables': 'Miami', 'West Palm Beach': 'Miami', 'Boca Raton': 'Miami',
        'Bethesda': 'Washington, DC', 'Arlington': 'Washington, DC', 'Tysons': 'Washington, DC', 'McLean': 'Washington, DC',
        'Palo Alto': 'San Francisco', 'Menlo Park': 'San Francisco', 'San Jose': 'San Francisco',
        'Santa Monica': 'Los Angeles', 'Beverly Hills': 'Los Angeles', 'Irvine': 'Los Angeles',
        'Costa Mesa': 'Los Angeles', 'Newport Beach': 'Los Angeles', 'Pasadena': 'Los Angeles', 'Glendale': 'Los Angeles',
        'Berwyn': 'Philadelphia', 'Wilmington': 'Philadelphia',
        'Fort Worth': 'Dallas', 'Plano': 'Dallas', 'Frisco': 'Dallas',
        'Rosemont': 'Chicago', 'Broomfield': 'Denver', 'League City': 'Houston',
    }
    return aliases.get(c, c)

def city_match(partner_city, firm_city_list):
    pc = normalize_city(partner_city)
    if not pc: return False
    nfc = [normalize_city(c) for c in firm_city_list]
    if pc in nfc: return True
    pc_lower = pc.lower()
    return any(pc_lower in fc.lower() or fc.lower() in pc_lower for fc in nfc)

# ── PPP / BOOK ──
def get_source_ppp(partner_firm):
    if not partner_firm: return None
    if partner_firm in feeder_scores:
        return feeder_scores[partner_firm].get('ppp')
    pf_lower = partner_firm.lower()
    for key in feeder_scores:
        if pf_lower in key.lower() or key.lower() in pf_lower:
            return feeder_scores[key].get('ppp')
    return None

def get_target_ppp(firm_name):
    if firm_name in firm_ppp_data: return firm_ppp_data[firm_name]
    for k, v in feeder_scores.items():
        if _normalize_for_match(firm_name) in _normalize_for_match(k) or _normalize_for_match(k) in _normalize_for_match(firm_name):
            return v.get('ppp')
    return None

def estimate_book(source_ppp, book_est=None):
    if book_est and book_est > 0:
        return book_est * 1000
    if source_ppp:
        return source_ppp * 0.7
    return 0

_FIRM_BOOK_MIN = {}
for _fi in firms_inv:
    _bs = _fi.get('book_size')
    if _bs:
        try:
            _FIRM_BOOK_MIN[_fi['firm']] = float(_bs) * 1_000_000
        except (ValueError, TypeError):
            pass

_NONSIGNED_BOOK_MIN = {
    'Kirkland & Ellis LLP': 5_000_000, 'Kirkland & Ellis': 5_000_000,
    'Skadden, Arps, Slate, Meagher & Flom LLP': 5_000_000, 'Skadden': 5_000_000,
    'Ropes & Gray LLP': 5_000_000, 'Ropes & Gray': 5_000_000,
    'Willkie Farr & Gallagher LLP': 5_000_000, 'Willkie Farr': 5_000_000,
    'King & Spalding LLP': 5_000_000, 'King & Spalding': 5_000_000,
    'Akin, Gump, Strauss, Hauer & Feld, LLP': 3_000_000, 'Akin Gump': 3_000_000,
    'Proskauer Rose LLP': 3_000_000, 'Proskauer': 3_000_000,
    'Alston & Bird LLP': 3_000_000, 'Alston & Bird': 3_000_000,
    'White & Case LLP': 5_000_000, 'White & Case': 5_000_000,
    'Orrick': 3_000_000,
    "O'Melveny & Myers LLP": 3_000_000, "O'Melveny": 3_000_000,
    'Morrison & Foerster LLP': 3_000_000, 'Morrison & Foerster': 3_000_000,
    'Fried Frank': 5_000_000,
    'Cravath': 10_000_000, 'Paul Weiss': 8_000_000, 'Wilson Sonsini': 3_000_000,
    'Weil': 5_000_000,
}
_FIRM_BOOK_MIN.update(_NONSIGNED_BOOK_MIN)

def get_firm_book_floor(firm_name):
    if firm_name in _FIRM_BOOK_MIN: return _FIRM_BOOK_MIN[firm_name]
    fn_lower = _normalize_for_match(firm_name)
    for k, v in _FIRM_BOOK_MIN.items():
        if _normalize_for_match(k) == fn_lower: return v
    return 0

# ── SIMILAR-FIRM INDEX ──
print("Building similar-firm index...")
_firm_profiles = {}
for fn in [tf['name'] for tf in target_firms] + [sf['name'] for sf in supplemental_firms]:
    ppp = get_target_ppp(fn)
    bands = get_all_bands(fn)
    practices = set(bands.keys()) if bands else set()
    _firm_profiles[fn] = {'ppp': ppp, 'practices': practices}

_similar_firms = {}
_profile_list = list(_firm_profiles.items())
for i, (fn1, p1) in enumerate(_profile_list):
    sims = []
    for j, (fn2, p2) in enumerate(_profile_list):
        if i == j: continue
        if p1['ppp'] and p2['ppp'] and p1['ppp'] > 0 and p2['ppp'] > 0:
            ratio = p2['ppp'] / p1['ppp']
            if ratio < 0.70 or ratio > 1.30: continue
        elif p1['ppp'] or p2['ppp']:
            continue
        shared = p1['practices'] & p2['practices']
        if len(shared) >= 2:
            sims.append(fn2)
    _similar_firms[fn1] = sims

_sim_feeder_cache = {}
def find_similar_feeder_moves(source_firm, dest_firm):
    key = (source_firm, dest_firm)
    if key in _sim_feeder_cache: return _sim_feeder_cache[key]
    similar = _similar_firms.get(dest_firm, [])
    total = 0
    for sim_firm in similar:
        moves = find_direct_moves_from(source_firm, sim_firm)
        total += moves
    result = total * 0.5
    _sim_feeder_cache[key] = result
    return result

# ── MAIN SCORING FUNCTION ──
def match_score(partner, firm_name):
    partner_city = partner.get('city', '')
    partner_firm = partner.get('firm', '')
    partner_practice = partner.get('practice', '')

    # Same-firm exclusion
    if partner_firm and firm_name:
        pf = _normalize_for_match(partner_firm)
        fn = _normalize_for_match(firm_name)
        if pf and fn:
            if pf == fn: return -999
            if len(pf) >= 4 and len(fn) >= 4 and (pf in fn or fn in pf): return -999

    _src_ppp = get_source_ppp(partner_firm)

    # Book-size ceiling (50%)
    _book_floor = get_firm_book_floor(firm_name)
    _est_book = 0
    if _book_floor > 0:
        _est_book = estimate_book(_src_ppp, partner.get('book_est'))
        if _est_book > 0 and _est_book < _book_floor * 0.50:
            return -999

    # Geography hard filter
    fc = firm_cities.get(firm_name)
    if not fc: return -999
    if not city_match(partner_city, fc): return -999

    # Factor 1: Direct feeder
    direct = find_direct_moves_from(partner_firm, firm_name)
    sim = find_similar_feeder_moves(partner_firm, firm_name)
    effective = direct + sim
    if effective >= 15: feeder_pts = 35
    elif effective >= 10: feeder_pts = 30
    elif effective >= 5: feeder_pts = 25
    elif effective >= 3: feeder_pts = 20
    elif effective >= 2: feeder_pts = 15
    elif effective >= 1: feeder_pts = 10
    else: feeder_pts = 0

    # Factor 2: Practice destination
    pct = get_practice_dest_score(partner_practice, firm_name)
    if pct >= 0.05: practice_pts = 20
    elif pct >= 0.03: practice_pts = 15
    elif pct >= 0.02: practice_pts = 12
    elif pct >= 0.01: practice_pts = 8
    elif pct > 0: practice_pts = 4
    else: practice_pts = 0

    # Factor 3: Chambers
    chambers_pts = chambers_practice_score(partner_practice, firm_name,
                                           bio_hook=partner.get('bio_hook', ''),
                                           full_bio=partner.get('full_bio', ''))

    # Factor 4: Book-size realism penalty
    book_penalty = 0
    if _book_floor > 0 and _est_book > 0:
        ratio = _est_book / _book_floor
        if ratio >= 1.0: book_penalty = 0
        elif ratio >= 0.75: book_penalty = -5
        elif ratio >= 0.50: book_penalty = -15

    total = feeder_pts + practice_pts + chambers_pts + book_penalty
    return total

# ── RUN MATCHING ──
# ONLY match to target firms (COLD_CALL_FIRMS) — supplemental firms are for feeder training only
all_firm_names = [tf['name'] for tf in target_firms]
results = []

for i, p in enumerate(new_partners):
    scores = []
    for fn in all_firm_names:
        s = match_score(p, fn)
        if s > -999:
            scores.append((fn, s))
    scores.sort(key=lambda x: -x[1])

    target = scores[0][0] if len(scores) > 0 else ''
    alt1 = scores[1][0] if len(scores) > 1 else ''
    alt2 = scores[2][0] if len(scores) > 2 else ''
    alt3 = scores[3][0] if len(scores) > 3 else ''
    top_score = scores[0][1] if scores else 0

    # Build record in same schema as dashboard_data.json
    practice = p.get('practice', '')
    rec = {
        'name': p['name'],
        'first': p['first'],
        'firm': p['firm'],
        'city': p['city'],
        'practice': practice,
        'target': target,
        'alt1': alt1,
        'alt2': alt2,
        'alt3': alt3,
        'score': round(top_score, 1),
        'stage': '',
        'linkedin': p.get('linkedin', ''),
        'fp': p.get('fp', ''),
        'book_est': 0,
        'message': '',
        'msg_alt1': '',
        'msg_alt2': '',
        'last_contact': '',
        'last_note': '',
        'bio_hook': p.get('bio_hook', ''),
        'candidate_band': band_label(get_band(p['firm'], practice)),
        'candidate_firm_canonical': normalize_firm(p['firm']) or p['firm'],
        'target_band': band_label(get_band(target, practice)) if target else '',
        'alt1_band': band_label(get_band(alt1, practice)) if alt1 else '',
        'alt2_band': band_label(get_band(alt2, practice)) if alt2 else '',
        'alt3_band': band_label(get_band(alt3, practice)) if alt3 else '',
        'chambers_adj_target': chambers_practice_score(practice, target, p.get('bio_hook',''), p.get('full_bio','')) if target else 0,
        'chambers_adj_alt1': chambers_practice_score(practice, alt1, p.get('bio_hook',''), p.get('full_bio','')) if alt1 else 0,
        'chambers_adj_alt2': chambers_practice_score(practice, alt2, p.get('bio_hook',''), p.get('full_bio','')) if alt2 else 0,
        'chambers_adj_alt3': chambers_practice_score(practice, alt3, p.get('bio_hook',''), p.get('full_bio','')) if alt3 else 0,
        'target_chambers_label': '',
        'alt1_chambers_label': '',
        'alt2_chambers_label': '',
        'alt3_chambers_label': '',
        'candidate_chambers_label': '',
        'status': '',
        'target_signed': target in SIGNED_NAMES if target else False,
        'alt1_signed': alt1 in SIGNED_NAMES if alt1 else False,
        'alt2_signed': alt2 in SIGNED_NAMES if alt2 else False,
        'alt3_signed': alt3 in SIGNED_NAMES if alt3 else False,
        'is_new': True,  # Flag for sorting priority
        'added_date': '2026-04-02',
    }
    results.append(rec)

    if (i+1) % 50 == 0:
        print(f"  Matched {i+1}/{len(new_partners)}...")

print(f"\nMatched all {len(results)} new partners")

# Stats
matched = [r for r in results if r['target']]
unmatched = [r for r in results if not r['target']]
print(f"  With matches: {len(matched)}")
print(f"  No match (no firm in their city): {len(unmatched)}")
if unmatched:
    print(f"  Unmatched cities: {Counter(r['city'] for r in unmatched).most_common(10)}")

with open(f'{BASE}/new_partners_matched.json', 'w') as f:
    json.dump(results, f, indent=2)
print(f"Saved new_partners_matched.json")
