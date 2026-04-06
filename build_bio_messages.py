import pandas as pd, json, re

df = pd.read_excel('/sessions/dreamy-ecstatic-heisenberg/mnt/Downloads/LINKEDIN CONNECTED PARTNERS.xlsx')
df['Full Name'] = (df['First Name'].fillna('') + ' ' + df['Last Name'].fillna('')).str.strip()

with open('dashboard_data.json') as f:
    partners = json.load(f)

_STOP_TAIL = re.compile(
    r'\s+\b(in|on|of|a|an|the|for|to|with|by|at|from|and|or|as|that|which|'
    r'including|such|both|various|multiple|across|between|among|through|about|before|'
    r'after|during|under|over|within|without|into|onto)\b$',
    re.I
)

_CLIENT_PHRASES = re.compile(
    r'^(public companies?|corporate executives?|sponsors?\s+and|investors?\s+and|'
    r'clients?\s+and|companies?\s+and|businesses?\s+and|institutions?\s+and|'
    r'u\.s\.\s+and|underwriters?|borrowers?\s+and)',
    re.I
)

# Phrases that sound like marketing/tagline copy — reject these
_MARKETING_PHRASES = re.compile(
    r'\b(innovation|balancing|execution|cutting.edge|world.class|excellence|'
    r'emerging\s+tech|thought\s+leader|best.in.class|market.leading|industry.leading)\b',
    re.I
)

_ACRONYMS = [
    (r'\bm&a\b', 'M&A'),
    (r'\bgp-led\b', 'GP-led'),
    (r'\bgp\b', 'GP'),
    (r'\blp\b', 'LP'),
    (r'\bsec\b', 'SEC'),
    (r'\bdoj\b', 'DOJ'),
    (r'\bfinra\b', 'FINRA'),
    (r'\berisa\b', 'ERISA'),
    (r'\bipo\b', 'IPO'),
    (r'\bspac\b', 'SPAC'),
    (r'\bfcpa\b', 'FCPA'),
    (r'\blbo\b', 'LBO'),
    (r'\baml\b', 'AML'),
    (r'\bu\.s\.\b', 'U.S.'),
]

def fix_acronyms(h):
    for pat, repl in _ACRONYMS:
        h = re.sub(pat, repl, h)
    return h


def clean_hook(h):
    if not h: return ''
    h = h.strip().rstrip('.,;:').strip()

    # Remove leading articles/possessives (loop to catch double)
    for _ in range(3):
        h = re.sub(r'^(the|a|an|his|her|their|its|this|such|particular|various|broad|extensive|diverse|wide)\s+', '', h, flags=re.I).strip()

    # Handle "advising/representing X on/in TOPIC" — extract TOPIC
    m_verb = re.match(
        r'^(?:advising|counseling|representing|assisting|serving|handling|managing|'
        r'advises|counsels|represents|assists|serves|handles|manages|conducts)\s+',
        h, re.I
    )
    if m_verb:
        rest = h[m_verb.end():]
        m_prep = re.search(
            r'\s+(?:on|in)\s+(?!connection|a\s+wide|various|multiple|all\s+aspects|addition|both\b)(.+)',
            rest, re.I
        )
        if m_prep and len(m_prep.group(1).split()) >= 2:
            h = m_prep.group(1).strip()
        else:
            # If no extractable topic after the verb, reject entirely
            return ''

    # Strip leaked verbs at start (advises, conducts, etc.)
    h = re.sub(r'^(?:advises|conducts|assists|represents|manages|handles|helps)\s+', '', h, flags=re.I).strip()

    # Remove leading articles again after verb stripping
    for _ in range(2):
        h = re.sub(r'^(the|a|an|his|her|their|its|this|such|representation|organization|formation)\s+(?:of\s+)?', '', h, flags=re.I).strip()

    if _CLIENT_PHRASES.match(h):
        return ''

    # Cut at first comma, semicolon, or "as well as" / "with emphasis" / "including"
    h = re.split(r'\s*[,;]\s*|\s+as\s+well\s+as\s+|\s+with\s+(?:an?\s+)?emphasis\s+|\s+including\s+|\s+particularly\s+', h, flags=re.I)[0].strip()

    # Strip trailing stop words
    prev = None
    while h != prev:
        prev = h
        h = _STOP_TAIL.sub('', h).rstrip('.,;: ').strip()

    # Trim to max 5 words (tighter — messages read better short)
    words = h.split()
    if len(words) > 5:
        h = ' '.join(words[:5])
        prev = None
        while h != prev:
            prev = h
            h = _STOP_TAIL.sub('', h).rstrip('.,;:').strip()

    # Final quality checks — reject if still garbage
    words = h.split()
    if len(words) < 2 and h.lower() not in ('m&a', 'derivatives', 'restructuring', 'bankruptcy',
                                              'antitrust', 'erisa', 'immigration', 'cybersecurity',
                                              'appellate', 'patent'):
        return ''  # single generic word = useless
    if re.match(r'^(range|variety|number|array|multitude|spectrum)\b', h, re.I):
        return ''

    return h.lower().strip()


