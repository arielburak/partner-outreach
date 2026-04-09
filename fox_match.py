"""
Fox Rothschild Matching — uses the SAME 5-factor scoring model as partner_match.py
but scores ALL 694 LinkedIn partners against Fox Rothschild specifically.

Criteria (from SKILL.md):
  1. Geography: partner's city must be in Fox's office list (HARD)
  2. Direct feeder: historical moves from partner's firm → Fox
  3. Practice destination: among movers in partner's practice, what % went to Fox?
  4. Chambers in practice: does Fox have Chambers prestige in partner's practice?
  5. PPP step direction: is the PPP move natural?
  6. Same-firm exclusion: can't be at Fox already
  7. PRESTIGE FLOOR: if source PPP > $3M, target must have PPP >= 50% of source

Only partners who PASS the hard filters AND score above a minimum threshold are included.
"""

import json, re, os
import pandas as pd
from collections import Counter, defaultdict

# ─── LOAD DATA ─────────────────────────────────────────────
with open('/sessions/dreamy-ecstatic-heisenberg/firms_inventory.json') as f:
    firms_inv = json.load(f)
with open('/sessions/dreamy-ecstatic-heisenberg/chambers_rankings.json') as f:
    ch_data = json.load(f)
with open('/sessions/dreamy-ecstatic-heisenberg/firm_ppp.json') as f:
    firm_ppp_data = json.load(f)
with open('/sessions/dreamy-ecstatic-heisenberg/feeder_scores.json') as f:
    feeder_scores = json.load(f)
with open('/sessions/dreamy-ecstatic-heisenberg/dashboard_data.json') as f:
    partners = json.load(f)

RANKINGS = ch_data['rankings']
ALIASES = ch_data['aliases']

# Fox Rothschild office cities (from firms_inventory.json)
fox_entry = next((e for e in firms_inv if 'fox' in e['firm'].lower()), None)
FOX_CITIES = [c.strip() for c in fox_entry['cities']] if fox_entry else []
print(f"Fox Rothschild offices: {FOX_CITIES}")

# Fox PPP
FOX_PPP = firm_ppp_data.get('Fox Rothschild', firm_ppp_data.get('Fox Rothschild LLP', 1100000))
print(f"Fox PPP: ${FOX_PPP:,.0f}")

# ─── BUILD MOVE MATRIX (same as partner_match.py) ─────────
direct_moves = defaultdict(Counter)
practice_dest = defaultdict(Counter)

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

def ingest(df, label):
    count = 0
    for _, row in df.iterrows():
        firms = parse_moves(row.get('Lateral Moves'))
        practice = str(row.get('Practice Areas', ''))
        for i in range(len(firms) - 1):
            src, dst = firms[i], firms[i+1]
            direct_moves[src][dst] += 1
            count += 1
            if practice and practice != 'nan':
                for pa in practice.split(','):
                    pa = pa.strip()
                    if pa:
                        practice_dest[pa][dst] += 1
    print(f"  [{label}] {count} moves")
    return count

print("Building move matrix...")
total = 0
try:
    df = pd.read_excel('/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/TO TRAIN MODEL ON ATTRITION.xlsx')
    total += ingest(df, 'Attrition')
except FileNotFoundError:
    pass

import glob
for af in glob.glob('/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/Attorneys*.xlsx'):
    try:
        df = pd.read_excel(af)
        total += ingest(df, f'Attorneys')
    except Exception:
        pass

try:
    df = pd.read_excel('/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/LINKEDIN CONNECTED PARTNERS.xlsx')
    if 'Lateral Moves' in df.columns:
        total += ingest(df, 'LinkedIn')
except FileNotFoundError:
    pass

print(f"  TOTAL: {total} moves parsed")

