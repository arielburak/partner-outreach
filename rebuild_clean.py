#!/usr/bin/env python3
"""Clean rebuild of Outreach.html — extracts template, removes duplicates, injects fresh data+JS.
Fixes applied:
  1. buildQ() pushes skipped/later to end in ALL views (not just Pending)
  2. Firm table moved to RIGHT side of card (same eye level)
  3. Firm table includes Book Size from Cold Call Sheet + PPP + city match
  4. Current firm PPP shown on card (signal bar area)
  5. COLD_CALL_FIRMS data injected for city/book filtering
"""
import json, re

with open('/sessions/dreamy-ecstatic-heisenberg/mnt/outputs/Outreach.html') as f:
    content = f.read()

# Read fresh data
with open('/sessions/dreamy-ecstatic-heisenberg/dashboard_data.json') as f:
    general = json.load(f)
with open('/sessions/dreamy-ecstatic-heisenberg/fox_normalized.json') as f:
    fox = json.load(f)
with open('/sessions/dreamy-ecstatic-heisenberg/mnt/outputs/legal-recruiting-model/firm_ppp.json') as f:
    firm_ppp = json.load(f)
with open('/sessions/dreamy-ecstatic-heisenberg/cold_call_firms.json') as f:
    cold_call_firms = json.load(f)

lines = content.split('\n')

# Find key sections
html_end = None
script_start = None
non_signed_line = None
ds_line_idx = None
first_let_line = None

for i, line in enumerate(lines):
    if line.strip() == '<script>':
        script_start = i
        html_end = i - 1
    if line.strip().startswith('const NON_SIGNED=') and non_signed_line is None:
        non_signed_line = i
    if line.strip().startswith('const DS=') and ds_line_idx is None:
        ds_line_idx = i
    if "let tab='general'" in line and first_let_line is None:
        first_let_line = i

print(f"HTML ends at line {html_end+1}")
print(f"<script> at line {script_start+1}")
print(f"First let at line {first_let_line+1}")

# ─── CSS ───────────────────────────────────────────────────────────────
css_addition = """
.city-tag{font-size:12px;color:#88aabb;font-weight:600;padding:2px 8px;background:#0d1f2a;border-radius:8px;border:1px solid #1a3040;}
.also-consider{display:flex;align-items:center;gap:10px;padding:10px 28px;font-size:11px;color:#555;flex-wrap:wrap;border-top:1px solid #1e1e3a;}
.also-consider-label{color:#555;font-weight:600;white-space:nowrap;}
.firm-chip{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:8px;padding:5px 12px;color:#4f8ef7;font-size:11px;font-weight:600;cursor:pointer;transition:all .2s;white-space:nowrap;}
.firm-chip:hover{background:#22224a;border-color:#4f8ef7;transform:translateY(-1px);box-shadow:0 2px 8px rgba(79,142,247,0.15);}
.firm-chip .chip-chambers{font-size:9px;color:#666;font-weight:400;margin-left:4px;}
.firm-table-panel{background:linear-gradient(145deg,#1a1a30,#161628);border:1px solid #2a2a4a;border-radius:16px;padding:18px 20px;width:340px;flex-shrink:0;overflow-y:auto;max-height:calc(100vh - 200px);align-self:flex-start;box-shadow:0 4px 24px rgba(0,0,0,0.3);}
.firm-table-panel h3{font-size:13px;font-weight:700;color:#888;margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px;}
.firm-table{width:100%;border-collapse:collapse;font-size:12px;}
.firm-table th{text-align:left;padding:5px 8px;border-bottom:2px solid #2a2a4a;color:#555;font-weight:600;font-size:11px;}
.firm-table td{padding:4px 8px;border-bottom:1px solid #1e1e3a;color:#bbb;}
.firm-table tr:hover td{background:#22223a;}
.firm-table .ft-name{color:#ddd;font-weight:500;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.firm-table .ft-ppp{color:#4f8ef7;text-align:right;font-weight:600;font-size:11px;}
.firm-table .ft-book{color:#e67e22;text-align:right;font-weight:600;font-size:11px;}
.firm-table .ft-match{text-align:center;}
.ft-dot{display:inline-block;width:8px;height:8px;border-radius:50%;}
.ft-dot.target{background:#4f8ef7;}
.ft-dot.alt{background:#a78bfa;}
.src-ppp-tag{display:inline-block;font-size:11px;color:#e67e22;font-weight:600;margin-left:4px;padding:2px 8px;background:#2a1500;border-radius:8px;border:1px solid #3a2500;}
.practice-tag{display:inline-block;font-size:11px;color:#a78bfa;font-weight:600;padding:2px 8px;background:#1e0a3c;border-radius:8px;border:1px solid #2a1550;}
.bio-hook-tag{display:inline-block;font-size:11px;color:#7a8a9a;font-style:italic;margin-left:6px;}
.pitch-override-indicator{font-size:10px;color:#e67e22;font-weight:500;margin-left:4px;font-style:italic;}
"""

# ─── HTML CLEANUP ──────────────────────────────────────────────────────
html_part = '\n'.join(lines[:script_start+1])

# Remove old CSS
for pattern in [
    r'\.city-tag\{[^}]*\}', r'\.also-consider\{[^}]*\}', r'\.also-consider-label\{[^}]*\}',
    r'\.firm-chip\{[^}]*\}', r'\.firm-chip:hover\{[^}]*\}', r'\.firm-chip \.chip-chambers\{[^}]*\}',
    r'\.firm-table-panel\{[^}]*\}', r'\.firm-table-panel h3\{[^}]*\}',
    r'\.firm-table\{[^}]*\}', r'\.firm-table th\{[^}]*\}',
    r'\.firm-table td\{[^}]*\}', r'\.firm-table tr:hover td\{[^}]*\}',
    r'\.firm-table \.ft-\w+\{[^}]*\}', r'\.ft-dot\{[^}]*\}', r'\.ft-dot\.\w+\{[^}]*\}',
    r'\.src-ppp-tag\{[^}]*\}',
    r'\.practice-tag\{[^}]*\}', r'\.bio-hook-tag\{[^}]*\}',
    r'\.pitch-override-indicator\{[^}]*\}',
]:
    html_part = re.sub(pattern, '', html_part)

# Remove old city-tag spans, firm-table-panel HTML
html_part = re.sub(r'\s*<span class="city-tag"[^>]*></span>\n?', '', html_part)
# Remove old firm-table-panel (multiline)
html_part = re.sub(r'\s*<div class="firm-table-panel".*?</table>\s*</div>', '', html_part, flags=re.DOTALL)
# Remove old src-ppp-tag spans
html_part = re.sub(r'\s*<span class="src-ppp-tag"[^>]*></span>\n?', '', html_part)
# Remove old practice-tag and bio-hook-tag spans
html_part = re.sub(r'\s*<span class="practice-tag"[^>]*></span>', '', html_part)
html_part = re.sub(r'\s*<span class="bio-hook-tag"[^>]*></span>', '', html_part)
# Remove orphan <br> before practice tag (from previous injection)
html_part = re.sub(r'\s*<br>\s*(?=<span class="practice-tag")', '', html_part)
# Remove old pitch-override-ind spans
html_part = re.sub(r'<span id="pitch-override-ind"[^>]*></span>', '', html_part)
# Clean multiple consecutive <br> tags
html_part = re.sub(r'(\s*<br>\s*){2,}', '\n        ', html_part)

# Add pitch-override-ind span before chambers-badges
if 'pitch-override-ind' not in html_part:
    html_part = html_part.replace(
        '<span id="chambers-badges"',
        '<span id="pitch-override-ind" class="pitch-override-indicator" style="display:none"></span><span id="chambers-badges"'
    )

