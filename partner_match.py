"""
Partner Matching Engine v3 — Attrition-Driven

Core logic: Partners move to firms that have prestige in their practice area.
The proof is in the data — 5,000 actual lateral moves tell us who goes where.

A Davis Polk RE partner moves to Goulston because Goulston is Chambers Band 3
in Real Estate. Reed Smith litigators go to Holland & Knight (11 moves in data)
because Holland & Knight is Chambers Litigation Band 2.

NO book estimates — can't reliably estimate portables from public data.

Scoring factors:
  1. Geography: candidate city in firm's office list (hard filter)
  2. Direct feeder: how many partners moved FROM candidate's firm TO this target?
  3. Practice destination: among all movers in candidate's practice, how popular
     is this target firm? (captures practice-level gravity)
  4. Chambers in practice: does the target have Chambers prestige in the
     candidate's specific practice area? Bio hooks narrow sub-practice matching.
  5. Book-size realism: PPP as book proxy vs. firm's stated book minimums
     (hard ceiling + soft penalty, NO directional preference)
  6. Same-firm exclusion
"""

import pandas as pd
import json, re
from collections import Counter, defaultdict

# ──────────────────────── LOAD DATA ────────────────────────

import os

with open('/sessions/dreamy-ecstatic-heisenberg/firms_inventory.json') as f:
    firms_inv = json.load(f)

with open('/sessions/dreamy-ecstatic-heisenberg/target_firms_full.json') as f:
    target_firms = json.load(f)

with open('/sessions/dreamy-ecstatic-heisenberg/chambers_rankings.json') as f:
    ch_data = json.load(f)

with open('/sessions/dreamy-ecstatic-heisenberg/firm_ppp.json') as f:
    firm_ppp_data = json.load(f)

with open('/sessions/dreamy-ecstatic-heisenberg/feeder_scores.json') as f:
    feeder_scores = json.load(f)

with open('/sessions/dreamy-ecstatic-heisenberg/dashboard_data.json') as f:
    partners = json.load(f)

# Load supplemental (non-signed) firms — high-prestige BigLaw targets
_supp_paths = [
    '/sessions/dreamy-ecstatic-heisenberg/supplemental_firms.json',
    '/sessions/dreamy-ecstatic-heisenberg/mnt/outputs/legal-recruiting-model/supplemental_firms.json',
]
supplemental_firms = []
for _sp in _supp_paths:
    if os.path.exists(_sp):
        with open(_sp) as f:
            supplemental_firms = json.load(f)
        print(f"Loaded {len(supplemental_firms)} supplemental firms from {_sp}")
        break

SIGNED_NAMES = {tf['name'] for tf in target_firms}

# ──────────────────────── EXTRACT BIO HOOKS ────────────────────────
# Read bios from LinkedIn file and attach hooks to partner records
# This is used to NARROW Chambers sub-practice matching

print("Extracting bio hooks for sub-practice narrowing...")
_bio_hook_patterns = [
    r'(?:focuses?\s+(?:her|his|their)\s+practice\s+on|focus(?:es|ing)?\s+on)\s+(.+?)(?:\.|,\s*(?:with|including|and\s+has))',
    r'(?:specializ(?:es|ing)\s+in)\s+(.+?)(?:\.|,\s*(?:with|including|and))',
    r'(?:concentrat(?:es|ing)\s+(?:her|his|their)\s+practice\s+(?:in|on))\s+(.+?)(?:\.|,)',
    r'(?:practice\s+(?:is\s+)?(?:focused|centered|concentrated)\s+(?:on|in))\s+(.+?)(?:\.|,)',
    r'(?:represents?\s+clients\s+in)\s+(.+?)(?:\.|,\s*(?:with|including|and))',
    r'(?:advises?\s+(?:clients\s+)?(?:on|in))\s+(.+?)(?:\.|,\s*(?:with|including))',
]