# ─── NORMALIZE HELPERS ─────────────────────────────────────
_norm_cache = {}
def _norm(name):
    if name in _norm_cache: return _norm_cache[name]
    if not name:
        _norm_cache[name] = ''
        return ''
    n = re.sub(r'\s*(LLP|LLC|PC|PLLC|PA|LP|LTD|P\.C\.|P\.A\.|L\.L\.P\.)\s*$', '', name.strip(), flags=re.I)
    n = re.sub(r',\s*$', '', n).strip().lower()
    _norm_cache[name] = n
    return n

# Pre-normalize move matrix
norm_moves = defaultdict(Counter)
for raw_src, dests in direct_moves.items():
    sn = _norm(raw_src)
    for raw_dst, cnt in dests.items():
        dn = _norm(raw_dst)
        norm_moves[sn][dn] += cnt

norm_practice_dest = {}
norm_practice_total = {}
for pa, dest_counts in practice_dest.items():
    nd = Counter()
    for raw_dst, cnt in dest_counts.items():
        nd[_norm(raw_dst)] += cnt
    norm_practice_dest[pa] = nd
    norm_practice_total[pa] = sum(nd.values())

fox_norm = _norm('Fox Rothschild')

def normalize_city(city):
    if not city: return ''
    c = city.strip()
    aliases = {
        'Washington, D.C.': 'Washington, DC', 'Washington DC': 'Washington, DC',
        'DC': 'Washington, DC', 'NYC': 'New York', 'New York City': 'New York',
        'New York, NY': 'New York', 'LA': 'Los Angeles', 'SF': 'San Francisco',
        'Philly': 'Philadelphia', 'Phila': 'Philadelphia',
    }
    return aliases.get(c, c)

def city_match(partner_city):
    pc = normalize_city(partner_city)
    if not pc: return False
    nfc = [normalize_city(c) for c in FOX_CITIES]
    if pc in nfc: return True
    pc_lower = pc.lower()
    return any(pc_lower in fc.lower() or fc.lower() in pc_lower for fc in nfc)

# ─── CHAMBERS ──────────────────────────────────────────────
PRACTICE_MAP_BROAD = {
    'litigation': ['Litigation', 'Litigation Trial Lawyers'],
    'corporate': ['Corporate', 'Corporate/M&A'],
    'real estate': ['Real Estate'],
    'intellectual property': ['Intellectual Property'],
    'labor & employment': ['Labor & Employment'],
    'labor and employment': ['Labor & Employment'],
    'employment': ['Labor & Employment'],
    'bankruptcy': ['Bankruptcy', 'Bankruptcy/Restructuring'],
    'restructuring': ['Bankruptcy', 'Bankruptcy/Restructuring'],
    'tax': ['Tax'],
    'banking': ['Banking', 'Banking & Finance'],
    'finance': ['Banking', 'Banking & Finance'],
    'health care': ['Health Care', 'Healthcare'],
    'healthcare': ['Health Care', 'Healthcare'],
    'energy': ['Energy & Natural Resources'],
    'environment': ['Environment'],
    'antitrust': ['Antitrust'],
    'insurance': ['Insurance'],
    'trusts & estates': ['Private Wealth Law', 'Tax'],
    'trusts and estates': ['Private Wealth Law', 'Tax'],
}

def normalize_firm(name):
    if not name: return None
    n = name.strip()
    if n in RANKINGS: return n
    if n in ALIASES: return ALIASES[n]
    stripped = re.sub(r'\s*(LLP|LLC|PC|PLLC|PA|LP|LTD|P\.C\.|P\.A\.)\s*$', '', n, flags=re.I).strip()
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

fox_bands = get_all_bands('Fox Rothschild')
print(f"Fox Chambers rankings: {fox_bands}")

# ─── SCORING (same 5 factors as partner_match.py) ─────────