# Add CSS before </style>
# Also override base card CSS for better design
card_css_overrides = """
.main{flex:1;display:flex;align-items:flex-start;justify-content:center;padding:20px 24px;overflow-y:auto;gap:20px;}
.card{background:linear-gradient(145deg,#1a1a30,#161628);border:1px solid #2a2a4a;border-radius:16px;width:100%;max-width:720px;padding:0;position:relative;box-shadow:0 4px 24px rgba(0,0,0,0.3);}
.card-header{padding:24px 28px 16px;border-bottom:1px solid #1e1e3a;}
.partner-name{font-size:26px;font-weight:800;margin-bottom:8px;letter-spacing:-0.3px;}
.partner-sub{font-size:12px;color:#666;display:flex;gap:8px;align-items:center;flex-wrap:wrap;line-height:1.8;}
.arrow{color:#4f8ef7;font-size:14px;opacity:0.7;}
.badge{font-size:10px;padding:3px 10px;border-radius:12px;font-weight:600;letter-spacing:0.3px;text-transform:uppercase;}
.warm{background:#3d3000;color:#ffd166;border:1px solid #5a4a00;}
.cold{background:#0d1f3c;color:#4f8ef7;border:1px solid #1a3060;}
.sent-badge{background:#0d2d1f;color:#27ae60;border:1px solid #1a4a2a;}
.signal-bar{display:flex;gap:6px;padding:12px 28px;align-items:center;flex-wrap:wrap;}
.signal-pill{font-size:10px;padding:3px 10px;border-radius:8px;background:#111;border:1px solid #2a2a4a;color:#777;}
.msg-area{background:#0d0d18;border:1px solid #252540;border-radius:10px;padding:18px 20px;font-size:13.5px;line-height:1.8;color:#ddd;white-space:pre-wrap;margin:0 28px 16px;min-height:88px;max-height:220px;overflow-y:auto;user-select:all;}
.alt-tabs{display:flex;gap:6px;padding:0 28px;margin-bottom:10px;}
.actions{display:flex;gap:8px;padding:0 28px;margin-bottom:10px;}
.btn{padding:10px 16px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;display:flex;align-items:center;gap:6px;transition:all 0.2s;flex:1;justify-content:center;}
.btn-copy{background:#4f8ef7;color:white;}.btn-copy:hover{background:#3a7de0;transform:translateY(-1px);}
.btn-li{background:#0077b5;color:white;}.btn-li:hover{background:#005f92;transform:translateY(-1px);}
.btn-fp{background:#6c3fc8;color:white;}.btn-fp:hover{background:#5a32a8;transform:translateY(-1px);}
.nav{display:flex;gap:8px;padding:0 28px 20px;}
.btn-next{background:#27ae60;color:white;font-size:13px;flex:1;}.btn-next:hover{background:#219a52;transform:translateY(-1px);}
.last-contact-bar{font-size:11px;color:#555;padding:10px 28px;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;border-top:1px solid #1e1e3a;}
.pitch-override-row{display:flex;align-items:center;gap:8px;padding:12px 28px;flex-wrap:wrap;background:#12122a;border-top:1px solid #1e1e3a;}
.fu-edit-row{display:none;background:#0d0d1a;border:1px solid #2a2a4a;border-radius:7px;padding:12px 14px;margin:0 28px 12px;gap:8px;flex-direction:column;}
"""
# Remove old base CSS definitions that we're overriding
for old_css in [
    r'\.main\{[^}]*\}',
    r'\.card\{[^}]*\}',
    r'\.card-header\{[^}]*\}',
    r'\.partner-name\{[^}]*\}',
    r'\.partner-sub\{[^}]*\}',
    r'\.arrow\{[^}]*\}',
    r'\.badge\{[^}]*\}',
    r'\.warm\{[^}]*\}',
    r'\.cold\{[^}]*\}',
    r'\.sent-badge\{[^}]*\}',
    r'\.signal-bar\{[^}]*\}',
    r'\.signal-pill\{font-size[^}]*\}',
    r'\.msg-area\{[^}]*\}',
    r'\.alt-tabs\{[^}]*\}',
    r'\.actions\{[^}]*\}',
    r'\.btn\{[^}]*\}',
    r'\.btn-copy\{[^}]*\}',
    r'\.btn-copy:hover\{[^}]*\}',
    r'\.btn-li\{[^}]*\}',
    r'\.btn-li:hover\{[^}]*\}',
    r'\.btn-fp\{[^}]*\}',
    r'\.btn-fp:hover\{[^}]*\}',
    r'\.nav\{[^}]*\}',
    r'\.btn-next\{[^}]*\}',
    r'\.btn-next:hover\{[^}]*\}',
    r'\.last-contact-bar\{[^}]*\}',
    r'\.pitch-override-row\{[^}]*\}',
    r'\.fu-edit-row\{display:none[^}]*\}',
]:
    html_part = re.sub(old_css, '', html_part, count=1)

html_part = html_part.replace('</style>', card_css_overrides + css_addition + '</style>')

# Add city span + src-ppp span + practice/bio after p-title
if 'id="p-city"' not in html_part:
    html_part = html_part.replace(
        '<span class="title-tag" id="p-title" style="display:none"></span>',
        '<span class="title-tag" id="p-title" style="display:none"></span>\n        <span class="city-tag" id="p-city" style="display:none"></span>\n        <span class="src-ppp-tag" id="p-src-ppp" style="display:none"></span>'
    )
# Add practice + bio_hook display after src-ppp (or after city if already present)
if 'id="p-practice"' not in html_part:
    html_part = html_part.replace(
        '<span class="src-ppp-tag" id="p-src-ppp" style="display:none"></span>',
        '<span class="src-ppp-tag" id="p-src-ppp" style="display:none"></span>\n        <br><span class="practice-tag" id="p-practice" style="display:none"></span><span class="bio-hook-tag" id="p-bio-hook" style="display:none"></span>'
    )

# Clean ALL old also-consider divs
while '<div class="also-consider"' in html_part:
    start = html_part.find('<div class="also-consider"')
    end = html_part.find('</div>', start)
    if end > start:
        html_part = html_part[:start] + html_part[end+6:]
    else:
        break

# Add also-consider before pitch-edit-row (if not already present)
if 'id="also-consider"' not in html_part:
    html_part = html_part.replace(
        '<div id="pitch-edit-row"',
        '<div class="also-consider" id="also-consider" style="display:none">\n      <span class="also-consider-label">Also consider:</span>\n      <span class="firm-chip" id="chip-alt2" onclick="quickPitch(\'alt2\', event)" title="Click = replace 1st firm · Shift+click = replace 2nd firm" style="cursor:pointer"></span>\n      <span class="firm-chip" id="chip-alt3" onclick="quickPitch(\'alt3\', event)" title="Click = replace 1st firm · Shift+click = replace 2nd firm" style="cursor:pointer"></span>\n    </div>\n    <div id="pitch-edit-row"'
    )

# Fix .main layout — flex row, centered, with gap
# align-items:flex-start keeps card/firm-table at top; justify-content:center centers horizontally
html_part = re.sub(r'<div class="main"[^>]*>', '<div class="main" style="gap:16px;flex-wrap:nowrap;justify-content:center;align-items:flex-start;">', html_part)

# Remove old firm-table-panel that's OUTSIDE main (after the closing </div> chain)
# It was placed before the toast div — clean it
html_part = re.sub(r'\s*<div class="firm-table-panel"[^>]*>.*?</table>\s*</div>\s*(?=</div>\s*<div class="toast")', '', html_part, flags=re.DOTALL)