try:
    _linkedin_df = pd.read_excel('/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/LINKEDIN CONNECTED PARTNERS.xlsx')
    _bio_by_name = {}
    for _, row in _linkedin_df.iterrows():
        # Build name from First + Last (no 'Full Name' column)
        first = str(row.get('First Name', '')).strip()
        last = str(row.get('Last Name', '')).strip()
        name = f"{first} {last}" if first and last and first != 'nan' and last != 'nan' else ''
        bio = str(row.get('Full Bio', ''))
        if name and bio and bio != 'nan':
            # Strip quoted text (Chambers quotes, testimonials) BEFORE storing
            bio_clean = re.sub(r'"[^"]*"', ' ', bio)
            bio_clean = re.sub(r'\u201c[^\u201d]*\u201d', ' ', bio_clean)
            bio_clean = re.sub(r'Chambers\s+USA\s+\d{4}', ' ', bio_clean)
            _bio_by_name[name] = bio_clean

    hook_count = 0
    extracted = 0
    for p in partners:
        # Respect stored hooks: if bio_hook key exists, don't re-extract
        if 'bio_hook' in p:
            if p['bio_hook']:
                hook_count += 1
            continue
        # No stored hook — try quick extraction from bio.
        # Only SET bio_hook if we find something; leave it absent otherwise
        # so build_bio_messages.py can try its own (more thorough) extraction.
        bio = _bio_by_name.get(p.get('name', ''), '')
        hook = ''
        for pattern in _bio_hook_patterns:
            m = re.search(pattern, bio, re.I)
            if m:
                hook = m.group(1).strip()[:120]
                break
        extracted += 1
        if hook:
            p['bio_hook'] = hook
            hook_count += 1
        # If no hook found, do NOT set bio_hook — let build_bio_messages handle it
    print(f"  Bio hooks: {hook_count} total ({extracted} newly extracted)")
except FileNotFoundError:
    _bio_by_name = {}
    print("  LinkedIn file not found, skipping bio hook extraction")
    for p in partners:
        if 'bio_hook' not in p:
            p['bio_hook'] = ''

RANKINGS = ch_data['rankings']
ALIASES  = ch_data['aliases']

# ──────────────────────── BUILD MOVE MATRIX FROM ATTRITION DATA ────────────────────────

print("Building move matrix from ALL lateral move data sources...")

# Parse lateral moves: "Firm A -> Firm B (Date) -> Firm C (Date)"
# Build: direct_moves[source][dest] = count
# Build: practice_dest[practice][dest] = count  (where do practice X movers go?)
direct_moves = defaultdict(Counter)      # source_firm → {dest_firm: count}
practice_dest = defaultdict(Counter)     # practice → {dest_firm: count}
dest_total_inbound = Counter()           # dest_firm → total inbound moves

def parse_moves(moves_str):
    """Parse 'Firm A -> Firm B (Date) -> Firm C (Date)' into list of firm names."""
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
    """Parse lateral moves from a dataframe and add to the global move matrix."""
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

# Source 1: Original attrition training data (5,000 records)
import glob
total = 0
attrition_path = '/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/TO TRAIN MODEL ON ATTRITION.xlsx'
try:
    attrition_df = pd.read_excel(attrition_path)
    total += ingest_lateral_moves(attrition_df, 'Attrition training')
except FileNotFoundError:
    print(f"  [Attrition training] Not found, skipping")

# Source 2: New attorneys file (5,000 more records)
attorneys_files = glob.glob('/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/Attorneys*.xlsx')
for af in attorneys_files:
    try:
        attorneys_df = pd.read_excel(af)
        total += ingest_lateral_moves(attorneys_df, f'Attorneys ({len(attorneys_df)})')
    except Exception as e:
        print(f"  [Attorneys] Error: {e}")

# Source 3: LinkedIn connected partners (also has lateral moves)
linkedin_path = '/sessions/dreamy-ecstatic-heisenberg/mnt/uploads/LINKEDIN CONNECTED PARTNERS.xlsx'
try:
    linkedin_df = pd.read_excel(linkedin_path)
    if 'Lateral Moves' in linkedin_df.columns:
        total += ingest_lateral_moves(linkedin_df, 'LinkedIn partners')
except FileNotFoundError:
    print(f"  [LinkedIn partners] Not found, skipping")

print(f"\n  TOTAL: {total} individual moves parsed")
print(f"  Source firms: {len(direct_moves)}")
print(f"  Destination firms: {len(dest_total_inbound)}")

# ──────────────────────── NORMALIZE FIRM NAMES FOR MATCHING ────────────────────────

_norm_cache = {}
def _normalize_for_match(name):
    """Lowercase, strip suffixes, for fuzzy matching between datasets."""
    if name in _norm_cache: return _norm_cache[name]
    if not name:
        _norm_cache[name] = ''
        return ''
    n = name.strip()
    n = re.sub(r'\s*(LLP|LLC|PC|PLLC|PA|LP|LTD|P\.C\.|P\.A\.|L\.L\.P\.)\s*$', '', n, flags=re.I)
    n = re.sub(r',\s*$', '', n).strip().lower()
    _norm_cache[name] = n
    return n

# Pre-build FULLY NORMALIZED move matrix: norm_moves[src_norm][dst_norm] = count
norm_moves = defaultdict(Counter)
for raw_src, dests in direct_moves.items():
    sn = _normalize_for_match(raw_src)
    for raw_dst, cnt in dests.items():
        dn = _normalize_for_match(raw_dst)
        norm_moves[sn][dn] += cnt