def extract_bio_hook(bio):
    if not bio or bio == 'nan' or len(bio) < 30:
        return None

    # Strip out quoted testimonials (Chambers quotes etc.) which contain
    # phrases like "navigate disputes in anticipation of litigation" that
    # are NOT the partner's actual practice description.
    # Only strip actual quoted text and attribution lines — preserve the rest.
    bio_clean = re.sub(r'\u201c[^\u201d]*\u201d', ' ', bio)  # smart quotes
    bio_clean = re.sub(r'"[^"]{10,}"', ' ', bio_clean)  # straight quotes (min 10 chars to avoid abbreviations)
    bio_clean = re.sub(r'Chambers\s+USA\s+\d{4}', ' ', bio_clean)

    raw_sents = re.split(r'(?<=[.!?])\s+', bio_clean.strip())
    sents = []
    i = 0
    while i < len(raw_sents):
        s = raw_sents[i]
        while i + 1 < len(raw_sents) and len(s.split()) <= 2:
            i += 1
            s = s + ' ' + raw_sents[i]
        sents.append(s)
        i += 1
    check = sents[:5]

    STOP = (
        r'\s+in\s+(?:connection\s+with|a\s+wide|various|multiple|all\s+aspects|addition|both\s)'
        r'|\s+across\s+(?:a\s+wide|multiple|various|all)'
        r'|\s+(?:as\s+well|particularly)'
        r'|\s+and\s+(?:non-U\.S\.|u\.s\.\s+and)'
        r'|\s+before\s+the\b'
        r'|\s+at\s+(?:the|both)\b'
        r'|\s+including\b'
    )

    patterns = [
        (r'understanding\s+of\s+([\w][\w\s,&/-]+?)'
         r'(?:' + STOP + r'|\s*,|\s*\.|\s+which|\s+that)', True),
        (r'(?:focuses?|concentrates?)\s+(?:his|her|their|the)?\s*practice\s+on\s+'
         r'((?:[A-Z]?[\w]+(?:\s+[\w&,/-]+){0,7}?))'
         r'(?:' + STOP + r'|\s*,\s*including|\s*\.|\s+advises?|\s+helps?|\s+includ)', True),
        (r'(?:focuses?|concentrates?)\s+on\s+'
         r'((?:[A-Z]?[\w]+(?:\s+[\w&,/-]+){0,7}?))'
         r'(?:' + STOP + r'|\s*,\s*including|\s*\.|\s+advises?|\s+helps?)', True),
        (r'practice\s+focused\s+on\s+([\w][\w\s,&/-]+?)'
         r'(?:' + STOP + r'|\s*,|\s*\.)', True),
        (r'focusing\s+on\s+([\w][\w\s,&/-]+?)'
         r'(?:' + STOP + r'|\s*,\s*including|\s*\.|\s+and\s)', True),
        (r'specializes?\s+in\s+([\w][\w\s,&/-]+?)'
         r'(?:\s*,\s*(?:including|with|and)\s|\s*\.)', True),
        (r'(?:particular\s+)?expertise\s+in\s+([\w][\w\s,&/-]+?)'
         r'(?:\s*,|\s*\.)', True),
        (r'practice\s+(?:includes?|spans?|covers?|encompasses?)\s+([\w][\w\s,&/-]+?)'
         r'(?:\s*,\s*including|\s*\.)', True),
        (r'represents?\s+(?:clients?|companies|institutions?|sponsors?)\s+in\s+'
         r'([\w][\w\s,&/-]+?)(?:\s*,\s*(?:including|with)\s|\s*\.)', True),
        (r'advises?\s+(?:clients?|companies|private\s+equity\s+(?:funds?|sponsors?|firms?)|'
         r'investors?|sponsors?|funds?|businesses?)\s+on\s+'
         r'([\w][\w\s,&/-]+?)(?:\s*,|\s*\.)', True),
        (r'lead\s+counsel\s+(?:for|on)\s+(?:clients\s+(?:on|in)\s+)?'
         r'([\w][\w\s,&/-]+?)(?:\s*\.|\s*,)', True),
        (r'helps?\s+clients?\s+(?:navigate\s+(?:and\s+resolve\s+)?|resolve\s+|with\s+)'
         r'([\w][\w\s,&/-]+?)(?:\s*\.|\s*,)', True),
        (r'experience\s+in\s+([\w][\w\s,&/-]+?)(?:\s*,|\s*\.)', True),
    ]

    for pat, _ in patterns:
        for sent in check:
            m = re.search(pat, sent, re.I)
            if m:
                hook = clean_hook(m.group(1))
                if not hook or len(hook) < 4:
                    continue
                first_word = hook.split()[0].lower()
                if first_word in ('and', 'or', 'but', 'the', 'a', 'an', 'in', 'on', 'of'):
                    continue
                if re.match(r'^(complex|broad|various|wide|multiple|all|many|extensive|'
                            r'diverse|variety|range\s+of|full\s+range)',
                            hook, re.I):
                    continue
                if re.match(r'^(advising|representing|counseling|assisting|handling|managing)',
                            hook, re.I) and len(hook.split()) <= 4:
                    continue
                # Reject marketing/tagline phrases
                if _MARKETING_PHRASES.search(hook):
                    continue
                return fix_acronyms(hook)

    # Named-practice fallback
    bio_head = ' '.join(sents[:3])
    named = re.search(
        r'\b((?:'
        r'GP-led\s+transactions?|'
        r'fund\s+formation|'
        r'secondary\s+(?:market|transactions?)|'
        r'private\s+(?:investment\s+)?funds?|'
        r'investment\s+funds?|'
        r'hedge\s+funds?|'
        r'closed-end\s+funds?|'
        r'liquidity\s+solutions?|'
        r'private\s+equity|'
        r'venture\s+capital|'
        r'growth\s+(?:equity|capital)|'
        r'mergers?\s+(?:and|&)\s+acquisitions?|'
        r'M&A|'
        r'leveraged\s+(?:buyouts?|finance)|'
        r'capital\s+markets?|'
        r'debt\s+(?:finance|capital|markets?)|'
        r'structured\s+finance|'
        r'derivatives|'
        r'real\s+estate\s+(?:finance|transactions?|development|investment)|'
        r'intellectual\s+property|'
        r'patent(?:\s+litigation)?|'
        r'trademark(?:\s+litigation)?|'
        r'bankruptcy|'
        r'restructuring|'
        r'labor\s+(?:and|&)\s+employment|'
        r'employment\s+litigation|'
        r'securities\s+(?:litigation|fraud|enforcement|regulation)|'
        r'SEC\s+enforcement|'
        r'regulatory\s+enforcement|'
        r'securities,\s+derivatives|'
        r'white\s+collar|'
        r'antitrust(?:\s+litigation)?|'
        r'class\s+actions?|'
        r'product\s+liability|'
        r'commercial\s+litigation|'
        r'appellate(?:\s+litigation)?|'
        r'insurance\s+(?:coverage|defense|litigation)|'
        r'construction\s+(?:litigation|disputes?)|'
        r'tax\s+(?:planning|litigation|controversy)|'
        r'ERISA|'
        r'healthcare\s+(?:transactions?|regulation)|'
        r'environmental(?:\s+law)?|'
        r'immigration|'
        r'data\s+privacy|'
        r'cybersecurity'
        r'))\b',
        bio_head, re.I
    )
    if named:
        return fix_acronyms(named.group(1).lower().strip())

    return None