# Add firm-table-panel INSIDE .main, right AFTER the card closes
# Use div counting from the card opening to find where the card closes
if 'id="firm-table-panel"' not in html_part:
    card_start = html_part.find('<div class="card" id="card">')
    if card_start >= 0:
        depth = 0
        i = card_start
        card_close_pos = -1
        while i < len(html_part):
            if html_part[i:i+4] == '<div':
                depth += 1
            elif html_part[i:i+6] == '</div>':
                depth -= 1
                if depth == 0:
                    card_close_pos = i + 6  # position AFTER the card's closing </div>
                    break
            i += 1
        if card_close_pos >= 0:
            firm_table_html = '\n  <div class="firm-table-panel" id="firm-table-panel" style="display:none">\n    <h3>Available Firms</h3>\n    <table class="firm-table" id="firm-table">\n      <thead><tr><th>Firm</th><th style="text-align:right">PPP</th><th style="text-align:right">Book</th><th></th></tr></thead>\n      <tbody id="firm-table-body"></tbody>\n    </table>\n  </div>'
            html_part = html_part[:card_close_pos] + firm_table_html + html_part[card_close_pos:]
            print(f"Inserted firm-table-panel right after card close (at char {card_close_pos})")
        else:
            print("WARNING: Could not find card's closing </div>")
    else:
        print("WARNING: Could not find card opening tag")

# Ensure .main closes before fu-view by checking actual div depth
fu_view_tag = '<div class="fu-view" id="fu-view">'
main_start_check = html_part.find('<div class="main"')
fu_pos = html_part.find(fu_view_tag)
if main_start_check >= 0 and fu_pos >= 0:
    section = html_part[main_start_check:fu_pos]
    d = 0
    for ch_i in range(len(section)):
        if section[ch_i:ch_i+4] == '<div':
            d += 1
        elif section[ch_i:ch_i+6] == '</div>':
            d -= 1
    if d > 0:
        # Need to add closing </div> tags to close .main before fu-view
        closes_needed = '</div>\n' * d
        html_part = html_part[:fu_pos] + closes_needed + html_part[fu_pos:]
        print(f"Added {d} missing </div> tag(s) before fu-view to close .main")
    elif d == 0:
        print(".main properly closes before fu-view")
    else:
        print(f"WARNING: depth is negative ({d}) — too many closes before fu-view")

# Remove extra empty lines
html_part = re.sub(r'\n{4,}', '\n\n', html_part)

# ─── JS CLEANUP AND FIXES ─────────────────────────────────────────────
js_lines = lines[first_let_line:]
js_part = '\n'.join(js_lines)

# Remove old injected render() additions (repeat to catch multiple copies)
# Use more targeted patterns that match the full block from comment to its final closing
for _ in range(3):
    # City display block: from "// City display" to the matching closing brace
    js_part = re.sub(r'\n\s*// City display\n\s*const cityEl=.*?cityEl\.style\.display=\'none\';\}', '', js_part, flags=re.DOTALL)
    # Source PPP display block
    js_part = re.sub(r'\n\s*// Source PPP display[^\n]*\n\s*const srcPppEl=.*?srcPppEl\.style\.display=\'none\';\}', '', js_part, flags=re.DOTALL)
    # Also-consider firm chips block (with PPP variant too)
    js_part = re.sub(r'\n\s*// Also-consider firm chips[^\n]*\n\s*const acRow=.*?acRow\.style\.display=\'none\';\}', '', js_part, flags=re.DOTALL)
    # Practice + bio hook display block
    js_part = re.sub(r'\n\s*// Practice \+ bio hook display[^\n]*\n\s*const practiceEl=.*?bioEl\.style\.display=\'none\';\}', '', js_part, flags=re.DOTALL)
# Clean orphaned closing fragments that may remain from VERY old injections
# Only match standalone orphan lines (not preceded by if/else on the same line)
js_part = re.sub(r'\n\s*\}else\{srcPppEl\.style\.display=\'none\';\}\s*\n', '\n', js_part)
js_part = re.sub(r'\n\s*\}else\{cityEl\.style\.display=\'none\';\}\s*\n', '\n', js_part)
# DO NOT clean acRow orphans — the newly injected code legitimately ends with that pattern

# ─── FIX sk() to use partner NAME instead of index ────────────────────
# Old: sk(t,i) => t+'_'+i  — breaks when data is rebuilt (indices shift)
# New: sk(t,i) => t+'_'+DS[t][i].name  — survives rebuilds
old_sk = "function sk(t,i){return t+'_'+i;}"
new_sk = "function sk(t,i){return t+'_'+(DS[t][i]?DS[t][i].name:i);}"
# Also handle the already-migrated version
already_new_sk = "function sk(t,i){return t+'_'+(DS[t][i]?DS[t][i].name:i);}"
if old_sk in js_part:
    js_part = js_part.replace(old_sk, new_sk)
    print("Changed sk() from index-based to name-based")
elif already_new_sk in js_part:
    print("sk() already name-based — no change needed")

# Remove any old migrateKeys block (it was broken — mapped wrong indices)
js_part = re.sub(r'\n*// Migrate old index-based status keys[^\n]*\n\(function migrateKeys\(\)\{.*?\}\)\(\);\n*', '\n', js_part, flags=re.DOTALL)

# Add a smarter migration that reconstructs status from the LOG (which has partner names)
migration_js = """
// Reconstruct status from log data (name-based, survives rebuilds)
(function reconstructStatus(){
  try{
    const raw=localStorage.getItem(SK);
    const old=raw?JSON.parse(raw):{};
    // Check if we have any name-based keys already (means migration already ran)
    const hasNameKeys=Object.keys(old).some(k=>/^(general|fox)_[A-Z]/.test(k));
    const hasIndexKeys=Object.keys(old).some(k=>/^(general|fox)_\\d+$/.test(k));
    if(!hasIndexKeys&&hasNameKeys)return; // Already migrated, nothing to do
    // Build fresh status from log (sent entries) and follow-up data
    const fresh={};
    // Preserve any existing name-based keys
    for(const[k,v] of Object.entries(old)){
      if(!/^(general|fox)_\\d+$/.test(k))fresh[k]=v;
    }
    // Reconstruct 'sent' from fuLog (the log has partner names)
    const logRaw=localStorage.getItem('ov6_log');
    if(logRaw){
      const log=JSON.parse(logRaw);
      const sentNames=new Set(log.map(e=>e.name));
      ['general','fox'].forEach(t=>{
        if(!DS[t])return;
        DS[t].forEach((p,i)=>{
          const key=t+'_'+p.name;
          if(sentNames.has(p.name)&&!fresh[key])fresh[key]='sent';
        });
      });
    }
    status=fresh;saveS();
  }catch(e){console.error('Migration error:',e);}
})();
"""
# Insert migration after loadS() — clean any old migration first
if 'reconstructStatus' not in js_part:
    js_part = js_part.replace('loadS();\n', 'loadS();\n' + migration_js)
    print("Added log-based status reconstruction")

# Fix applyFirmOverride
old_afo = re.search(r'function applyFirmOverride\(msg,p\)\{.*?(?=\nfunction )', js_part, re.DOTALL)
if old_afo:
    new_afo = """function applyFirmOverride(msg,p){
  if(!pitchOverride.firm1||!p)return msg;
  const oldF1=sfGlobal(p.target||'');
  const oldF2=sfGlobal(p.alt1||'');
  const newF1=sfGlobal(pitchOverride.firm1);
  const newF2=pitchOverride.firm2?sfGlobal(pitchOverride.firm2):'';
  let m=msg;
  if(oldF1&&newF1!==oldF1)m=m.split(oldF1).join(newF1);
  if(oldF2&&newF2&&newF2!==oldF2)m=m.split(oldF2).join(newF2);
  else if(oldF2&&!newF2)m=m.split(oldF2).join(newF1);
  if(newF1&&(!newF2||newF2===newF1)){
    m=m.replace(newF1+' and '+newF1,newF1);
    m=m.replace(/\\bboth\\b/g,'it').replace(/\\bare both\\b/g,'is').replace(/\\btheir\\b/g,'its').replace(/\\bsearches\\b/g,'search').replace(/\\bpractices\\b/g,'practice');
  }
  return m;
}"""
    js_part = js_part[:old_afo.start()] + new_afo + js_part[old_afo.end():]
    print("Replaced applyFirmOverride")