# Also build substring index for partial matching (one-time cost)
_all_src_norms = list(norm_moves.keys())
_all_dst_norms = set()
for dests in norm_moves.values():
    _all_dst_norms.update(dests.keys())
_all_dst_norms = list(_all_dst_norms)

# Pre-compute normalized practice_dest
norm_practice_dest = {}  # practice -> {dst_norm: count}
norm_practice_total = {}  # practice -> total
for pa, dest_counts in practice_dest.items():
    nd = Counter()
    for raw_dst, cnt in dest_counts.items():
        nd[_normalize_for_match(raw_dst)] += cnt
    norm_practice_dest[pa] = nd
    norm_practice_total[pa] = sum(nd.values())

_feeder_cache = {}
def find_direct_moves_from(source_firm, dest_firm):
    """How many partners moved from source_firm to dest_firm in the training data?"""
    key = (source_firm, dest_firm)
    if key in _feeder_cache: return _feeder_cache[key]
    src_norm = _normalize_for_match(source_firm)
    dst_norm = _normalize_for_match(dest_firm)

    total = norm_moves.get(src_norm, {}).get(dst_norm, 0)
    # Substring fallback (only if exact normalized didn't match)
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
    """Among all movers in this practice area, what fraction went to dest_firm?"""
    key = (practice, dest_firm)
    if key in _prac_dest_cache: return _prac_dest_cache[key]
    dst_norm = _normalize_for_match(dest_firm)
    total_score = 0

    for pa in practice.split(','):
        pa = pa.strip()
        if not pa or pa == 'nan':
            continue
        nd = norm_practice_dest.get(pa)
        if not nd: continue
        total_in_practice = norm_practice_total[pa]
        if total_in_practice == 0: continue

        firm_count = nd.get(dst_norm, 0)
        # Substring fallback
        if firm_count == 0:
            for dn, cnt in nd.items():
                if dst_norm in dn or dn in dst_norm:
                    firm_count += cnt
        if firm_count > 0:
            pct = firm_count / total_in_practice
            total_score = max(total_score, pct)

    _prac_dest_cache[key] = total_score
    return total_score

# ──────────────────────── CHAMBERS HELPERS ────────────────────────

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

# BROAD practice-to-Chambers mapping (used as fallback when no bio hook)
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