def score_for_fox(p):
    """Score a partner for Fox Rothschild using the 5-factor model."""
    partner_city = p.get('city', '')
    partner_firm = p.get('firm', '')
    partner_practice = p.get('practice', '')

    # 0. Same-firm exclusion
    if partner_firm:
        pf = _norm(partner_firm)
        if pf == fox_norm or 'fox rothschild' in pf or fox_norm in pf:
            return -999, 'same-firm'

    # 0b. PRESTIGE FLOOR: if source PPP > $3M, target must have PPP >= 50% of source
    src_ppp = None
    if partner_firm in feeder_scores:
        src_ppp = feeder_scores[partner_firm].get('ppp')
    if not src_ppp:
        pf_lower = partner_firm.lower()
        for key in feeder_scores:
            if pf_lower in key.lower() or key.lower() in pf_lower:
                src_ppp = feeder_scores[key].get('ppp')
                break
    if not src_ppp:
        src_ppp = firm_ppp_data.get(partner_firm, 0)
        if not src_ppp:
            for k, v in firm_ppp_data.items():
                if _norm(k) == _norm(partner_firm):
                    src_ppp = v
                    break

    if src_ppp and src_ppp > 3_000_000 and FOX_PPP < src_ppp * 0.50:
        return -999, f'prestige-floor (src ${src_ppp/1e6:.1f}M >> Fox ${FOX_PPP/1e6:.1f}M)'

    # 1. GEOGRAPHY (hard filter)
    if not city_match(partner_city):
        return -999, 'geography'

    # 2. DIRECT FEEDER (0-25 pts)
    src_norm = _norm(partner_firm)
    direct = norm_moves.get(src_norm, {}).get(fox_norm, 0)
    if direct == 0 and src_norm:
        for sn in norm_moves:
            if src_norm in sn or sn in src_norm:
                for dn, cnt in norm_moves[sn].items():
                    if fox_norm in dn or dn in fox_norm:
                        direct += cnt
    if direct >= 5:   feeder_pts = 25
    elif direct >= 3: feeder_pts = 20
    elif direct >= 2: feeder_pts = 15
    elif direct >= 1: feeder_pts = 10
    else:             feeder_pts = 0

    # 3. PRACTICE DESTINATION (0-20 pts)
    prac_pct = 0
    for pa in partner_practice.split(','):
        pa = pa.strip()
        if not pa: continue
        nd = norm_practice_dest.get(pa)
        if not nd: continue
        total_in = norm_practice_total[pa]
        if total_in == 0: continue
        fc = nd.get(fox_norm, 0)
        if fc == 0:
            for dn, cnt in nd.items():
                if fox_norm in dn or dn in fox_norm:
                    fc += cnt
        if fc > 0:
            prac_pct = max(prac_pct, fc / total_in)
    if prac_pct >= 0.05:   prac_pts = 20
    elif prac_pct >= 0.03: prac_pts = 15
    elif prac_pct >= 0.02: prac_pts = 12
    elif prac_pct >= 0.01: prac_pts = 8
    elif prac_pct > 0:     prac_pts = 4
    else:                  prac_pts = 0

    # 4. CHAMBERS IN PRACTICE (0-30 pts)
    chambers_pts = 0
    for area in partner_practice.split(','):
        area_lower = area.strip().lower()
        chambers_keys = PRACTICE_MAP_BROAD.get(area_lower, [])
        best_band = None
        for ck in chambers_keys:
            if ck in fox_bands and fox_bands[ck] is not None:
                if best_band is None or fox_bands[ck] < best_band:
                    best_band = fox_bands[ck]
        if best_band is None:
            for fk, fv in fox_bands.items():
                if fv is not None and (area_lower in fk.lower() or fk.lower() in area_lower):
                    if best_band is None or fv < best_band:
                        best_band = fv
        if best_band is not None:
            if best_band == 1:   score = 30
            elif best_band == 2: score = 25
            elif best_band == 3: score = 20
            elif best_band == 4: score = 15
            else:                score = 10
            chambers_pts = max(chambers_pts, score)

    # 5. PPP ALIGNMENT (-5 to +10 pts)
    ppp_pts = 0
    if src_ppp and src_ppp > 0:
        ratio = FOX_PPP / src_ppp
        diff = abs(ratio - 1.0)
        if diff <= 0.15:   ppp_pts = 10
        elif diff <= 0.30: ppp_pts = 8
        elif diff <= 0.50: ppp_pts = 5
        elif diff <= 0.75: ppp_pts = 0
        else:              ppp_pts = -5

    total = feeder_pts + prac_pts + chambers_pts + ppp_pts
    breakdown = f"feeder={feeder_pts} prac={prac_pts} chambers={chambers_pts} ppp={ppp_pts}"
    return total, breakdown