# ─── FIX buildQ() — push skipped/later to end in ALL views ────────────
old_buildQ = re.search(r'function buildQ\(\)\{.*?\n\}', js_part, re.DOTALL)
if old_buildQ:
    new_buildQ = """function buildQ(){
  const d=DS[tab];
  let idxs=d.map((_,i)=>i);
  // Sort by last_contact date, oldest first
  idxs.sort((a,b)=>parseLC(d[a].last_contact)-parseLC(d[b].last_contact));
  if(filter==='warm')idxs.sort((a,b)=>{const wa=(d[a].stage||'').toLowerCase().includes('warm'),wb=(d[b].stage||'').toLowerCase().includes('warm');return wa===wb?0:wa?-1:1;});
  if(filter==='pending'){
    idxs=idxs.filter(i=>status[sk(tab,i)]!=='sent');
    idxs.sort((a,b)=>{const sa=status[sk(tab,a)]||'',sb=status[sk(tab,b)]||'';const ra=(sa==='skipped'?2:sa==='later'?1:0),rb=(sb==='skipped'?2:sb==='later'?1:0);return ra-rb||parseLC(d[a].last_contact)-parseLC(d[b].last_contact);});
  } else {
    // ALL other views: also push skipped/later to end
    idxs.sort((a,b)=>{const sa=status[sk(tab,a)]||'',sb=status[sk(tab,b)]||'';const ra=(sa==='sent'?3:sa==='skipped'?2:sa==='later'?1:0),rb=(sb==='sent'?3:sb==='skipped'?2:sb==='later'?1:0);return ra-rb||parseLC(d[a].last_contact)-parseLC(d[b].last_contact);});
  }
  if(filter==='leader')idxs=idxs.filter(i=>isLeader(d[i]));
  if(dept&&tab==='fox')idxs=idxs.filter(i=>d[i].dept===dept);
  if(cityF&&tab==='fox')idxs=idxs.filter(i=>d[i].city===cityF);
  queue=idxs;qi=0;
}"""
    js_part = js_part[:old_buildQ.start()] + new_buildQ + js_part[old_buildQ.end():]
    print("Replaced buildQ with skipped/later sort for all views")

# ─── INJECT render() additions: city, src PPP, also-consider ──────────
city_js = """  // City display
  const cityEl=document.getElementById('p-city');
  if(p.city){cityEl.textContent=p.city;cityEl.style.display='';}else{cityEl.style.display='none';}
  // Source PPP display (current firm)
  const srcPppEl=document.getElementById('p-src-ppp');
  if(!isFox && p.firm){
    let srcPpp=0;
    for(const[k,v] of Object.entries(FIRM_PPP)){if(sfGlobal(k)===sfGlobal(p.firm)||k===p.firm){srcPpp=v;break;}}
    if(srcPpp){srcPppEl.textContent='PPP $'+(srcPpp/1e6).toFixed(1)+'M';srcPppEl.style.display='';}
    else{srcPppEl.style.display='none';}
  }else{srcPppEl.style.display='none';}
  // Practice + bio hook display
  const practiceEl=document.getElementById('p-practice');
  const bioEl=document.getElementById('p-bio-hook');
  if(p.practice){practiceEl.textContent=p.practice;practiceEl.style.display='';}else{practiceEl.style.display='none';}
  if(p.bio_hook){bioEl.textContent='— '+p.bio_hook;bioEl.style.display='';}else{bioEl.style.display='none';}
  // Also-consider firm chips (with PPP)
  const acRow=document.getElementById('also-consider');
  if(!isFox && (p.alt2||p.alt3)){
    acRow.style.display='';
    const c2=document.getElementById('chip-alt2');
    const c3=document.getElementById('chip-alt3');
    function chipPPP(firm){let pp=0;for(const[k,v] of Object.entries(FIRM_PPP)){if(sfGlobal(k)===sfGlobal(firm)||k===firm){pp=v;break;}}return pp?'<span class="chip-chambers">$'+(pp/1e6).toFixed(1)+'M</span>':'';}
    if(p.alt2){c2.style.display='';c2.innerHTML=sfGlobal(p.alt2)+chipPPP(p.alt2)+(p.alt2_chambers_label&&p.alt2_chambers_label!=='Not ranked'?'<span class="chip-chambers">'+p.alt2_chambers_label+'</span>':'');}else{c2.style.display='none';}
    if(p.alt3){c3.style.display='';c3.innerHTML=sfGlobal(p.alt3)+chipPPP(p.alt3)+(p.alt3_chambers_label&&p.alt3_chambers_label!=='Not ranked'?'<span class="chip-chambers">'+p.alt3_chambers_label+'</span>':'');}else{c3.style.display='none';}
  }else{acRow.style.display='none';}
"""

if '  if(!isFox&&p.last_contact)' in js_part:
    js_part = js_part.replace(
        '  if(!isFox&&p.last_contact)',
        city_js + '  if(!isFox&&p.last_contact)'
    )

# ─── REBUILD buildFirmTable with book size + city matching ─────────────
firm_table_js = """
// Populate firm comparison table — uses COLD_CALL_FIRMS for book size + city match
function buildFirmTable(p){
  const panel=document.getElementById('firm-table-panel');
  const tbody=document.getElementById('firm-table-body');
  if(!p||tab==='fox'){panel.style.display='none';return;}
  panel.style.display='';
  const myTargets=new Set([p.target,p.alt1,p.alt2,p.alt3].filter(Boolean));
  const myTargetsShort=new Set([...myTargets].map(f=>sfGlobal(f)));
  const pCity=p.city||'';
  // Build rows from COLD_CALL_FIRMS, filtered by partner's city
  const rows=[];
  const seen=new Set();
  for(const[firm,info] of Object.entries(COLD_CALL_FIRMS)){
    if(pCity && info.cities && info.cities.length>0 && !info.cities.includes(pCity))continue;
    const short=sfGlobal(firm);
    if(seen.has(short))continue;
    seen.add(short);
    // Look up PPP
    let ppp=FIRM_PPP[firm]||0;
    if(!ppp){for(const[k,v] of Object.entries(FIRM_PPP)){if(sfGlobal(k)===short){ppp=v;break;}}}
    const isTarget=myTargetsShort.has(short);
    const book=info.book||0;
    rows.push({firm,short,ppp,book,isTarget});
  }
  rows.sort((a,b)=>a.book-b.book||b.ppp-a.ppp);
  tbody.innerHTML=rows.map(r=>{
    const pppStr=r.ppp>=1e6?'$'+(r.ppp/1e6).toFixed(1)+'M':r.ppp>=1e3?'$'+Math.round(r.ppp/1e3)+'K':'';
    const bookStr=r.book?'$'+r.book+'M':'';
    const dot=r.isTarget?'<span class="ft-dot target" title="Matched to this partner"></span>':'';
    return '<tr><td class="ft-name" title="'+r.firm+'">'+r.short+'</td><td class="ft-ppp">'+pppStr+'</td><td class="ft-book">'+bookStr+'</td><td class="ft-match">'+dot+'</td></tr>';
  }).join('');
}

"""

quick_pitch_js = """
// Quick-pitch: click chip = replace firm1 (primary), shift+click = replace firm2 (secondary)
function quickPitch(which, evt){
  const c=cur();
  if(!c)return;
  const p=c.p;
  const firm=which==='alt2'?p.alt2:(which==='alt3'?p.alt3:'');
  if(!firm)return;
  const oldFirm1 = (pitchOverride && pitchOverride.firm1) || p.target;
  const oldFirm2 = (pitchOverride && pitchOverride.firm2) || p.alt1 || '';
  if(evt && evt.shiftKey){
    // Shift+click: replace firm2 (secondary)
    pitchOverride={firm1:oldFirm1, firm2:firm, reason:'Replaced '+sfGlobal(oldFirm2)+' with '+sfGlobal(firm)};
  } else {
    // Normal click: replace firm1 (primary)
    pitchOverride={firm1:firm, firm2:oldFirm2, reason:'Replaced '+sfGlobal(oldFirm1)+' with '+sfGlobal(firm)};
  }
  render();
}

"""