# BIO KEYWORD → specific Chambers sub-practices
# When we find these keywords in the partner's bio hook, we NARROW
# the Chambers lookup to only the relevant sub-practice(s)
BIO_KEYWORD_TO_CHAMBERS = {
    # Corporate sub-specialties
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

    # Litigation sub-specialties
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
    # Expanded litigation sub-specialties
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
    # Expanded bankruptcy/restructuring
    'chapter 11': ['Bankruptcy/Restructuring'],
    'chapter 7': ['Bankruptcy/Restructuring'],
    'distressed debt': ['Bankruptcy/Restructuring', 'Private Credit'],
    'distressed': ['Bankruptcy/Restructuring'],
    'workout': ['Bankruptcy/Restructuring'],
    'creditors rights': ['Bankruptcy/Restructuring'],
    'debtor in possession': ['Bankruptcy/Restructuring'],
    'special situations': ['Bankruptcy/Restructuring', 'Private Credit'],

    # Industry-specific
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
    """Given a bio hook AND the full bio text, return specific Chambers sub-practices.

    Scans the FULL BIO for keywords — not just the short hook. This captures
    partners who practice across multiple sub-specialties (e.g., entertainment
    + media + IP litigation) that a 2-5 word hook can't fully represent.

    Returns None if no keywords match (fall back to broad mapping)."""
    # Scan both the hook and the full bio for maximum coverage
    text = ((bio_hook or '') + ' ' + (full_bio or '')).lower()
    if not text.strip():
        return None
    matched = set()
    for keyword, chambers_cats in BIO_KEYWORD_TO_CHAMBERS.items():
        if keyword in text:
            matched.update(chambers_cats)
    return list(matched) if matched else None

def _firm_breadth_dampener(firm_bands):
    """Firms ranked in many practices (30+) get a Chambers dampener.
       Kirkland is Band 1 in 30+ practices — that dilutes the signal.
       A firm ranked in 5 practices that includes yours is more meaningful
       than a firm ranked in 42 practices that happens to include yours."""
    n = len(firm_bands)
    if n >= 30: return 0.70   # heavy dampener — e.g., Kirkland (42), Latham (49)
    if n >= 20: return 0.85   # moderate — e.g., DLA Piper (43), Paul Hastings (29)
    return 1.0                # no dampener — focused firm

def chambers_practice_score(partner_practice, firm_name, bio_hook='', full_bio=''):
    """Does the target firm have Chambers prestige in what this partner does?

    BINARY MODEL: What matters is that a firm IS ranked in the relevant
    practice area — not which band. Band 1 vs Band 4 is NOT a prestige
    gradient for matching purposes; it just means they're ranked.
    "Ranked = good, not ranked = bad."

    Bio hooks REINFORCE the base score (additive bonus), never reduce it.
    A firm ranked in the partner's broad practice gets a base score.
    If the firm is ALSO ranked in the specific sub-practice from the bio,
    that's an additional bonus on top.

    Scans the FULL BIO (not just the short hook) for Chambers keyword matches
    to capture all relevant sub-practices.

    Firms ranked in 30+ practices get dampened — breadth dilutes specificity.

    Scoring:
      Base (firm ranked in broad practice):     20 pts
      Bio sub-practice bonus (also ranked):    +10 pts  (max 30 total)
      Breadth dampener applied to total
    """
    if not partner_practice: return 0
    areas = [p.strip() for p in partner_practice.split(',')]
    firm_bands = get_all_bands(firm_name)
    if not firm_bands: return 0

    bio_keys = _get_bio_chambers_keys(bio_hook, full_bio=full_bio)
    dampener = _firm_breadth_dampener(firm_bands)

    BROAD_CATS = {'Litigation', 'Litigation Trial Lawyers', 'Corporate', 'Corporate/M&A'}

    best_score = 0
    for area in areas:
        area_lower = area.strip().lower()

        # Step 1: Check if firm is ranked in the BROAD practice area
        # This is the base signal — ranked or not ranked (binary)
        broad_ranked = False
        chambers_keys = PRACTICE_MAP_BROAD.get(area_lower, [])
        for ck in chambers_keys:
            if ck in firm_bands and firm_bands[ck] is not None:
                broad_ranked = True
                break
        # Fuzzy fallback for broad match
        if not broad_ranked:
            for fk, fv in firm_bands.items():
                if fv is not None and (area_lower in fk.lower() or fk.lower() in area_lower):
                    broad_ranked = True
                    break

        if not broad_ranked:
            continue  # Firm not ranked in this practice at all -> 0 pts

        # Base score: firm IS ranked in the practice (binary — band doesn't matter)
        base_score = 20

        # Step 2: Bio hook bonus — ADDITIVE, never replaces base
        # If bio hook identifies specific sub-practices AND the firm is ranked
        # in those sub-practices, add a specificity bonus
        bio_bonus = 0
        if bio_keys:
            specific_keys = [k for k in bio_keys if k not in BROAD_CATS]
            for ck in specific_keys:
                if ck in firm_bands and firm_bands[ck] is not None:
                    bio_bonus = 10  # firm ranked in the specific sub-practice too
                    break

        score = int((base_score + bio_bonus) * dampener)
        best_score = max(best_score, score)

    # ── BIO HOOK PROMOTION ──────────────────────────────────────────────
    # If the bio identifies specific sub-practices (e.g., "construction",
    # "cannabis", "franchise") and the firm IS Chambers-ranked there, treat
    # this as a PRIMARY practice match — even if the broad practice field
    # ("Litigation", "Real Estate") didn't trigger a match for this firm.
    #
    # Why: A partner whose bio says "construction" and who tells the recruiter
    # "I do construction, not real estate" should match firms ranked in
    # Construction. Before this fix, those firms got 0 Chambers points
    # because the broad practice field drove everything.
    #
    # Scoring: bio-promoted match = 20 pts (same as broad match base).
    # This doesn't override existing broad matches — it ADDS new firms
    # that are ranked in the bio-specific sub-practice but weren't caught
    # by the broad practice field. max() ensures no inflation.
    if bio_keys:
        specific_bio_keys = [k for k in bio_keys if k not in BROAD_CATS]
        for ck in specific_bio_keys:
            if ck in firm_bands and firm_bands[ck] is not None:
                bio_promoted_score = int(20 * dampener)
                best_score = max(best_score, bio_promoted_score)
                break  # one promoted match is enough for base score

    return best_score

# ──────────────────────── CITY NORMALIZATION ────────────────────────

firm_cities = {}
for entry in firms_inv:
    firm_cities[entry['firm']] = [c.strip() for c in entry['cities']]

# Add supplemental firm cities so they pass the geography hard filter
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
    }
    return aliases.get(c, c)

def city_match(partner_city, firm_city_list):
    pc = normalize_city(partner_city)
    if not pc: return False
    nfc = [normalize_city(c) for c in firm_city_list]
    if pc in nfc: return True
    pc_lower = pc.lower()
    return any(pc_lower in fc.lower() or fc.lower() in pc_lower for fc in nfc)