# Industry-standard firm name shortenings — used in all outreach messages
FIRM_ALIASES = {
    'latham & watkins': 'Latham',
    'kirkland & ellis': 'Kirkland',
    'skadden, arps, slate, meagher & flom': 'Skadden',
    'skadden arps slate meagher & flom': 'Skadden',
    'simpson thacher & bartlett': 'Simpson Thacher',
    'davis polk & wardwell': 'Davis Polk',
    'cleary gottlieb steen & hamilton': 'Cleary',
    'cleary gottlieb': 'Cleary',
    'wilmer cutler pickering hale and dorr': 'WilmerHale',
    'wilmerhale': 'WilmerHale',
    'quinn emanuel urquhart & sullivan': 'Quinn Emanuel',
    'weil, gotshal & manges': 'Weil',
    'weil gotshal & manges': 'Weil',
    'gibson, dunn & crutcher': 'Gibson Dunn',
    'gibson dunn & crutcher': 'Gibson Dunn',
    "o'melveny & myers": "O'Melveny",
    'paul, weiss, rifkind, wharton & garrison': 'Paul Weiss',
    'paul weiss rifkind wharton & garrison': 'Paul Weiss',
    'willkie farr & gallagher': 'Willkie Farr',
    'debevoise & plimpton': 'Debevoise',
    'cahill gordon & reindel': 'Cahill',
    'norton rose fulbright': 'Norton Rose',
    'morgan, lewis & bockius': 'Morgan Lewis',
    'morgan lewis & bockius': 'Morgan Lewis',
    'freshfields bruckhaus deringer': 'Freshfields',
    'faegre drinker biddle & reath': 'Faegre Drinker',
    'arentfox schiff': 'ArentFox',
    'mcdermott will & emery': 'McDermott',
    'sidley austin': 'Sidley',
    'dechert llp': 'Dechert',
    'cooley llp': 'Cooley',
    'fried, frank, harris, shriver & jacobson': 'Fried Frank',
    'fried frank harris shriver & jacobson': 'Fried Frank',
    'sullivan & cromwell': 'Sullivan & Cromwell',
    'cravath, swaine & moore': 'Cravath',
    'king & spalding': 'King & Spalding',
    'ropes & gray': 'Ropes & Gray',
    'white & case': 'White & Case',
    'akin, gump, strauss, hauer & feld': 'Akin Gump',
    'akin gump strauss hauer & feld': 'Akin Gump',
    'alston & bird': 'Alston & Bird',
    'morrison & foerster': 'MoFo',
    'orrick, herrington & sutcliffe': 'Orrick',
    'proskauer rose': 'Proskauer',
    'vinson & elkins': 'V&E',
    'wilson sonsini goodrich & rosati': 'Wilson Sonsini',
    'wilson sonsini goodrich': 'Wilson Sonsini',
    'paul, weiss, rifkind, wharton & garrison': 'Paul Weiss',
    'paul weiss rifkind wharton & garrison': 'Paul Weiss',
    'fried, frank, harris, shriver & jacobson': 'Fried Frank',
    'fried frank harris shriver & jacobson': 'Fried Frank',
}