# Remove old buildFirmTable and quickPitch (all variants)
for _ in range(3):
    js_part = re.sub(r'\n*// Populate firm comparison table.*?function buildFirmTable\(p\)\{.*?\n\}\n*', '\n', js_part, flags=re.DOTALL)
    js_part = re.sub(r'\nfunction buildFirmTable\(p\)\{.*?\n\}\n', '\n', js_part, flags=re.DOTALL)
    js_part = re.sub(r'\n*// Quick-pitch:.*?function quickPitch\([^)]*\)\{.*?\n\}\n*', '\n', js_part, flags=re.DOTALL)
    js_part = re.sub(r'\nfunction quickPitch\([^)]*\)\{.*?\n\}\n', '\n', js_part, flags=re.DOTALL)
js_part = js_part.replace('\nfunction updateP()', firm_table_js + quick_pitch_js + 'function updateP()')

# ─── STRIP previously injected search/subSearch blocks (idempotent) ───────────
# Remove everything from const SUB_SEARCH_KW or let searchFirm up to the next
# top-level let/const/function that is NOT part of the search block
js_part = re.sub(
    r'\n(?:const SUB_SEARCH_KW\s*=\s*\{.*?\};\s*\n)?let searchFirm\s*=.*?(?=\nfunction setFilter|\nfunction setDept|\nlet pitchOverride|\nfunction updateP)',
    '\n',
    js_part, flags=re.DOTALL
)
# Also strip standalone SUB_SEARCH_KW block if searchFirm was stripped separately
js_part = re.sub(r'\nconst SUB_SEARCH_KW\s*=\s*\{.*?\};\s*\n', '\n', js_part, flags=re.DOTALL)

# ─── FIX switchTab() — don't hide .main (it contains fu-view & log-view) ─────
# Instead, hide/show individual children: card, firm-table-panel for outreach views
# and fu-view, log-view for special tabs
old_switchTab = re.search(r'function switchTab\(t\)\{.*?\n\}', js_part, re.DOTALL)
if old_switchTab:
    new_switchTab = """function switchTab(t){
  const isSpecial = t==='followups'||t==='log';
  const gm=document.getElementById('general-main');if(gm)gm.style.display=isSpecial?'none':'';
  const offRow=document.getElementById('offered-row');if(offRow&&isSpecial)offRow.style.display='none';
  document.querySelector('.topbar').style.display = isSpecial?'none':'';
  document.querySelector('.filter-bar').style.display = isSpecial?'none':'';
  document.getElementById('fu-view').style.display = t==='followups'?'flex':'none';
  document.getElementById('log-view').style.display = t==='log'?'flex':'none';
  // Update tab classes
  document.getElementById('tab-general').className='tab'+(t==='general'?' active':'');
  document.getElementById('tab-fox').className='tab fox-tab'+(t==='fox'?' active':'');
  document.getElementById('tab-followups').className='tab fu-tab'+(t==='followups'?' active':'');
  document.getElementById('tab-log').className='tab log-tab'+(t==='log'?' active':'');
  if(isSpecial){
    if(t==='followups'){fuBuildQ();renderFuTab();}
    else{renderLogTab();}
    return;
  }
  tab=t;
  const isFox=t==='fox';
  document.body.className=isFox?'view-fox':'';
  const foxEls=document.querySelectorAll('.fox-only');
  foxEls.forEach(el=>el.style.display=isFox?'':'none');
  const genEls=document.querySelectorAll('.gen-only');
  genEls.forEach(el=>el.style.display=isFox?'none':'');
  qi=0;buildQ();render();
}"""
    js_part = js_part[:old_switchTab.start()] + new_switchTab + js_part[old_switchTab.end():]
    print("Fixed switchTab to not hide .main")

# Call buildFirmTable in render()
if 'buildFirmTable(p)' not in js_part:
    js_part = js_part.replace(
        "updateP();document.getElementById('prog-text')",
        "buildFirmTable(p);\n  updateP();document.getElementById('prog-text')"
    )

# ─── FIX pitchOverride — render() must NOT reset it; use override in pitch display ──
# Remove pitchOverride={} from render() (it wipes chip overrides before they display)
js_part = js_part.replace(
    "  pitchOverride={};\n  const pr=document.getElementById('pitch-row')",
    "  const pr=document.getElementById('pitch-row')"
)
# Instead reset on prev/skip/later navigation
js_part = re.sub(
    r"const prev=\(\)=>\{if\(qi>0\)\{qi--;render\(\);\}\};",
    "const prev=()=>{if(qi>0){qi--;pitchOverride={};render();}};",
    js_part
)
# Add pitchOverride reset to skip/later only if not already present
if 'pitchOverride={};render' not in js_part.split('const skip')[1].split(';')[0:10].__repr__() if 'const skip' in js_part else True:
    pass
# Safer: just do a targeted replacement
js_part = re.sub(
    r"(const skip=\(\)=>\{[^}]*?)(?:pitchOverride=\{\};)*(render\(\);\};)",
    r"\1pitchOverride={};render();};",
    js_part
)
js_part = re.sub(
    r"(const later=\(\)=>\{[^}]*?)(?:pitchOverride=\{\};)*(render\(\);\};)",
    r"\1pitchOverride={};render();};",
    js_part
)
# Use pitchOverride-aware firm display in pitch row
old_pitch_display = """    const f1Label=(p.target_signed===false?'\\u26a0\\ufe0f ':'')+(p.target||'');
    const f2Label=p.alt1?(' + '+(p.alt1_signed===false?'\\u26a0\\ufe0f ':'')+p.alt1):'';
    document.getElementById('pitch-display').textContent=f1Label+f2Label;"""
new_pitch_display = """    const dispF1=pitchOverride.firm1||p.target||'';
    const dispF2=pitchOverride.firm2!==undefined?pitchOverride.firm2:(p.alt1||'');
    const f1Signed=pitchOverride.firm1?!NON_SIGNED.has(pitchOverride.firm1):(p.target_signed!==false);
    const f2Signed=pitchOverride.firm2?!NON_SIGNED.has(pitchOverride.firm2):(p.alt1_signed!==false);
    const f1Label=(!f1Signed?'\\u26a0\\ufe0f ':'')+sfGlobal(dispF1);
    const f2Label=dispF2?(' + '+(!f2Signed?'\\u26a0\\ufe0f ':'')+sfGlobal(dispF2)):'';
    document.getElementById('pitch-display').textContent=f1Label+f2Label;
    const poInd=document.getElementById('pitch-override-ind');
    if(poInd){if(pitchOverride.firm1||pitchOverride.firm2){poInd.textContent='(edited)';poInd.style.display='';}else{poInd.style.display='none';}}"""
if old_pitch_display in js_part:
    js_part = js_part.replace(old_pitch_display, new_pitch_display)
    print("Updated pitch display to use pitchOverride")

# ─── CSS OVERRIDES for card redesign ─────────────────────────────────────────