# ─── RUN MATCHING ──────────────────────────────────────────
print(f"\nScoring {len(partners)} partners against Fox Rothschild...")

results = []
filtered = {'same-firm': 0, 'prestige-floor': 0, 'geography': 0, 'low-score': 0}

MIN_SCORE = 10  # Minimum score to include — must have SOME signal

for p in partners:
    score, detail = score_for_fox(p)
    if score == -999:
        reason = detail.split(' ')[0] if ' ' in detail else detail
        filtered[reason] = filtered.get(reason, 0) + 1
        continue
    if score < MIN_SCORE:
        filtered['low-score'] += 1
        continue

    results.append({
        'name': p['name'],
        'first': p.get('first', p['name'].split()[0]),
        'firm': p.get('firm', ''),
        'practice': p.get('practice', ''),
        'target': 'Fox Rothschild',
        'dept': p.get('practice', '').split(',')[0].strip(),
        'score': score,
        'city': p.get('city', ''),
        'stage': p.get('stage', 'cold'),
        'linkedin': p.get('linkedin', ''),
        'fp': p.get('fp', ''),
        'message': p.get('message', ''),  # Will need Fox-specific messages
        'bio_hook': p.get('bio_hook', ''),
        'book_est': p.get('book_est', 0),
        'ppp': firm_ppp_data.get(p.get('firm', ''), 0),
        'att': feeder_scores.get(p.get('firm', ''), {}).get('direct_fox', 0),
        'n_moves': feeder_scores.get(p.get('firm', ''), {}).get('total_moves', 0),
        '_breakdown': detail,
    })

results.sort(key=lambda x: -x['score'])

print(f"\nResults:")
print(f"  Passed all filters: {len(results)}")
print(f"  Filtered out:")
for reason, count in sorted(filtered.items(), key=lambda x: -x[1]):
    print(f"    {reason}: {count}")

print(f"\nScore distribution:")
scores = [r['score'] for r in results]
for threshold in [50, 40, 30, 20, 10]:
    count = sum(1 for s in scores if s >= threshold)
    print(f"  Score >= {threshold}: {count}")

print(f"\nTop 20 Fox candidates:")
for r in results[:20]:
    print(f"  {r['score']:3.0f}  {r['name']:<30s} {r['firm'][:30]:<30s} {r['city']:<15s} {r['dept']}")

print(f"\nBottom 10:")
for r in results[-10:]:
    print(f"  {r['score']:3.0f}  {r['name']:<30s} {r['firm'][:30]:<30s} {r['city']:<15s} {r['_breakdown']}")

# Source firm distribution
firm_dist = Counter(r['firm'] for r in results)
print(f"\nTop source firms:")
for firm, count in firm_dist.most_common(15):
    ppp = firm_ppp_data.get(firm, 0)
    ppp_str = f"${ppp/1e6:.1f}M" if ppp else "?"
    print(f"  {count:3d}  {firm[:40]:<40s} PPP={ppp_str}")

# City distribution
city_dist = Counter(r['city'] for r in results)
print(f"\nCity distribution:")
for city, count in city_dist.most_common():
    print(f"  {count:3d}  {city}")

# Save
with open('/sessions/dreamy-ecstatic-heisenberg/fox_normalized.json', 'w') as f:
    json.dump(results, f, ensure_ascii=False)
print(f"\nSaved {len(results)} Fox candidates to fox_normalized.json")