# ──────────────────────── PPP ALIGNMENT ────────────────────────

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
    """Estimate portable book size.
       If we have a book_est from FirmProspects, use it (in $K, convert to $).
       Otherwise, use source PPP as a rough proxy — partners at low-PPP firms
       typically have books in the 0.5x-1x PPP range."""
    if book_est and book_est > 0:
        return book_est * 1000  # book_est is in $K
    if source_ppp:
        return source_ppp * 0.7  # conservative proxy
    return 0

# ── BOOK MINIMUMS — from actual firm intelligence (firms_inventory.json) ──
# Values in $ (converted from M in inventory). These are what the firms actually
# told us or what we know from placement experience.
# For non-signed firms, we use known market expectations.
_FIRM_BOOK_MIN = {}
for _fi in firms_inv:
    _bs = _fi.get('book_size')
    if _bs:
        try:
            _FIRM_BOOK_MIN[_fi['firm']] = float(_bs) * 1_000_000
        except (ValueError, TypeError):
            pass

# Non-signed firms — known market expectations
_NONSIGNED_BOOK_MIN = {
    'Kirkland & Ellis LLP': 5_000_000,
    'Kirkland & Ellis': 5_000_000,
    'Skadden, Arps, Slate, Meagher & Flom LLP': 5_000_000,
    'Skadden': 5_000_000,
    'Ropes & Gray LLP': 5_000_000,
    'Ropes & Gray': 5_000_000,
    'Willkie Farr & Gallagher LLP': 5_000_000,
    'Willkie Farr': 5_000_000,
    'King & Spalding LLP': 5_000_000,
    'King & Spalding': 5_000_000,
    'Akin, Gump, Strauss, Hauer & Feld, LLP': 3_000_000,
    'Akin Gump': 3_000_000,
    'Proskauer Rose LLP': 3_000_000,
    'Proskauer': 3_000_000,
    'Alston & Bird LLP': 3_000_000,
    'Alston & Bird': 3_000_000,
    'White & Case LLP': 5_000_000,
    'White & Case': 5_000_000,
    'Orrick': 3_000_000,
    "O'Melveny & Myers LLP": 3_000_000,
    "O'Melveny": 3_000_000,
    'Morrison & Foerster LLP': 3_000_000,
    'Morrison & Foerster': 3_000_000,
    'Fried Frank': 5_000_000,
    'Cravath': 10_000_000,
    'Paul Weiss': 8_000_000,
    'Wilson Sonsini': 3_000_000,
}
_FIRM_BOOK_MIN.update(_NONSIGNED_BOOK_MIN)



def get_firm_book_floor(firm_name):
    """What portable book does this firm require?
       Uses actual intelligence from firm conversations and market knowledge."""
    if firm_name in _FIRM_BOOK_MIN:
        return _FIRM_BOOK_MIN[firm_name]
    # Fuzzy match
    fn_lower = _normalize_for_match(firm_name)
    for k, v in _FIRM_BOOK_MIN.items():
        if _normalize_for_match(k) == fn_lower:
            return v
    return 0  # Unknown firm — no floor

def prestige_score(partner_firm, firm_name):
    """PPP range check — closer to partner's current PPP = better fit."""
    source_ppp = get_source_ppp(partner_firm)
    target_ppp = get_target_ppp(firm_name)
    if source_ppp is None or target_ppp is None or source_ppp == 0:
        return 0
    ratio = target_ppp / source_ppp
    # How far off from 1.0 (exact match)?
    diff = abs(ratio - 1.0)
    if   diff <= 0.15: return 10   # within 15% — tight range
    elif diff <= 0.30: return 8    # within 30%
    elif diff <= 0.50: return 5    # within 50%
    elif diff <= 0.75: return 0    # stretch but possible
    else:              return -5   # too far apart

# ──────────────────────── SIMILAR-FIRM FEEDER SIGNAL ────────────────────────
# "If a firm has attrition to X, scan all similar to X."
# Two firms are "similar" if they share PPP range (+/- 30%) AND at least 2
# overlapping Chambers practice areas. When source_firm has feeder moves
# to firm_A, and firm_B is similar to firm_A, firm_B gets a reduced feeder credit.

print("Building similar-firm index for feeder expansion...")

# Build the similarity index (one-time cost)
_firm_profiles = {}  # firm_name -> {'ppp': float, 'practices': set}
for fn in [tf['name'] for tf in target_firms] + [sf['name'] for sf in supplemental_firms]:
    ppp = get_target_ppp(fn)
    bands = get_all_bands(fn)
    practices = set(bands.keys()) if bands else set()
    _firm_profiles[fn] = {'ppp': ppp, 'practices': practices}