# ─── DATA INJECTION ───────────────────────────────────────────────────
firm_aliases_js = {
    'latham & watkins': 'Latham', 'kirkland & ellis': 'Kirkland',
    'skadden, arps, slate, meagher & flom': 'Skadden',
    'simpson thacher & bartlett': 'Simpson Thacher', 'davis polk & wardwell': 'Davis Polk',
    'cleary gottlieb steen & hamilton': 'Cleary', 'cleary gottlieb': 'Cleary',
    'wilmerhale': 'WilmerHale', 'quinn emanuel urquhart & sullivan': 'Quinn Emanuel',
    'weil, gotshal & manges': 'Weil', 'weil gotshal & manges': 'Weil',
    'gibson, dunn & crutcher': 'Gibson Dunn', 'gibson dunn & crutcher': 'Gibson Dunn',
    "o'melveny & myers": "O'Melveny",
    'paul, weiss, rifkind, wharton & garrison': 'Paul Weiss',
    'willkie farr & gallagher': 'Willkie Farr', 'debevoise & plimpton': 'Debevoise',
    'cahill gordon & reindel': 'Cahill', 'norton rose fulbright': 'Norton Rose',
    'morgan, lewis & bockius': 'Morgan Lewis', 'morgan lewis & bockius': 'Morgan Lewis',
    'faegre drinker biddle & reath': 'Faegre Drinker', 'arentfox schiff': 'ArentFox',
    'mcdermott will & emery': 'McDermott', 'mcdermott will & schulte': 'McDermott',
    'sidley austin': 'Sidley',
    'fried, frank, harris, shriver & jacobson': 'Fried Frank',
    'sullivan & cromwell': 'Sullivan & Cromwell', 'cravath, swaine & moore': 'Cravath',
    'king & spalding': 'King & Spalding', 'ropes & gray': 'Ropes & Gray',
    'white & case': 'White & Case',
    'akin, gump, strauss, hauer & feld': 'Akin Gump', 'akin gump': 'Akin Gump',
    'alston & bird': 'Alston & Bird',
    'morrison & foerster': 'MoFo', 'orrick, herrington & sutcliffe': 'Orrick',
    'proskauer rose': 'Proskauer', 'vinson & elkins': 'V&E',
    'dorsey & whitney': 'Dorsey', 'holland & knight': 'Holland & Knight',
    'troutman pepper locke': 'Troutman', 'troutman pepper': 'Troutman',
    'arnold & porter kaye scholer': 'Arnold & Porter', 'arnold & porter': 'Arnold & Porter',
    'pillsbury winthrop shaw pittman': 'Pillsbury',
    'sheppard, mullin, richter & hampton': 'Sheppard Mullin', 'sheppard mullin': 'Sheppard Mullin',
    'fenwick & west': 'Fenwick', 'wilson sonsini goodrich & rosati': 'Wilson Sonsini',
    'haynes and boone': 'Haynes Boone',
    'cadwalader, wickersham & taft': 'Cadwalader',
    'boies, schiller & flexner': 'Boies Schiller',
    'jenner & block': 'Jenner & Block', 'crowell & moring': 'Crowell & Moring',
    'steptoe': 'Steptoe', 'winston & strawn': 'Winston & Strawn',
    'mayer brown': 'Mayer Brown', 'foley & lardner': 'Foley & Lardner',
    'katten muchin rosenman': 'Katten', 'goodwin procter': 'Goodwin', 'goodwin': 'Goodwin',
    'dla piper': 'DLA Piper', 'herbert smith freehills kramer': 'Kramer Levin',
    'lowenstein sandler': 'Lowenstein',
    'mintz, levin, cohn, ferris, glovsky and popeo': 'Mintz', 'mintz levin': 'Mintz',
    'patterson belknap webb & tyler': 'Patterson Belknap',
    'perkins coie': 'Perkins Coie', 'paul hastings': 'Paul Hastings',
    'dechert': 'Dechert', 'cooley': 'Cooley', 'milbank': 'Milbank',
    'wachtell, lipton, rosen & katz': 'Wachtell',
    'susman godfrey': 'Susman Godfrey', 'quinn emanuel': 'Quinn Emanuel',
    'davis wright tremaine': 'Davis Wright', 'blank rome': 'Blank Rome',
    'ballard spahr': 'Ballard Spahr', 'polsinelli': 'Polsinelli',
    'baker botts': 'Baker Botts', 'baker mckenzie': 'Baker McKenzie',
    'baker & hostetler': 'BakerHostetler', 'jones day': 'Jones Day',
    'covington & burling': 'Covington',
}

non_signed_firms = [
    "Akin, Gump, Strauss, Hauer & Feld, LLP", "Alston & Bird LLP",
    "Cravath, Swaine & Moore LLP", "Fried, Frank, Harris, Shriver & Jacobson LLP",
    "King & Spalding LLP", "Kirkland & Ellis LLP", "Morrison & Foerster LLP",
    "O'Melveny & Myers LLP", "Orrick, Herrington & Sutcliffe LLP",
    "Paul, Weiss, Rifkind, Wharton & Garrison LLP", "Ropes & Gray LLP",
    "Skadden, Arps, Slate, Meagher & Flom LLP", "White & Case LLP",
    "Willkie Farr & Gallagher LLP", "Wilson Sonsini Goodrich & Rosati"
]

# Update tab badge counts in the HTML to reflect actual data
html_part = re.sub(
    r"(id=\"tab-general\"[^>]*>General Outreach\s*<span class=\"tab-badge\">)\d+(</span>)",
    rf"\g<1>{len(general)}\2",
    html_part
)
html_part = re.sub(
    r"(id=\"tab-fox\"[^>]*>Fox Rothschild\s*<span class=\"tab-badge\">)\d+(</span>)",
    rf"\g<1>{len(fox)}\2",
    html_part
)
print(f"Updated tab badges: General={len(general)}, Fox={len(fox)}")

ds_obj = {"general": general, "fox": fox}

data_block = f"""const NON_SIGNED=new Set({json.dumps(non_signed_firms)});
const FIRM_ALIASES_JS={json.dumps(firm_aliases_js, ensure_ascii=False)};
const FIRM_PPP={json.dumps(firm_ppp, ensure_ascii=False)};
const COLD_CALL_FIRMS={json.dumps(cold_call_firms, ensure_ascii=False)};
function chambersBadge(label){{if(!label||label==='Not ranked')return'<span class="chambers-badge cb-nr">NR</span>';const n=parseInt(label.replace('Band ',''));const cls=['','cb-b1','cb-b2','cb-b3','cb-b4','cb-b5'][n]||'cb-nr';return'<span class="chambers-badge '+cls+'">B'+n+'</span>';}}
function sfGlobal(n){{if(!n)return'';const key=n.replace(/\\s*(LLP|LLC|PC|PLLC|PA|LP|Ltd|P\\.C\\.|P\\.A\\.)\\s*$/i,'').replace(/,\\s*$/,'').trim().toLowerCase().replace(/\\s+/g,' ');if(FIRM_ALIASES_JS[key])return FIRM_ALIASES_JS[key];const keyNoComma=key.replace(/,/g,'');for(const[k,v] of Object.entries(FIRM_ALIASES_JS)){{if(keyNoComma===k.replace(/,/g,''))return v;}}return n.replace(/\\b(LLP|LLC|PC|PLLC|PA|LP)\\b/gi,'').replace(/,\\s*$/,'').trim().split(/\\s+/).slice(0,3).join(' ');}}
const DS={json.dumps(ds_obj, ensure_ascii=False)};
"""

# ─── ASSEMBLE FINAL HTML ──────────────────────────────────────────────
final = html_part + '\n' + data_block + js_part

with open('/sessions/dreamy-ecstatic-heisenberg/mnt/outputs/Outreach.html', 'w') as f:
    f.write(final)

# ─── APPLY LIGHT THEME + FIRM SEARCH TABS ──────────────────────────────
import subprocess
result = subprocess.run(['python3', '/sessions/dreamy-ecstatic-heisenberg/patch_light_and_searches.py'],
                       capture_output=True, text=True)
print("Light theme + search tabs patch:")
print(result.stdout)
if result.stderr:
    print("ERRORS:", result.stderr)

# ─── POST-PATCH: inject all persistent fixes ──────────────────────────
with open('/sessions/dreamy-ecstatic-heisenberg/mnt/outputs/Outreach.html') as f:
    post = f.read()

# 1. Add id="general-main" to the .main div
post = post.replace(
    '<div class="main" style="gap:16px;flex-wrap:nowrap;justify-content:center;align-items:flex-start;">',
    '<div class="main" id="general-main" style="gap:16px;flex-wrap:nowrap;justify-content:center;align-items:flex-start;">'
)