def sf(name):
    if not name: return ''
    # Check aliases first (case-insensitive)
    key = re.sub(r'\s+', ' ', name.strip()).lower()
    key_no_suffix = re.sub(r'\s*(llp|llc|pc|pllc|pa|lp|ltd|p\.c\.|p\.a\.)$', '', key).strip()
    if key in FIRM_ALIASES: return FIRM_ALIASES[key]
    if key_no_suffix in FIRM_ALIASES: return FIRM_ALIASES[key_no_suffix]
    n = re.sub(r'\b(LLP|LLC|PC|PLLC|PA|LP|LTD|P\.C\.|P\.A\.)\b', '', name, flags=re.I)
    n = re.sub(r',\s*$', '', n).strip()
    words = n.split()
    stops = {'&', 'and', 'of', 'the'}
    kept = []
    for w in words:
        if len(kept) >= 3 and w.lower() in stops: break
        kept.append(w)
        if len(kept) >= 4: break
    return ' '.join(kept)


def build_messages(first, firm1, firm2, city, practice, hook, seed=0):
    f1, f2 = sf(firm1), sf(firm2)
    p = practice.split(',')[0].strip().lower()
    # NEVER say "commercial real estate" — always just "real estate"
    p = p.replace('commercial real estate', 'real estate')
    both = bool(f1 and f2 and f1 != f2)
    firms = f"{f1} and {f2}" if both else f1
    their = 'their' if both else 'its'
    believe = 'both' if both else 'it'
    search_word = 'searches' if both else 'search'

    # ECVC hook
    if hook and hook.lower() in ('venture capital', 'emerging companies', 'emerging companies and venture capital'):
        hook = 'ECVC'

    # What to use in the practice-specific variant (Alt2)
    spec = hook if hook else p

    # 4 closings — Ari's approved message structure
    # Primary & Alt1: generic body (NO practice area, just "lateral searches")
    # Alt2: practice-specific body ("searches for their {practice} groups")
    closings = [
        "Would you be open to a chat and going over options together?",
        "Are these firms that could interest you?",
        "Are these firms you'd consider speaking with?",
        "Are you currently open to conversations?",
    ]

    generic_body = f"I'm working with {firms} on {their} lateral {search_word} and believe {believe} could be a great platform for you."
    practice_body = f"I'm working with {firms} on {their} {search_word} for {their} {spec} {'groups' if both else 'group'} and believe {believe} could be a great platform for you."

    ci = seed % 4
    primary = f"Hi {first},\n\n{generic_body}\n\n{closings[ci]}"
    alt1    = f"Hi {first},\n\n{generic_body}\n\n{closings[(ci + 1) % 4]}"
    alt2    = f"Hi {first},\n\n{practice_body}\n\n{closings[(ci + 2) % 4]}"

    return primary, alt1, alt2