_similar_firms = {}  # firm_name -> [similar_firm_names]
_profile_list = list(_firm_profiles.items())
for i, (fn1, p1) in enumerate(_profile_list):
    sims = []
    for j, (fn2, p2) in enumerate(_profile_list):
        if i == j: continue
        # PPP within 30%
        if p1['ppp'] and p2['ppp'] and p1['ppp'] > 0 and p2['ppp'] > 0:
            ratio = p2['ppp'] / p1['ppp']
            if ratio < 0.70 or ratio > 1.30: continue
        elif p1['ppp'] or p2['ppp']:
            continue  # one has PPP, other doesn't — can't compare
        # At least 2 shared Chambers practices
        shared = p1['practices'] & p2['practices']
        if len(shared) >= 2:
            sims.append(fn2)
    _similar_firms[fn1] = sims

_sim_counts = [len(v) for v in _similar_firms.values() if v]
print(f"  {sum(1 for v in _similar_firms.values() if v)} firms have similar peers")
if _sim_counts:
    print(f"  Avg {sum(_sim_counts)/len(_sim_counts):.1f} similar firms per firm (max {max(_sim_counts)})")

_sim_feeder_cache = {}
def find_similar_feeder_moves(source_firm, dest_firm):
    """Check if source_firm has attrition to firms SIMILAR to dest_firm.
    Returns a discounted count (half weight of direct moves)."""
    key = (source_firm, dest_firm)
    if key in _sim_feeder_cache: return _sim_feeder_cache[key]
    similar = _similar_firms.get(dest_firm, [])
    total = 0
    for sim_firm in similar:
        moves = find_direct_moves_from(source_firm, sim_firm)
        total += moves
    # Discount: similar-firm moves count at half weight
    result = total * 0.5
    _sim_feeder_cache[key] = result
    return result

# ──────────────────────── MAIN SCORING FUNCTION ────────────────────────

def match_score(partner, firm_name):
    """
    Components:
      Geography:            hard filter (partner city must be in firm's office list)
      Book-size ceiling:    hard filter (est. book < 15% of firm's stated minimum)
      Direct feeder:        0 to +35 pts (historical moves from source→target)
      Practice destination: 0 to +20 pts (practice-level gravity toward target)
      Chambers in practice: 0 to +30 pts (binary ranked/unranked + bio bonus, dampened)
      Book realism penalty: -15 to 0 pts (est. book vs firm's stated minimum)
    PPP is used ONLY as a book-size estimator — no directional preference.
    Max theoretical: ~85 pts
    """
    partner_city = partner.get('city', '')
    partner_firm = partner.get('firm', '')
    partner_practice = partner.get('practice', '')

    # ── 0. Same-firm exclusion ──
    if partner_firm and firm_name:
        pf = _normalize_for_match(partner_firm)
        fn = _normalize_for_match(firm_name)
        # Guard: both must be non-empty and >= 4 chars for substring match
        # (prevents "LLP"→"" matching everything, and "morris" matching "morrison")
        if pf and fn:
            if pf == fn:
                return -999
            if len(pf) >= 4 and len(fn) >= 4 and (pf in fn or fn in pf):
                return -999

    # ── 0b. PPP — used ONLY as book-size estimator, not directional preference ──
    # No prestige floor: partners can move up or down freely.
    # PPP feeds into book-size estimation for the ceiling check below.
    _src_ppp = get_source_ppp(partner_firm)
    _tgt_ppp = get_target_ppp(firm_name)

    # ── 0c. BOOK-SIZE CEILING (hard filter — upward) ──
    # Uses actual firm book minimums from intelligence.
    # Hard block: candidate book < 50% of firm minimum.
    # Soft penalty applied in scoring section for stretch matches.
    #
    # Changed from 15% → 50% (March 2026): the old 15% threshold allowed
    # $500K-book partners to be pitched to $3M+ PPP firms like Dechert/Cooley,
    # producing obviously unrealistic matches. 50% still allows stretch matches
    # (e.g., $1.5M book → $3M min firm) but blocks the absurd ones.
    # Feeder patterns are still captured via scoring — they just can't overcome
    # a hard book-size floor anymore.
    _book_floor = get_firm_book_floor(firm_name)
    _est_book = 0
    if _book_floor > 0:
        _est_book = estimate_book(_src_ppp, partner.get('book_est'))
        if _est_book > 0 and _est_book < _book_floor * 0.50:
            return -999

    # ── 1. GEOGRAPHY (hard filter) ──
    cities = firm_cities.get(firm_name, [])
    if not cities or not city_match(partner_city, cities):
        return -999

    # ── 2. DIRECT FEEDER (0-35 pts) ──
    # How many partners actually moved from candidate's firm to this target?
    # NOTE: Similar-firm feeder index is built above but not used in scoring
    # yet — backtesting showed it adds noise. Kept for future refinement.
    direct = find_direct_moves_from(partner_firm, firm_name)
    if   direct >= 15: feeder_pts = 35   # massive corridor (e.g., Reed Smith → H&K)
    elif direct >= 10: feeder_pts = 30   # very strong signal
    elif direct >= 5:  feeder_pts = 25
    elif direct >= 3:  feeder_pts = 20
    elif direct >= 2:  feeder_pts = 15
    elif direct >= 1:  feeder_pts = 10
    else:              feeder_pts = 0

    # ── 3. PRACTICE DESTINATION (0-20 pts) ──
    # Among all movers in this practice, what % went to this target?
    prac_pct = get_practice_dest_score(partner_practice, firm_name)
    if   prac_pct >= 0.05: prac_pts = 20   # 5%+ of all movers in practice go here
    elif prac_pct >= 0.03: prac_pts = 15
    elif prac_pct >= 0.02: prac_pts = 12
    elif prac_pct >= 0.01: prac_pts = 8
    elif prac_pct > 0:     prac_pts = 4
    else:                  prac_pts = 0

    # ── 4. CHAMBERS IN PRACTICE (0-30 pts) — biggest single factor ──
    # Use FULL BIO + bio hook to narrow to specific sub-practices
    bio_hook = partner.get('bio_hook', '')
    full_bio = _bio_by_name.get(partner.get('name', ''), '')
    chambers_pts = chambers_practice_score(partner_practice, firm_name, bio_hook=bio_hook, full_bio=full_bio)

    # ── 5. PPP — NO directional scoring ──
    # PPP is only used as a book-size proxy (for ceiling check + book penalty above).
    # No points for moving up/down/lateral — all directions weighted equally.
    ppp_pts = 0

    # ── 6. BOOK-SIZE REALISM PENALTY (-15 to 0 pts) ──
    # Penalizes stretch matches where candidate's estimated book is below
    # the firm's stated minimum. Scaled by gap size.
    # - Book >= 100% of min: no penalty
    # - Book 75-100% of min: -5 pts (slight stretch)
    # - Book 50-75% of min: -15 pts (stretch, needs strong signal)
    # - Book < 50% of min: hard-blocked above
    book_penalty = 0
    if _book_floor > 0 and _est_book > 0:
        book_ratio = _est_book / _book_floor
        if book_ratio >= 1.0:
            book_penalty = 0     # meets minimum
        elif book_ratio >= 0.75:
            book_penalty = -5    # slight stretch
        elif book_ratio >= 0.50:
            book_penalty = -15   # stretch — hard block at 0.50 handles worse

    total = feeder_pts + prac_pts + chambers_pts + ppp_pts + book_penalty
    return total