# 2. Add offered-row HTML after #general-main closing tag, before fu-view
if 'id="offered-row"' not in post:
    post = post.replace(
        '</div>\n<div class="fu-view" id="fu-view">',
        '</div>\n<div id="offered-row" style="display:none;padding:6px 20px;background:#fff;border-top:1px solid #e0e4ec;">'
        '\n  <input id="offered-text" readonly onclick="this.select()" title="Click to select · Ctrl+C to copy"'
        ' style="width:360px;max-width:100%;background:#f5f7fa;border:1px solid #d0d5e0;border-radius:5px;padding:5px 10px;font-size:12px;color:#333;cursor:text;font-family:inherit;" />'
        '\n</div>\n<div class="fu-view" id="fu-view">',
        1
    )

# 3. PPP in pitch display (upgrade textContent → innerHTML with pitchPPP helper)
old_pd = """    const f1Label=(!f1Signed?'\\u26a0\\ufe0f ':'')+sfGlobal(dispF1);
    const f2Label=dispF2?(' + '+(!f2Signed?'\\u26a0\\ufe0f ':'')+sfGlobal(dispF2)):'';
    document.getElementById('pitch-display').textContent=f1Label+f2Label;"""
new_pd = """    function pitchPPP(firm){let pp=0;for(const[k,v] of Object.entries(FIRM_PPP)){if(sfGlobal(k)===sfGlobal(firm)||k===firm){pp=v;break;}}return pp?' <span style="font-size:11px;color:#e67e22;font-weight:700">$'+(pp/1e6).toFixed(1)+'M</span>':'';}
    const f1Label=(!f1Signed?'\\u26a0\\ufe0f ':'')+sfGlobal(dispF1)+pitchPPP(dispF1);
    const f2Label=dispF2?(' + '+(!f2Signed?'\\u26a0\\ufe0f ':'')+sfGlobal(dispF2)+pitchPPP(dispF2)):'';
    document.getElementById('pitch-display').innerHTML=f1Label+f2Label;
    // Update offered field
    const offRow=document.getElementById('offered-row');
    const offTxt=document.getElementById('offered-text');
    if(offRow&&offTxt&&!isFox&&dispF1){offTxt.value='Offered '+sfGlobal(dispF1)+(dispF2?' + '+sfGlobal(dispF2):'');offRow.style.display='block';}
    else if(offRow){offRow.style.display='none';}"""
if old_pd in post:
    post = post.replace(old_pd, new_pd)
    print("Injected pitchPPP + offered field update")

# 4. tableSwapFirm + doSwap — replace shift-click with popup
old_tsf_start = 'function tableSwapFirm(firm,evt){'
if old_tsf_start not in post:
    # inject after copyMsg
    table_swap_js = """
function tableSwapFirm(firm,evt){
  const c=cur();if(!c)return;
  const p=c.p;
  const oldF1=sfGlobal((pitchOverride&&pitchOverride.firm1)||p.target||'');
  const oldF2=sfGlobal((pitchOverride&&pitchOverride.firm2)!==undefined?(pitchOverride.firm2):(p.alt1||''));
  let pop=document.getElementById('swap-popup');
  if(!pop){pop=document.createElement('div');pop.id='swap-popup';pop.style.cssText='position:fixed;z-index:9999;background:#fff;border:1px solid #ccc;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.18);padding:10px 12px;font-size:12px;min-width:160px;';document.body.appendChild(pop);}
  pop.innerHTML='<div style="font-weight:700;margin-bottom:8px;color:#333">Swap <em>'+sfGlobal(firm)+'</em> as:</div>'
    +'<button onclick="doSwap(\\'f1\\',\\''+firm.replace(/\\'/g,"\\\\'")+'\\')" style="display:block;width:100%;text-align:left;padding:5px 8px;margin-bottom:4px;border:1px solid #4f8ef7;border-radius:5px;background:#eef3ff;color:#1a4bb8;cursor:pointer;font-size:12px;">F1 — replacing <b>'+oldF1+'</b></button>'
    +'<button onclick="doSwap(\\'f2\\',\\''+firm.replace(/\\'/g,"\\\\'")+'\\')" style="display:block;width:100%;text-align:left;padding:5px 8px;border:1px solid #aaa;border-radius:5px;background:#f5f5f5;color:#444;cursor:pointer;font-size:12px;">F2 — replacing <b>'+oldF2+'</b></button>';
  const x=evt.clientX,y=evt.clientY;
  pop.style.left=(x+8)+'px';pop.style.top=(y-10)+'px';pop.style.display='block';
  setTimeout(()=>document.addEventListener('click',function h(){pop.style.display='none';document.removeEventListener('click',h);},{once:true}),10);
}
function doSwap(slot,firm){
  const c=cur();if(!c)return;
  const p=c.p;
  const oldF1=(pitchOverride&&pitchOverride.firm1)||p.target||'';
  const oldF2=(pitchOverride&&pitchOverride.firm2)!==undefined?(pitchOverride.firm2):(p.alt1||'');
  if(slot==='f2'){pitchOverride={firm1:oldF1,firm2:firm,reason:'Replaced '+sfGlobal(oldF2)+' with '+sfGlobal(firm)};}
  else{pitchOverride={firm1:firm,firm2:oldF2,reason:'Replaced '+sfGlobal(oldF1)+' with '+sfGlobal(firm)};}
  render();
}"""
    post = post.replace(
        'function copyMsg(){',
        table_swap_js + '\nfunction copyMsg(){'
    )
    print("Injected tableSwapFirm + doSwap")

# 5. Make firm table rows call tableSwapFirm
post = post.replace(
    "title=\"Click = pitch as F1  ·  Shift+click = pitch as F2\"",
    "title=\"Click to swap into pitch\""
)

# 6. Firebase SDK block — restore SDK (WebSocket) approach that bypasses CORS
import re as _re
# Ensure SDK script tags are present before </style> close comment or <body>
FB_SDK_TAGS = '<script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js"></script>\n<script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-database-compat.js"></script>\n'
# Remove any old SDK tags or "removed" comment first (idempotent)
post = _re.sub(r'<script src="https://www\.gstatic\.com/firebasejs[^"]*"></script>\n?', '', post)
post = post.replace('<!-- Firebase SDK removed — using REST API instead (no CDN dependency) -->\n', '')
# Inject SDK tags just before <body>
if FB_SDK_TAGS.strip() not in post:
    post = post.replace('<body>', FB_SDK_TAGS + '<body>', 1)

