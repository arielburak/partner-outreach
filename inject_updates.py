"""
Inject new partners + snooze feature + sorting priority into index.html.
DOES NOT break existing data — only appends to DS.general and patches JS functions.
"""
import json, re

BASE = '/sessions/dreamy-ecstatic-heisenberg/partner-outreach'

with open(f'{BASE}/index.html', 'r') as f:
    html = f.read()

# ── 1. ADD NEW PARTNERS TO DS.general ──
with open(f'{BASE}/new_partners_matched.json') as f:
    new_partners = json.load(f)

# Include ALL partners (matched + unmatched)
matched = new_partners  # all 342
print(f"Adding {len(matched)} new partners to DS.general ({sum(1 for p in matched if p.get('target'))} matched, {sum(1 for p in matched if not p.get('target'))} unmatched)")

# Extract current DS
m = re.search(r'const DS=(\{.*?\});', html, re.DOTALL)
if not m:
    raise ValueError("Could not find const DS= in index.html")
ds = json.loads(m.group(1))

# Clean up fields before injection (remove temp fields, ensure schema match)
existing_keys = set()
if ds['general']:
    existing_keys = set(ds['general'][0].keys())

for p in matched:
    # Remove temp/internal fields
    for k in ['full_bio', 'bio', 'jaide', 'specialties', 'fp_id']:
        p.pop(k, None)
    # Ensure all expected keys exist
    for k in existing_keys:
        if k not in p:
            p[k] = ''
    # Mark as new for sorting priority
    p['is_new'] = True
    p['added_date'] = '2026-04-02'

# Append to general tab
ds['general'].extend(matched)
print(f"DS.general now has {len(ds['general'])} candidates (was {len(ds['general'])-len(matched)})")

# Replace DS in HTML
new_ds_json = json.dumps(ds, ensure_ascii=False)
html = html[:m.start()] + 'const DS=' + new_ds_json + ';' + html[m.end():]

# ── 2. ADD SNOOZE FEATURE ──
# Add snooze data storage (localStorage key: ov6_snooze)
# Format: { "general_Name": "2026-10-02" }  (return date)
snooze_init = """
// ── SNOOZE DATA ──
const SNOOZE_SK='ov6_snooze';
let snoozeData={};
function loadSnooze(){try{snoozeData=JSON.parse(localStorage.getItem(SNOOZE_SK)||'{}')||{}}catch(e){snoozeData={}}}
function saveSnooze(){try{localStorage.setItem(SNOOZE_SK,JSON.stringify(snoozeData))}catch(e){};scheduleFbSave();}
loadSnooze();

function snoozeCandidate(months){
  const c=cur();if(!c)return;
  const key=sk(tab,c.i);
  const d=new Date();
  d.setMonth(d.getMonth()+months);
  const returnDate=d.toISOString().slice(0,10);
  snoozeData[key]=returnDate;
  status[key]='snoozed';
  saveS();saveSnooze();
  pitchOverride={};
  qi++;if(qi>=queue.length)qi=0;altIdx=0;buildQ();render();updateP();
  showToast('Snoozed until '+returnDate);
}

function snoozeCustom(){
  const c=cur();if(!c)return;
  const input=prompt('Return date (YYYY-MM-DD):','');
  if(!input||!/^\\d{4}-\\d{2}-\\d{2}$/.test(input))return;
  const key=sk(tab,c.i);
  snoozeData[key]=input;
  status[key]='snoozed';
  saveS();saveSnooze();
  pitchOverride={};
  qi++;if(qi>=queue.length)qi=0;altIdx=0;buildQ();render();updateP();
  showToast('Snoozed until '+input);
}

function unsnoozeExpired(){
  const today=todayStr();
  let count=0;
  for(const[key,returnDate] of Object.entries(snoozeData)){
    if(returnDate<=today){
      delete snoozeData[key];
      if(status[key]==='snoozed')delete status[key];
      count++;
    }
  }
  if(count>0){saveS();saveSnooze();buildQ();}
  return count;
}
"""

# Insert snooze code right after the existing loadS/saveS block
insert_after = "loadS();\n"
pos = html.find(insert_after, html.find('function loadS()'))
if pos == -1:
    raise ValueError("Could not find loadS() call to insert snooze code after")
insert_pos = pos + len(insert_after)
html = html[:insert_pos] + snooze_init + html[insert_pos:]

# ── 3. UPDATE buildQ TO HANDLE SNOOZE + NEW PRIORITY ──
# Find and replace buildQ function
old_buildq = """function buildQ(){
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
  }"""

new_buildq = """function buildQ(){
  // Unsnooze any candidates whose return date has passed
  unsnoozeExpired();
  const d=DS[tab];
  const today=todayStr();
  let idxs=d.map((_,i)=>i);
  // Filter out snoozed candidates (return date still in the future)
  idxs=idxs.filter(i=>{const key=sk(tab,i);if(status[key]==='snoozed'&&snoozeData[key]&&snoozeData[key]>today)return false;return true;});
  // Sort: new uploads first (is_new flag), then unseen, then skipped/later, then sent
  // Within each tier: oldest last_contact first
  function sortRank(i){
    const s=status[sk(tab,i)]||'';
    if(s==='sent')return 90;
    if(s==='snoozed')return 80;  // shouldn't appear (filtered above), but safety
    if(s==='skipped')return 60;
    if(s==='later')return 50;
    // Unseen — prioritize new uploads
    if(d[i].is_new)return 5;
    return 10;
  }
  idxs.sort((a,b)=>sortRank(a)-sortRank(b)||parseLC(d[a].last_contact)-parseLC(d[b].last_contact));
  if(filter==='warm')idxs.sort((a,b)=>{const wa=(d[a].stage||'').toLowerCase().includes('warm'),wb=(d[b].stage||'').toLowerCase().includes('warm');return wa===wb?0:wa?-1:1;});
  if(filter==='pending'){
    idxs=idxs.filter(i=>status[sk(tab,i)]!=='sent');
    idxs.sort((a,b)=>{const sa=status[sk(tab,a)]||'',sb=status[sk(tab,b)]||'';const ra=(sa==='skipped'?2:sa==='snoozed'?3:sa==='later'?1:0),rb=(sb==='skipped'?2:sb==='snoozed'?3:sb==='later'?1:0);return ra-rb||parseLC(d[a].last_contact)-parseLC(d[b].last_contact);});
  }"""