# ──────────────────────── RUN MATCHING ────────────────────────

print(f"\nRunning matching on {len(partners)} partners × {len(target_firms)} target firms...")

target_firm_names = [tf['name'] for tf in target_firms] + [sf['name'] for sf in supplemental_firms]
changed = 0
no_match = 0
examples = []

for p in partners:
    old_target = p.get('target', '')
    old_alt1 = p.get('alt1', '')

    scored = []
    for fn in target_firm_names:
        s = match_score(p, fn)
        if s > -999:
            scored.append((fn, s))
    scored.sort(key=lambda x: -x[1])

    if len(scored) >= 4:
        new_target, new_alt1, new_alt2, new_alt3 = scored[0][0], scored[1][0], scored[2][0], scored[3][0]
    elif len(scored) >= 3:
        new_target, new_alt1, new_alt2, new_alt3 = scored[0][0], scored[1][0], scored[2][0], ''
    elif len(scored) == 2:
        new_target, new_alt1, new_alt2, new_alt3 = scored[0][0], scored[1][0], '', ''
    elif len(scored) == 1:
        new_target, new_alt1, new_alt2, new_alt3 = scored[0][0], '', '', ''
    else:
        no_match += 1
        new_target, new_alt1, new_alt2, new_alt3 = '', '', '', ''

    if new_target != old_target or new_alt1 != old_alt1:
        changed += 1
        if len(examples) < 12:
            examples.append({
                'name': p['name'], 'city': p.get('city',''),
                'firm': p.get('firm',''), 'practice': p.get('practice',''),
                'before': f"{old_target} / {old_alt1}",
                'after': f"{new_target} / {new_alt1}",
                'score': scored[0][1] if scored else 0,
                'breakdown': {
                    'feeder': find_direct_moves_from(p.get('firm',''), new_target),
                    'chambers': chambers_practice_score(p.get('practice',''), new_target, bio_hook=p.get('bio_hook','')),
                    'ppp': prestige_score(p.get('firm',''), new_target),
                },
                'bio_hook': p.get('bio_hook', '(none)')
            })

    p['target'] = new_target
    p['alt1'] = new_alt1
    p['alt2'] = new_alt2
    p['alt3'] = new_alt3

    # Flag whether each assigned firm is a signed client
    p['target_signed'] = new_target in SIGNED_NAMES if new_target else True
    p['alt1_signed'] = new_alt1 in SIGNED_NAMES if new_alt1 else True
    p['alt2_signed'] = new_alt2 in SIGNED_NAMES if new_alt2 else True
    p['alt3_signed'] = new_alt3 in SIGNED_NAMES if new_alt3 else True

    # Update Chambers fields
    practice = p.get('practice', '')
    candidate_band = get_band(p.get('firm', ''), practice)
    p['candidate_band'] = candidate_band
    p['candidate_firm_canonical'] = normalize_firm(p.get('firm', ''))
    p['target_band'] = get_band(new_target, practice)
    p['alt1_band'] = get_band(new_alt1, practice) if new_alt1 else None
    p['alt2_band'] = get_band(new_alt2, practice) if new_alt2 else None
    p['alt3_band'] = get_band(new_alt3, practice) if new_alt3 else None
    bh = p.get('bio_hook', '')
    fb = _bio_by_name.get(p.get('name', ''), '')
    p['chambers_adj_target'] = chambers_practice_score(practice, new_target, bio_hook=bh, full_bio=fb)
    p['chambers_adj_alt1'] = chambers_practice_score(practice, new_alt1, bio_hook=bh, full_bio=fb) if new_alt1 else 0
    p['chambers_adj_alt2'] = chambers_practice_score(practice, new_alt2, bio_hook=bh, full_bio=fb) if new_alt2 else 0
    p['chambers_adj_alt3'] = chambers_practice_score(practice, new_alt3, bio_hook=bh, full_bio=fb) if new_alt3 else 0
    p['target_chambers_label'] = band_label(p['target_band'])
    p['alt1_chambers_label'] = band_label(p['alt1_band']) if new_alt1 else "Not ranked"
    p['alt2_chambers_label'] = band_label(p['alt2_band']) if new_alt2 else "Not ranked"
    p['alt3_chambers_label'] = band_label(p['alt3_band']) if new_alt3 else "Not ranked"
    p['candidate_chambers_label'] = band_label(candidate_band)