firebase_rest_block = """// ── Firebase SDK sync (WebSocket — bypasses all CORS restrictions) ────────
const FB_CONFIG={apiKey:"AIzaSyBBGbuBdtCwYa8v7J9-iG7UtZQ05exGtAk",authDomain:"partner-outreach-ebb5e.firebaseapp.com",databaseURL:"https://partner-outreach-ebb5e-default-rtdb.firebaseio.com",projectId:"partner-outreach-ebb5e"};
let _fbApp=null,_fbDb=null,_fbRef=null,_fbInitialized=false,_fbSaveDebounce=null;
function updateFbStatus(s,msg){const el=document.getElementById('fb-status');if(!el)return;if(s==='synced'){el.innerHTML='✓ Saved to cloud';el.style.cssText='font-size:10px;padding:4px 11px;border-radius:6px;border:1px solid #27ae60;background:#eafaf1;color:#1e8449;font-weight:600;white-space:nowrap;';}else if(s==='saving'){el.innerHTML='↑ Saving...';el.style.cssText='font-size:10px;padding:4px 11px;border-radius:6px;border:1px solid #e8d080;background:#fff0e0;color:#b8860b;font-weight:600;white-space:nowrap;';}else if(s==='error'){el.innerHTML='⚠ Sync error <u style="cursor:pointer;margin-left:4px" onclick="initFirebase()" title="'+(msg||'').replace(/"/g,"'")+'">retry</u>';el.style.cssText='font-size:10px;padding:4px 11px;border-radius:6px;border:1px solid #e74c3c;background:#fde8e8;color:#c0392b;font-weight:600;white-space:nowrap;';if(msg)console.error('[FB sync]',msg);}else{el.innerHTML='⏳ Connecting...';el.style.cssText='font-size:10px;padding:4px 11px;border-radius:6px;border:1px solid #e8d080;background:#fff0e0;color:#b8860b;font-weight:600;white-space:nowrap;';}}
function initFirebase(){if(typeof firebase==='undefined'){setTimeout(initFirebase,500);return;}updateFbStatus('connecting');try{_fbApp=(firebase.apps&&firebase.apps.length)?firebase.app():firebase.initializeApp(FB_CONFIG);_fbDb=firebase.database(_fbApp);_fbRef=_fbDb.ref('outreach');_fbRef.once('value').then(function(snap){const data=snap.val();if(data){if(data.status){status=data.status;try{localStorage.setItem(SK,JSON.stringify(status));}catch(e){}}if(data.fuLog){fuLog=data.fuLog;try{localStorage.setItem(LOG_SK,JSON.stringify(fuLog));}catch(e){}}if(data.fuData){fuData=data.fuData;try{localStorage.setItem(FU_SK,JSON.stringify(fuData));}catch(e){}}}_fbInitialized=true;updateFbStatus('synced');buildQ();render();updateFuBadge();const fuV=document.getElementById('fu-view');const logV=document.getElementById('log-view');if(fuV&&fuV.style.display!=='none'){fuBuildQ();renderFuTab();}else if(logV&&logV.style.display!=='none'){renderLogTab();}}).catch(function(e){_fbInitialized=true;updateFbStatus('error',e&&e.message?e.message:String(e));});}catch(e){_fbInitialized=true;updateFbStatus('error',e&&e.message?e.message:String(e));}}
function fbSaveNow(){if(!_fbInitialized||!_fbRef)return;const data={status:status||{},fuLog:(typeof fuLog!=='undefined'?fuLog:[])||[],fuData:(typeof fuData!=='undefined'?fuData:{})||{},lastSaved:new Date().toISOString(),version:'v5e'};_fbRef.set(data).then(function(){updateFbStatus('synced');}).catch(function(e){updateFbStatus('error',e&&e.message?e.message:String(e));});}
function scheduleFbSave(){if(!_fbInitialized)return;updateFbStatus('saving');clearTimeout(_fbSaveDebounce);_fbSaveDebounce=setTimeout(fbSaveNow,1200);}
setTimeout(initFirebase,300);
"""

# Strip any old Firebase block (JSONP, REST, or SDK variant) and inject new
post = _re.sub(r'// ── Firebase(?:.*?)\nsetTimeout\(initFirebase,\d+\);\n', firebase_rest_block, post, flags=_re.DOTALL)
if 'initFirebase' not in post:
    post = post.replace('function autoBackup()', firebase_rest_block + 'function autoBackup()')
print("Firebase SDK block applied")

# 7. savePitchEdit — update offered field on manual firm edit
old_spe = "  document.getElementById('pitch-edit-row').classList.remove('open');"
new_spe = """  // Update offered field
  const _offR=document.getElementById('offered-row');const _offT=document.getElementById('offered-text');
  if(_offR&&_offT&&f1){_offT.value='Offered '+f1+(f2?' + '+f2:'');_offR.style.display='block';}
  document.getElementById('pitch-edit-row').classList.remove('open');"""
if old_spe in post and '_offR' not in post:
    post = post.replace(old_spe, new_spe, 1)
    print("Patched savePitchEdit offered field")

# 8. copyOffered function
if 'function copyOffered' not in post:
    post = post.replace(
        'function copyMsg(){',
        'function copyOffered(){const t=document.getElementById("offered-text");if(!t||!t.value)return;navigator.clipboard.writeText(t.value);}\n'
        + 'function copyMsg(){'
    )

# 9. Core card-action functions — next/prev/skip/later/copyMsg/openLI/openFP
# These are MANDATORY. Without them, all dashboard buttons are broken.
core_actions = """function next(){
  const c=cur();if(!c)return;
  status[sk(tab,c.i)]='sent';saveS();
  const p=c.p;const k=fuKey(p);
  const today=todayStr();
  fuData[k]={name:p.name,firm:p.firm,city:p.city||'',target:p.target||'',alt1:p.alt1||'',sentDate:today,nextDate:addDays(today,8),stage:1,practice:p.practice||''};
  saveFu();
  fuLog.push({date:today,name:p.name,firm:p.firm,city:p.city||'',target:p.target||'',alt1:p.alt1||'',action:'sent'});
  try{localStorage.setItem(LOG_SK,JSON.stringify(fuLog));}catch(e){}
  scheduleFbSave();
  qi++;if(qi>=queue.length)qi=0;
  altIdx=0;
  buildQ();render();updateP();updateFuBadge();
}
function prev(){qi--;if(qi<0)qi=queue.length-1;altIdx=0;render();}
function skip(){
  const c=cur();if(!c)return;
  status[sk(tab,c.i)]='skip';saveS();scheduleFbSave();
  qi++;if(qi>=queue.length)qi=0;altIdx=0;buildQ();render();updateP();
}
function later(){
  const c=cur();if(!c)return;
  status[sk(tab,c.i)]='later';saveS();scheduleFbSave();
  qi++;if(qi>=queue.length)qi=0;altIdx=0;buildQ();render();updateP();
}
function copyMsg(){
  const el=document.getElementById('p-msg');if(!el)return;
  navigator.clipboard.writeText(el.textContent).then(()=>showToast('Copied!')).catch(()=>{});
}
function openLI(){const c=cur();if(c&&c.p.linkedin)window.open(c.p.linkedin,'_blank');}
function openFP(){const c=cur();if(c&&c.p.fp)window.open(c.p.fp,'_blank');}
"""
if 'function next()' not in post:
    post = post.replace("document.addEventListener('keydown'", core_actions + "document.addEventListener('keydown'")
    print("Injected core card-action functions (next/prev/skip/later/copyMsg/openLI/openFP)")
else:
    print("Core card-action functions already present")

with open('/sessions/dreamy-ecstatic-heisenberg/mnt/outputs/Outreach.html', 'w') as f:
    f.write(post)
# Also save to Downloads so it persists between sessions and deploy task can find it
import shutil as _shutil
_dl_path = '/sessions/dreamy-ecstatic-heisenberg/mnt/Downloads/Outreach.html'
try:
    with open(_dl_path, 'w') as f:
        f.write(post)
    print(f"Saved to {_dl_path}")
except:
    # Try home directory paths (for scheduled task context)
    for alt in [os.path.expanduser('~/Downloads/Outreach.html'), '/Downloads/Outreach.html']:
        try:
            with open(alt, 'w') as f:
                f.write(post)
            print(f"Saved to {alt}")
            break
        except:
            pass
print("Post-patch complete")

# Re-read for verification
with open('/sessions/dreamy-ecstatic-heisenberg/mnt/outputs/Outreach.html') as f:
    final = f.read()

# ─── VERIFY ────────────────────────────────────────────────────────────
check_lines = final.split('\n')
print(f"\nTotal lines: {len(check_lines)}")
print(f"function sfGlobal: {final.count('function sfGlobal')}")
print(f"function buildFirmTable: {final.count('function buildFirmTable')}")
print(f"function applyFirmOverride: {final.count('function applyFirmOverride')}")
print(f"function buildQ: {final.count('function buildQ')}")
print(f"function quickPitch: {final.count('function quickPitch')}")
print(f"COLD_CALL_FIRMS: {final.count('COLD_CALL_FIRMS')}")
print(f"p-src-ppp: {final.count('p-src-ppp')}")
print(f"p-practice: {final.count('p-practice')}")
print(f"p-bio-hook: {final.count('p-bio-hook')}")
print(f"General partners: {len(general)}, Fox partners: {len(fox)}")
print(f"\nDone!")