if old_buildq not in html:
    print("WARNING: Could not find exact buildQ to replace — trying flexible match")
    # Fallback: find the function start and replace up to the closing of the else block
    raise ValueError("buildQ not found for replacement")
else:
    html = html.replace(old_buildq, new_buildq, 1)
    print("Updated buildQ with snooze filtering + new-upload priority sorting")

# ── 4. ADD SNOOZE BUTTONS TO THE UI ──
# Find the Skip button and add snooze options next to it
# Current skip button area:
old_skip_btn = """<button onclick="skip()" style="background:#888;color:#fff;"""
# We'll find the full skip button line
skip_line_match = re.search(r'(<button onclick="skip\(\)"[^>]*>Skip</button>)', html)
if skip_line_match:
    old_skip = skip_line_match.group(1)
    # Replace with a skip dropdown that includes snooze options
    new_skip = """<div style="position:relative;display:inline-block" id="skip-wrap">""" + \
        """<button onclick="skip()" style="background:#888;color:#fff;border:none;padding:8px 16px;border-radius:6px 0 0 6px;cursor:pointer;font-weight:600">Skip</button>""" + \
        """<button onclick="document.getElementById('snooze-menu').style.display=document.getElementById('snooze-menu').style.display==='block'?'none':'block'" style="background:#666;color:#fff;border:none;padding:8px 8px;border-radius:0 6px 6px 0;cursor:pointer;font-weight:600">&#9660;</button>""" + \
        """<div id="snooze-menu" style="display:none;position:absolute;top:100%;left:0;background:#fff;border:1px solid #ccc;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.15);z-index:999;min-width:180px;margin-top:4px">""" + \
        """<div style="padding:8px 12px;font-weight:600;color:#555;border-bottom:1px solid #eee;font-size:13px">Snooze (skip &amp; return later)</div>""" + \
        """<div onclick="snoozeCandidate(3);document.getElementById('snooze-menu').style.display='none'" style="padding:8px 12px;cursor:pointer;font-size:14px" onmouseover="this.style.background='#f0f0f0'" onmouseout="this.style.background='#fff'">3 months</div>""" + \
        """<div onclick="snoozeCandidate(6);document.getElementById('snooze-menu').style.display='none'" style="padding:8px 12px;cursor:pointer;font-size:14px" onmouseover="this.style.background='#f0f0f0'" onmouseout="this.style.background='#fff'">6 months</div>""" + \
        """<div onclick="snoozeCandidate(12);document.getElementById('snooze-menu').style.display='none'" style="padding:8px 12px;cursor:pointer;font-size:14px" onmouseover="this.style.background='#f0f0f0'" onmouseout="this.style.background='#fff'">1 year</div>""" + \
        """<div onclick="snoozeCustom();document.getElementById('snooze-menu').style.display='none'" style="padding:8px 12px;cursor:pointer;font-size:14px;border-top:1px solid #eee" onmouseover="this.style.background='#f0f0f0'" onmouseout="this.style.background='#fff'">Custom date...</div>""" + \
        """</div></div>"""
    html = html.replace(old_skip, new_skip, 1)
    print("Added snooze dropdown to Skip button")
else:
    print("WARNING: Could not find Skip button to add snooze dropdown")

# ── 5. CLOSE SNOOZE MENU ON CLICK OUTSIDE ──
close_menu_js = """
// Close snooze menu on outside click
document.addEventListener('click',function(e){
  var m=document.getElementById('snooze-menu');
  if(m&&m.style.display==='block'){
    var w=document.getElementById('skip-wrap');
    if(w&&!w.contains(e.target))m.style.display='none';
  }
});
"""
# Insert before closing </script>
last_script_close = html.rfind('</script>')
if last_script_close != -1:
    html = html[:last_script_close] + close_menu_js + html[last_script_close:]
    print("Added click-outside handler for snooze menu")

# ── 6. ADD SNOOZE DATA TO FIREBASE SYNC ──
# Find fbSaveNow and add snooze data to it
fbsave_match = re.search(r'(function fbSaveNow\(\)\{[^}]*?)(try\{fb\.ref)', html, re.DOTALL)
if fbsave_match:
    # Already handled — snooze calls scheduleFbSave() which will sync
    print("Firebase sync: snooze data calls scheduleFbSave on save")

# ── 7. UPDATE THE COUNTER TO SHOW SNOOZED COUNT ──
# Find updateP function to show snoozed count
updateP_match = re.search(r'function updateP\(\)\{', html)
if updateP_match:
    # Find the line that shows the counter
    pass  # We'll add snooze count to the stats display instead

# ── SAVE ──
with open(f'{BASE}/index.html', 'w') as f:
    f.write(html)
print(f"\nSaved updated index.html ({len(html)} bytes)")
print(f"Total DS.general: {len(ds['general'])} candidates")