# ──────────────────────── RESULTS ────────────────────────

print(f"\nAssignments changed: {changed}/{len(partners)}")
print(f"No match: {no_match}")

print("\nSample assignments with breakdown:")
for ex in examples:
    bd = ex['breakdown']
    print(f"\n  {ex['name']} ({ex['city']}, {ex['firm']}, {ex['practice']})")
    print(f"    Before: {ex['before']}")
    print(f"    After:  {ex['after']}  (score: {ex['score']:.0f})")
    print(f"    Bio hook: {ex.get('bio_hook','(none)')}")
    print(f"    Why: {bd['feeder']} direct moves in data, Chambers={bd['chambers']}pts, PPP={bd['ppp']}pts")

target_dist = Counter(p['target'] for p in partners if p.get('target'))
print(f"\nTop 20 target firms by assignment count:")
for firm, count in target_dist.most_common(20):
    bands = get_all_bands(firm)
    ranked = ', '.join(f"{k}:B{v}" for k,v in bands.items()) if bands else "unranked"
    fn = _normalize_for_match(firm)
    inbound = sum(norm_moves.get(sn, {}).get(fn, 0) for sn in _all_src_norms)
    print(f"  {count:3d}  {firm}  ({ranked})  [{inbound} historical inbound moves]")

# Verification: RE partners → RE-ranked firms
re_p = [p for p in partners if 'Real Estate' in p.get('practice','')]
re_ok = sum(1 for p in re_p if get_band(p['target'], 'Real Estate') is not None)
print(f"\nRE partners → Chambers RE-ranked target: {re_ok}/{len(re_p)}")

lit_p = [p for p in partners if 'Litigation' in p.get('practice','')]
lit_ok = sum(1 for p in lit_p if get_band(p['target'], 'Litigation') is not None)
print(f"Litigation partners → Chambers Lit-ranked target: {lit_ok}/{len(lit_p)}")

corp_p = [p for p in partners if 'Corporate' in p.get('practice','')]
corp_ok = sum(1 for p in corp_p if get_band(p['target'], 'Corporate') is not None)
print(f"Corporate partners → Chambers Corp-ranked target: {corp_ok}/{len(corp_p)}")

with open('/sessions/dreamy-ecstatic-heisenberg/dashboard_data.json', 'w') as f:
    json.dump(partners, f, ensure_ascii=False)
print("\nSaved dashboard_data.json.")