bio_lookup = {
    r['Full Name']: str(r['Full Bio']) if pd.notna(r['Full Bio']) else ''
    for _, r in df.iterrows()
}

no_hook = 0
hook_ok = 0
samples = []

_BAD_TAIL = re.compile(r'\s+(in|on|of|a|an|the|for|to|with|by|at|from|and|or)$', re.I)

def validate_hook(hook, practice):
    """Reject hooks that would read badly in messages or mismatch the practice."""
    if not hook:
        return None
    h = hook.lower().strip()
    # Contains action verbs / broken phrases / venue-not-specialty
    if re.search(r'\b(to counsel|to help|to assist|to advise|to represent|issues related|related to|advises|conducts|assists|represents)\b', h):
        return None
    if re.search(r'\b(anticipation|navigate|resolution|resolving|through to|service.based|some of the|one of the)\b', h):
        return None
    if re.search(r'\b(state and federal courts?|federal and state courts?|permitting applications?|organizational structuring)\b', h):
        return None
    # Litigator with pure transactional hook
    if 'litigation' in practice.lower() and h in ('m&a', 'private equity', 'venture capital', 'hedge funds', 'fund formation'):
        return None
    # Too long
    if len(h.split()) > 5:
        return None
    # Starts with garbage
    if re.match(r'^(formation|organization|issues|representation|range|variety|deal\s+across|transactions?\s+across)', h):
        return None
    # Redundant with practice (e.g. hook="labor and employment", practice="Labor & Employment")
    prac_norm = practice.split(',')[0].strip().lower().replace('&', 'and')
    if h.replace('&', 'and') == prac_norm:
        return None
    return hook

for i, p in enumerate(partners):
    # Use stored bio_hook if already set (preserves manual corrections);
    # only fall back to LinkedIn bio extraction if empty.
    # bio_hook='' means "explicitly no hook" (don't re-extract)
    if 'bio_hook' in p and p['bio_hook'] == '':
        hook = None
    elif p.get('bio_hook'):
        hook = validate_hook(p['bio_hook'], p.get('practice', ''))
        if not hook:
            p['bio_hook'] = ''  # was bad, clear it
    else:
        bio = bio_lookup.get(p['name'], '')
        hook = extract_bio_hook(bio)
        hook = validate_hook(hook, p.get('practice', ''))
        p['bio_hook'] = hook or ''
    if hook:
        hook_ok += 1
        if len(samples) < 20:
            samples.append((p['name'], p.get('practice', ''), hook))
    else:
        no_hook += 1

    msg, alt1, alt2 = build_messages(
        p['first'], p['target'], p.get('alt1', ''),
        p['city'], p.get('practice', ''), hook, seed=i
    )
    p['message'] = msg
    p['msg_alt1'] = alt1
    p['msg_alt2'] = alt2

print(f"With hook: {hook_ok}/694 ({hook_ok * 100 // 694}%)")
print(f"Without hook (generic): {no_hook}/694")
print(f"\nSample hooks:")
for name, prac, hook in samples:
    print(f"  {name} ({prac}): '{hook}'")

with open('dashboard_data.json', 'w') as f:
    json.dump(partners, f, ensure_ascii=False)
print("\nSaved.")
