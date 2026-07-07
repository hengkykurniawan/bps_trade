#!/usr/bin/env python3
"""
BPS Foreign Trade (ekspor-impor) local web app.

Zero-install UI over the webapi.bps.go.id `dataexim` endpoint:

    python bps_exim_app.py        ->  http://127.0.0.1:8766

Pick flow (export/import), years (2014+), months, HS codes (all 2-digit
chapters and/or full 8-digit BTKI codes), fetch, then filter the result
by port (pelabuhan) and country before downloading CSV.

The API key is read from `.bps_key` next to this script and never leaves
the backend; the browser only talks to this local server.
"""

import json
import os
import re
import sys
import time
import urllib.request
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8766
BASE = "https://webapi.bps.go.id/v1/api/dataexim"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FLOW = {"export": 1, "import": 2}
DATA_START_YEAR = 2014  # dataexim has nothing before this (probed 1996-2013)

# All HS chapters offered by the BPS website's "HS 2 dijit" selector
# (standard HS nomenclature; 77 is reserved and does not exist).
HS_CHAPTERS = [
    ("01", "Live animals"), ("02", "Meat and edible meat offal"),
    ("03", "Fish and crustaceans"), ("04", "Dairy produce; eggs; honey"),
    ("05", "Other products of animal origin"), ("06", "Live trees and plants"),
    ("07", "Edible vegetables"), ("08", "Edible fruit and nuts"),
    ("09", "Coffee, tea, mate and spices"), ("10", "Cereals"),
    ("11", "Milling products; malt; starches"), ("12", "Oil seeds; oleaginous fruits"),
    ("13", "Lac; gums and resins"), ("14", "Vegetable plaiting materials"),
    ("15", "Animal/vegetable fats and oils"), ("16", "Preparations of meat or fish"),
    ("17", "Sugars and sugar confectionery"), ("18", "Cocoa and cocoa preparations"),
    ("19", "Preparations of cereals/flour/milk"), ("20", "Preparations of vegetables/fruit"),
    ("21", "Miscellaneous edible preparations"), ("22", "Beverages, spirits and vinegar"),
    ("23", "Food industry residues; animal feed"), ("24", "Tobacco"),
    ("25", "Salt; sulphur; earths; cement"), ("26", "Ores, slag and ash"),
    ("27", "Mineral fuels and oils"), ("28", "Inorganic chemicals"),
    ("29", "Organic chemicals"), ("30", "Pharmaceutical products"),
    ("31", "Fertilisers"), ("32", "Tanning/dyeing extracts; paints"),
    ("33", "Essential oils; perfumery; cosmetics"), ("34", "Soap; washing preparations; waxes"),
    ("35", "Albuminoids; glues; enzymes"), ("36", "Explosives; pyrotechnics; matches"),
    ("37", "Photographic/cinematographic goods"), ("38", "Miscellaneous chemical products"),
    ("39", "Plastics and articles thereof"), ("40", "Rubber and articles thereof"),
    ("41", "Raw hides, skins and leather"), ("42", "Leather articles; travel goods"),
    ("43", "Furskins and artificial fur"), ("44", "Wood and articles of wood"),
    ("45", "Cork and articles of cork"), ("46", "Straw/basketware manufactures"),
    ("47", "Pulp of wood"), ("48", "Paper and paperboard"),
    ("49", "Printed books and newspapers"), ("50", "Silk"),
    ("51", "Wool and animal hair"), ("52", "Cotton"),
    ("53", "Other vegetable textile fibres"), ("54", "Man-made filaments"),
    ("55", "Man-made staple fibres"), ("56", "Wadding, felt, nonwovens; ropes"),
    ("57", "Carpets"), ("58", "Special woven fabrics; lace"),
    ("59", "Impregnated/coated textile fabrics"), ("60", "Knitted or crocheted fabrics"),
    ("61", "Apparel, knitted or crocheted"), ("62", "Apparel, not knitted"),
    ("63", "Other made-up textile articles"), ("64", "Footwear"),
    ("65", "Headgear"), ("66", "Umbrellas; walking-sticks"),
    ("67", "Prepared feathers; artificial flowers"), ("68", "Articles of stone/plaster/cement"),
    ("69", "Ceramic products"), ("70", "Glass and glassware"),
    ("71", "Pearls, precious stones/metals; jewellery"), ("72", "Iron and steel"),
    ("73", "Articles of iron or steel"), ("74", "Copper and articles thereof"),
    ("75", "Nickel and articles thereof"), ("76", "Aluminium and articles thereof"),
    ("78", "Lead and articles thereof"), ("79", "Zinc and articles thereof"),
    ("80", "Tin and articles thereof"), ("81", "Other base metals; cermets"),
    ("82", "Tools and cutlery of base metal"), ("83", "Miscellaneous base-metal articles"),
    ("84", "Machinery and mechanical appliances"), ("85", "Electrical machinery and equipment"),
    ("86", "Railway locomotives and stock"), ("87", "Vehicles other than railway"),
    ("88", "Aircraft and spacecraft"), ("89", "Ships and boats"),
    ("90", "Optical/photographic/medical instruments"), ("91", "Clocks and watches"),
    ("92", "Musical instruments"), ("93", "Arms and ammunition"),
    ("94", "Furniture; bedding; lamps"), ("95", "Toys, games, sports equipment"),
    ("96", "Miscellaneous manufactured articles"), ("97", "Works of art; antiques"),
]

MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
          "Agustus", "September", "Oktober", "November", "Desember"]


def load_key():
    path = os.path.join(SCRIPT_DIR, ".bps_key")
    if os.path.exists(path):
        return open(path).read().strip()
    sys.exit("No API key: put it in .bps_key next to this script.")


KEY = load_key()


def load_master():
    """hs_master.json: {era_start_year: [[code, desc], ...]}, extracted from
    BPS's 'HSCode Master BPS.pdf' by extract_hs_master.py. 2012 era uses
    10-digit codes, 2017/2022 eras 8-digit."""
    path = os.path.join(SCRIPT_DIR, "hs_master.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


MASTER = load_master()


def era_for_year(year):
    y = int(year)
    return "2012" if y <= 2016 else ("2017" if y <= 2021 else "2022")


def expand_chapters(year, chapters):
    """All full HS codes under the given 2-digit chapters, per the master
    that applies to `year`."""
    want = set(chapters)
    return [c for c, _ in MASTER[era_for_year(year)] if c[:2] in want]


def split_bracketed(s):
    m = re.match(r"\[([^\]]*)\]\s*(.*)", s or "")
    return (m.group(1), m.group(2)) if m else ("", s or "")


def fetch_exim(flow, hs_codes, year, month):
    """One dataexim request. hs_codes all at the same level."""
    jenishs = 1 if len(hs_codes[0]) <= 2 else 2
    periode = 1 if month else 2
    url = (f"{BASE}/sumber/{FLOW[flow]}/periode/{periode}"
           f"/kodehs/{'%3B'.join(hs_codes)}"
           f"/jenishs/{jenishs}/tahun/{year}/bulan/{month or 1}/key/{KEY}")
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            break
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"BPS request failed: {last}")
    if d.get("status") == "Error":
        raise RuntimeError(f"BPS: {d.get('message', 'unknown error')}")
    if d.get("data-availability") != "available":
        return []
    rows = []
    for r in d.get("data", []):
        hs_code, hs_desc = split_bracketed(r.get("kodehs"))
        month_id, month_name = split_bracketed(r.get("bulan", ""))
        rows.append({
            "flow": flow, "year": r.get("tahun"),
            "month_id": month_id, "month": month_name,
            "hs_code": hs_code, "hs_desc": hs_desc,
            "port": r.get("pod") or "", "country": r.get("ctr") or "",
            "value_usd": r.get("value"), "netweight_kg": r.get("netweight"),
        })
    return rows


PORTS_CACHE = os.path.join(SCRIPT_DIR, "ports.json")


def get_ports():
    """All port names, harvested once from a full-chapter sweep of the most
    recent complete year (the API has no port-list endpoint) and cached."""
    if os.path.exists(PORTS_CACHE):
        with open(PORTS_CACHE, encoding="utf-8") as f:
            return json.load(f)
    year = date.today().year - 1
    chapters = [c for c, _ in HS_CHAPTERS]
    ports = set()
    for flow in ("export", "import"):
        for i in range(0, len(chapters), 20):
            for r in fetch_exim(flow, chapters[i:i + 20], year, None):
                if r["port"]:
                    ports.add(r["port"])
    out = sorted(ports)
    with open(PORTS_CACHE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out


def page_html():
    year_now = date.today().year
    years = list(range(year_now, DATA_START_YEAR - 1, -1))
    cfg = json.dumps({"years": years, "months": MONTHS, "chapters": HS_CHAPTERS,
                      "hasMaster": MASTER is not None})
    return HTML.replace("__CFG__", cfg)


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BPS Foreign Trade Downloader</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root { --blue:#0b5ed7; --bg:#f5f7fa; --line:#dde3ea; }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.45 system-ui,Segoe UI,Arial,sans-serif; background:var(--bg); color:#1c2733; }
  header { background:var(--blue); color:#fff; padding:12px 20px; font-size:17px; font-weight:600; }
  header small { font-weight:400; opacity:.85; margin-left:10px; }
  main { max-width:1250px; margin:16px auto; padding:0 16px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px 16px; margin-bottom:14px; }
  .row { display:flex; flex-wrap:wrap; gap:22px; }
  .col { min-width:180px; }
  h3 { margin:0 0 8px; font-size:13px; text-transform:uppercase; letter-spacing:.4px; color:#5a6b7d; }
  label.opt { display:block; padding:1px 0; cursor:pointer; white-space:nowrap; }
  .scroll { max-height:210px; overflow:auto; border:1px solid var(--line); border-radius:6px; padding:6px 8px; background:#fcfdfe; }
  .chapters { columns:2; min-width:430px; }
  .chapters label.opt { break-inside:avoid; font-size:12.5px; }
  input[type=text], textarea, select { border:1px solid var(--line); border-radius:6px; padding:6px 8px; font:inherit; }
  textarea { width:100%; height:64px; resize:vertical; }
  .mini { font-size:12px; color:#5a6b7d; }
  button { border:0; border-radius:6px; padding:8px 18px; font:inherit; cursor:pointer; }
  .primary { background:var(--blue); color:#fff; font-weight:600; }
  .primary:disabled { background:#9db8dd; cursor:default; }
  .ghost { background:#e8eef6; color:var(--blue); }
  .linkbtn { background:none; color:var(--blue); padding:2px 4px; text-decoration:underline; }
  #bar { height:8px; background:#e4e9f0; border-radius:4px; overflow:hidden; margin-top:8px; display:none; }
  #bar div { height:100%; width:0%; background:var(--blue); transition:width .2s; }
  #stats { display:flex; gap:26px; flex-wrap:wrap; margin:4px 0 10px; }
  #stats b { font-size:17px; }
  .statlab { font-size:11.5px; color:#5a6b7d; text-transform:uppercase; letter-spacing:.4px; }
  table { border-collapse:collapse; width:100%; font-size:12.5px; }
  th, td { border-bottom:1px solid var(--line); padding:4px 8px; text-align:left; }
  th { background:#f0f4f9; position:sticky; top:0; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  #tablewrap { max-height:480px; overflow:auto; border:1px solid var(--line); border-radius:6px; }
  #log { color:#a33; font-size:12.5px; white-space:pre-wrap; }
  .filters { display:flex; gap:14px; flex-wrap:wrap; align-items:flex-end; margin-bottom:10px; }
  .filters .f { display:flex; flex-direction:column; gap:3px; }
  .filters select { min-width:210px; }
  .vizgrid { display:grid; grid-template-columns:repeat(auto-fit, minmax(400px, 1fr)); gap:20px; }
  .viz h4 { margin:0 0 6px; font-size:13px; font-weight:600; color:#52514e; }
  .viz svg { width:100%; height:auto; display:block; }
  .viz svg text { font:11px system-ui, sans-serif; fill:#898781; }
  .viz svg text.val { fill:#52514e; font-variant-numeric:tabular-nums; }
  .viz svg text.name { fill:#0b0b0b; }
  #map { height:480px; border-radius:6px; border:1px solid var(--line); }
  #tip { position:fixed; display:none; background:#0b0b0b; color:#fff; font-size:12px;
         padding:5px 9px; border-radius:5px; pointer-events:none; z-index:2000; max-width:280px; }
  .legend { display:flex; gap:18px; align-items:center; font-size:12px; color:#52514e; margin-bottom:8px; }
  .legend .sw { display:inline-block; width:14px; height:4px; border-radius:2px; vertical-align:middle; margin-right:5px; }
</style>
</head>
<body>
<header>BPS Foreign Trade Downloader <small>webapi.bps.go.id &middot; dataexim</small></header>
<main>

<div class="card">
  <div class="row">
    <div class="col">
      <h3>Flow</h3>
      <label class="opt"><input type="radio" name="flow" value="export" checked> Ekspor (export)</label>
      <label class="opt"><input type="radio" name="flow" value="import"> Impor (import)</label>
    </div>
    <div class="col">
      <h3>Year <button class="linkbtn" onclick="setAll('years',true)">all</button><button class="linkbtn" onclick="setAll('years',false)">none</button></h3>
      <div class="scroll" id="years"></div>
    </div>
    <div class="col">
      <h3>Month <button class="linkbtn" onclick="setAll('monthsbox',true)">all</button><button class="linkbtn" onclick="setAll('monthsbox',false)">none</button></h3>
      <div class="scroll" id="monthsbox"></div>
      <div class="mini" style="max-width:180px">Check months for monthly data (bulanan); leave all unchecked for annual totals (tahunan). Months not yet released are skipped.</div>
      <h3 style="margin-top:14px">Port (pelabuhan)</h3>
      <label class="opt"><input type="checkbox" id="incport" checked> Include port information</label>
      <select id="portsel" style="max-width:210px;margin-top:4px"><option value="">(all ports)</option></select>
      <h3 style="margin-top:14px">Country (negara)</h3>
      <label class="opt"><input type="checkbox" id="incctr" checked> Include country information</label>
      <select id="ctrsel" style="max-width:210px;margin-top:4px"><option value="">(all countries)</option></select>
      <div class="mini" style="max-width:200px">Untick port and/or country to aggregate values over them &mdash; untick country for world totals.</div>
    </div>
    <div class="col" style="flex:1">
      <h3>HS chapters (2-digit)
        <button class="linkbtn" onclick="setAll('chapters',true)">all</button>
        <button class="linkbtn" onclick="setAll('chapters',false)">none</button>
        <input type="text" id="hsfilter" placeholder="search..." style="margin-left:8px;padding:2px 6px;font-size:12px" oninput="filterChapters()">
      </h3>
      <div class="scroll chapters" id="chapters"></div>
      <div id="levelbox" style="margin-top:8px">
        <label class="opt" style="display:inline-block;margin-right:16px"><input type="radio" name="hslevel" value="2" checked> 2-digit (chapter totals)</label>
        <label class="opt" style="display:inline-block"><input type="radio" name="hslevel" value="8"> 8-digit (every full HS code in ticked chapters)</label>
      </div>
      <h3 style="margin-top:12px">Extra full HS codes (optional)</h3>
      <textarea id="fullhs" placeholder="e.g. 15111000 27011290  (space, comma or newline separated)"></textarea>
      <div class="mini">Must match BPS's HS master exactly: 8-digit for 2017+, 10-digit for 2014&ndash;2016. No 4/6-digit prefixes.</div>
    </div>
  </div>
  <div style="margin-top:12px; display:flex; gap:10px; align-items:center;">
    <button class="primary" id="go" onclick="fetchAll()">Fetch data</button>
    <button class="ghost" id="cancel" onclick="cancelled=true" style="display:none">Cancel</button>
    <span class="mini" id="progtext"></span>
  </div>
  <div id="bar"><div></div></div>
  <div id="log"></div>
</div>

<div class="card" id="results" style="display:none">
  <div class="filters">
    <div class="f"><span class="statlab">Pelabuhan (port)</span><select id="fport" onchange="render()"></select></div>
    <div class="f"><span class="statlab">Negara (country)</span><select id="fctr" onchange="render()"></select></div>
    <div class="f"><span class="statlab">HS code</span><select id="fhs" onchange="render()"></select></div>
    <div class="f"><span class="statlab">Search</span><input type="text" id="fsearch" placeholder="any text..." oninput="render()"></div>
    <button class="primary" onclick="downloadCSV()">Download CSV</button>
  </div>
  <div id="stats"></div>
  <div id="tablewrap"><table id="tbl"></table></div>
  <div class="mini" id="tablenote" style="margin-top:6px"></div>
</div>

<div class="card viz" id="vizcard" style="display:none">
  <div class="vizgrid">
    <div><h4 id="t_time"></h4><div id="c_time"></div></div>
    <div id="c_ctr_wrap"><h4>Top countries by value (US$)</h4><div id="c_ctr"></div></div>
    <div><h4>Top HS codes by value (US$)</h4><div id="c_hs"></div></div>
    <div id="c_port_wrap"><h4>Top ports by value (US$)</h4><div id="c_port"></div></div>
  </div>
  <div class="mini">Charts follow the filters above. Hover a bar for the exact value.</div>
</div>

<div class="card" id="mapcard" style="display:none">
  <div class="legend">
    <b style="color:#1c2733">Trade flow map</b>
    <span><span class="sw" style="background:#2a78d6"></span>export flows</span>
    <span><span class="sw" style="background:#eb6834"></span>import flows</span>
    <span><span class="sw" style="background:#0d366b;height:10px;width:10px;border-radius:50%"></span>Indonesian port</span>
  </div>
  <div class="legend" id="mapperiodrow" style="display:none">
    <span>Period:</span>
    <input type="range" id="mapslider" min="0" max="0" value="0" step="1"
           style="flex:1;max-width:360px" oninput="mapSlide(this.value)">
    <b id="mapperiodlab" style="color:#1c2733;min-width:90px"></b>
  </div>
  <div id="map"></div>
  <div class="mini" id="mapnote" style="margin-top:6px"></div>
</div>

<div id="tip"></div>

</main>
<script>
const CFG = __CFG__;
let rows = [], cancelled = false, hasPort = true, hasCtr = true;

function el(id){ return document.getElementById(id); }

function boxes(container, items, name, checkedFirst){
  el(container).innerHTML = items.map(([v, lab], i) =>
    `<label class="opt"><input type="checkbox" name="${name}" value="${v}" ${i===0&&checkedFirst?'checked':''}> ${lab}</label>`).join('');
}
boxes('years', CFG.years.map(y=>[y, y]), 'year', true);
boxes('monthsbox', CFG.months.map((m,i)=>[i+1, String(i+1).padStart(2,'0') + ' ' + m]), 'month', false);
boxes('chapters', CFG.chapters.map(([c,d])=>[c, `[${c}] ${d}`]), 'hs', false);

fetch('/api/ports').then(r => r.json()).then(d => {
  if (!d.ports) return;
  el('portsel').innerHTML = `<option value="">(all ports - ${d.ports.length})</option>` +
    d.ports.map(p => `<option>${p.replace(/</g,'&lt;')}</option>`).join('');
}).catch(() => {});
fetch('/api/countries').then(r => r.json()).then(d => {
  if (!d.countries) return;
  el('ctrsel').innerHTML = `<option value="">(all countries - ${d.countries.length})</option>` +
    d.countries.map(c => `<option>${c.replace(/</g,'&lt;')}</option>`).join('');
}).catch(() => {});

function setAll(container, on){
  el(container).querySelectorAll('input[type=checkbox]').forEach(b => {
    if (b.closest('label').style.display !== 'none') b.checked = on;
  });
}
function filterChapters(){
  const q = el('hsfilter').value.toLowerCase();
  el('chapters').querySelectorAll('label').forEach(l => {
    l.style.display = l.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}
function picked(name){
  return [...document.querySelectorAll(`input[name=${name}]:checked`)].map(b => b.value);
}

async function fetchAll(){
  const flow = document.querySelector('input[name=flow]:checked').value;
  const years = picked('year');
  // months checked -> monthly data; none checked -> annual totals
  const months = picked('month').length ? picked('month') : [''];
  const chapters = picked('hs');
  const full = el('fullhs').value.split(/[\s,;]+/).filter(Boolean);
  const bad = full.filter(c => !/^\d{3,10}$/.test(c));

  const level = document.querySelector('input[name=hslevel]:checked').value;

  el('log').textContent = '';
  if (!years.length) return el('log').textContent = 'Pick at least one year.';
  if (!chapters.length && !full.length) return el('log').textContent = 'Pick at least one HS chapter or enter a full HS code.';
  if (bad.length) return el('log').textContent = 'These do not look like HS codes: ' + bad.join(', ');
  if (level === '8' && chapters.length && !CFG.hasMaster)
    return el('log').textContent = 'hs_master.json is missing next to the app - 8-digit expansion unavailable.';

  // the API rejects requests with more than 20 HS codes
  const chunk = arr => Array.from({length: Math.ceil(arr.length/20)}, (_, i) => arr.slice(i*20, i*20+20));
  const jobs = [];
  if (chapters.length && level === '2')
    for (const b of chunk(chapters)) for (const y of years) for (const m of months) jobs.push({b, y, m});
  if (chapters.length && level === '8') {
    // full codes differ by era (10-digit <=2016, 8-digit after); expand per year
    const cache = {};
    for (const y of years) {
      if (!(y in cache)) {
        const r = await fetch(`/api/expand?year=${y}&chapters=${chapters.join(';')}`);
        const d = await r.json();
        if (d.error) return el('log').textContent = 'Error: ' + d.error;
        cache[y] = d.codes;
      }
      for (const b of chunk(cache[y])) for (const m of months) jobs.push({b, y, m});
    }
  }
  if (full.length)
    for (const b of chunk(full)) for (const y of years) for (const m of months) jobs.push({b, y, m});

  rows = []; cancelled = false;
  el('go').disabled = true; el('cancel').style.display = '';
  el('bar').style.display = ''; el('bar').firstElementChild.style.width = '0%';
  el('results').style.display = el('vizcard').style.display = el('mapcard').style.display = 'none';

  let done = 0, empty = 0;
  const run = async job => {
    const u = `/api/exim?flow=${flow}&hs=${job.b.join(';')}&year=${job.y}&month=${job.m}`;
    const r = await fetch(u);
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    if (!d.rows.length) empty++;
    rows.push(...d.rows);
    done++;
    el('bar').firstElementChild.style.width = (100*done/jobs.length) + '%';
    el('progtext').textContent = `${done}/${jobs.length} requests, ${rows.length.toLocaleString()} rows`;
  };
  try {
    const queue = [...jobs];
    const workers = Array.from({length: 4}, async () => {
      while (queue.length && !cancelled) await run(queue.shift());
    });
    await Promise.all(workers);
    if (cancelled) el('log').textContent = 'Cancelled - showing what was fetched so far.';
  } catch (e) {
    el('log').textContent = 'Error: ' + e.message;
  }
  el('go').disabled = false; el('cancel').style.display = 'none';

  hasPort = el('incport').checked;
  hasCtr = el('incctr').checked;
  const onePort = el('portsel').value, oneCtr = el('ctrsel').value;
  let note = '';
  if (hasPort && onePort) { rows = rows.filter(r => r.port === onePort); note += ` for ${onePort}`; }
  if (hasCtr && oneCtr) { rows = rows.filter(r => r.country === oneCtr); note += ` for ${oneCtr}`; }
  if (!hasPort || !hasCtr) {
    // aggregate: sum values per flow/year/month/HS + whichever dims remain
    const agg = new Map();
    for (const r of rows) {
      const p = hasPort ? r.port : '', c = hasCtr ? r.country : '';
      const k = [r.flow, r.year, r.month_id, r.hs_code, p, c].join('|');
      const a = agg.get(k);
      if (a) { a.value_usd += +r.value_usd || 0; a.netweight_kg += +r.netweight_kg || 0; }
      else agg.set(k, {...r, port: p, country: c, value_usd: +r.value_usd || 0, netweight_kg: +r.netweight_kg || 0});
    }
    rows = [...agg.values()];
    note += !hasPort && !hasCtr ? ' (world totals: aggregated over ports & countries)'
          : !hasPort ? ' (aggregated over ports)' : ' (world: aggregated over countries)';
  }

  el('progtext').textContent = `${rows.length.toLocaleString()} rows${note}`
    + (empty ? ` (${empty} request(s) with no data skipped)` : '');
  rows.sort((a, b) =>
    (+a.year - +b.year) || ((+a.month_id || 0) - (+b.month_id || 0)) ||
    a.hs_code.localeCompare(b.hs_code) || (a.port || '').localeCompare(b.port || '') ||
    (a.country || '').localeCompare(b.country || ''));
  if (rows.length) {
    buildFilters();
    el('results').style.display = el('vizcard').style.display = el('mapcard').style.display = '';
    render();
  }
}

function fillSelect(id, values, label){
  const s = el(id);
  s.innerHTML = `<option value="">(all ${label} - ${values.length})</option>` +
    values.map(v => `<option>${v.replace(/</g,'&lt;')}</option>`).join('');
}
function buildFilters(){
  el('fport').closest('.f').style.display = hasPort ? '' : 'none';
  el('fctr').closest('.f').style.display = hasCtr ? '' : 'none';
  el('fport').value = ''; el('fctr').value = '';
  if (hasPort) fillSelect('fport', [...new Set(rows.map(r=>r.port))].sort(), 'ports');
  if (hasCtr) fillSelect('fctr', [...new Set(rows.map(r=>r.country))].sort(), 'countries');
  fillSelect('fhs', [...new Set(rows.map(r=>r.hs_code))].sort(), 'HS');
  el('fsearch').value = '';
}
function filtered(){
  const p = el('fport').value, c = el('fctr').value, h = el('fhs').value,
        q = el('fsearch').value.toLowerCase();
  return rows.filter(r =>
    (!p || r.port === p) && (!c || r.country === c) && (!h || r.hs_code === h) &&
    (!q || Object.values(r).join(' ').toLowerCase().includes(q)));
}

const COLS = ['flow','year','month_id','month','hs_code','hs_desc','port','country','value_usd','netweight_kg'];
const NUM = new Set(['value_usd','netweight_kg']);
const activeCols = () => COLS.filter(c =>
  (hasPort || c !== 'port') && (hasCtr || c !== 'country'));

function render(){
  const f = filtered();
  const usd = f.reduce((s,r)=>s+(+r.value_usd||0), 0);
  const kg  = f.reduce((s,r)=>s+(+r.netweight_kg||0), 0);
  el('stats').innerHTML =
    `<span><div class="statlab">rows (filtered / fetched)</div><b>${f.length.toLocaleString()} / ${rows.length.toLocaleString()}</b></span>` +
    `<span><div class="statlab">total value (US$)</div><b>${usd.toLocaleString(undefined,{maximumFractionDigits:0})}</b></span>` +
    `<span><div class="statlab">total net weight (kg)</div><b>${kg.toLocaleString(undefined,{maximumFractionDigits:0})}</b></span>`;
  const cap = 1000, show = f.slice(0, cap), cols = activeCols();
  el('tbl').innerHTML =
    '<tr>' + cols.map(c=>`<th class="${NUM.has(c)?'num':''}">${c}</th>`).join('') + '</tr>' +
    show.map(r => '<tr>' + cols.map(c => {
      let v = r[c] ?? '';
      if (NUM.has(c)) v = (+v).toLocaleString();
      return `<td class="${NUM.has(c)?'num':''}">${String(v).replace(/</g,'&lt;')}</td>`;
    }).join('') + '</tr>').join('');
  el('tablenote').textContent = f.length > cap
    ? `Preview limited to ${cap.toLocaleString()} rows - the CSV download contains all ${f.length.toLocaleString()} filtered rows.` : '';
  renderCharts(f);
  rebuildSlider(f);
  updateMap(f);
}

// ---------------------------------------------------------------- charts
const BLUE = '#2a78d6', ORANGE = '#eb6834', GRID = '#e1e0d9', AXIS = '#c3c2b7';
const esc_ = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const fmtV = v => v >= 1e9 ? (v/1e9).toFixed(1)+'B' : v >= 1e6 ? (v/1e6).toFixed(1)+'M'
              : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : String(Math.round(v));
function showTip(ev, html){ const t = el('tip'); t.innerHTML = html; t.style.display = 'block';
  t.style.left = Math.min(ev.clientX + 14, innerWidth - 290) + 'px'; t.style.top = (ev.clientY + 14) + 'px'; }
function hideTip(){ el('tip').style.display = 'none'; }

function roundTopBar(x, y, w, h){  // 4px rounded data-end, anchored to baseline
  const r = Math.min(4, w/2, h);
  return `M${x},${y+h} L${x},${y+r} Q${x},${y} ${x+r},${y} L${x+w-r},${y} Q${x+w},${y} ${x+w},${y+r} L${x+w},${y+h} Z`;
}
function roundEndBarH(x, y, w, h){
  const r = Math.min(4, h/2, w);
  return `M${x},${y} L${x+w-r},${y} Q${x+w},${y} ${x+w},${y+r} L${x+w},${y+h-r} Q${x+w},${y+h} ${x+w-r},${y+h} L${x},${y+h} Z`;
}

function drawBarsV(id, data, color){  // data: [[label, value], ...] in x order
  const W = 560, H = 230, L = 48, R = 8, T = 10, B = 24;
  const max = Math.max(...data.map(d => d[1]), 1);
  const iw = W - L - R, ih = H - T - B, n = data.length;
  const slot = iw/n, bw = Math.max(2, Math.min(56, slot - 2));
  let s = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  for (let g = 0; g <= 4; g++) {
    const y = T + ih - ih*g/4;
    s += `<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="${g ? GRID : AXIS}" stroke-width="1"/>`
       + `<text x="${L-6}" y="${y+4}" text-anchor="end" class="val">${fmtV(max*g/4)}</text>`;
  }
  const step = Math.ceil(n / 8);
  data.forEach(([lab, v], i) => {
    const x = L + slot*i + (slot - bw)/2, h = Math.max(1, ih*v/max), y = T + ih - h;
    s += `<path d="${roundTopBar(x, y, bw, h)}" fill="${color}" data-tip="${esc_(lab)}: US$ ${Math.round(v).toLocaleString()}"/>`;
    if (i % step === 0) s += `<text x="${x+bw/2}" y="${H-8}" text-anchor="middle">${esc_(lab)}</text>`;
  });
  el(id).innerHTML = s + '</svg>';
}

function drawBarsH(id, data, color){  // data: [[label, value], ...] descending
  const W = 560, L = 170, R = 62, RH = 25, T = 4;
  const H = T + data.length*RH + 6;
  const max = Math.max(...data.map(d => d[1]), 1);
  const iw = W - L - R;
  let s = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  s += `<line x1="${L-4}" y1="${T}" x2="${L-4}" y2="${H-4}" stroke="${AXIS}" stroke-width="1"/>`;
  data.forEach(([lab, v], i) => {
    const y = T + RH*i + 4, w = Math.max(1, iw*v/max);
    const name = lab.length > 24 ? lab.slice(0, 23) + '…' : lab;
    s += `<text x="${L-10}" y="${y+11}" text-anchor="end" class="name">${esc_(name)}</text>`
       + `<path d="${roundEndBarH(L-4, y, w, RH-9)}" fill="${color}" data-tip="${esc_(lab)}: US$ ${Math.round(v).toLocaleString()}"/>`
       + `<text x="${L+w+2}" y="${y+11}" class="val">${fmtV(v)}</text>`;
  });
  el(id).innerHTML = s + '</svg>';
}

function renderCharts(f){
  const color = f[0] && f[0].flow === 'import' ? ORANGE : BLUE;
  const sum = keyf => { const m = new Map();
    for (const r of f){ const k = keyf(r); m.set(k, (m.get(k)||0) + (+r.value_usd||0)); } return m; };
  const per = [...sum(r => r.month_id ? `${r.year}-${r.month_id}` : String(r.year)).entries()]
    .sort((a,b) => a[0].localeCompare(b[0]));
  el('t_time').textContent = `Value by ${per[0] && per[0][0].includes('-') ? 'month' : 'year'} (US$)`;
  drawBarsV('c_time', per, color);
  const top = keyf => [...sum(keyf).entries()].sort((a,b) => b[1]-a[1]).slice(0, 10);
  el('c_ctr_wrap').style.display = hasCtr ? '' : 'none';
  if (hasCtr) drawBarsH('c_ctr', top(r => r.country), color);
  drawBarsH('c_hs', top(r => r.hs_code), color);
  el('c_port_wrap').style.display = hasPort ? '' : 'none';
  if (hasPort) drawBarsH('c_port', top(r => r.port), color);
}

document.addEventListener('mousemove', ev => {
  const tgt = ev.target.closest && ev.target.closest('[data-tip]');
  if (tgt) showTip(ev, tgt.getAttribute('data-tip')); else hideTip();
});

// ------------------------------------------------------------------- map
let map = null, flowLayer = null, GEO = null;
let mapPeriods = [], mapIdx = 0;  // 0 = all periods, i>0 = mapPeriods[i-1]
const perKey = r => r.month_id ? `${r.year}-${r.month_id}` : String(r.year);

function rebuildSlider(f){
  const ps = [...new Set(f.map(perKey))].sort();
  if (ps.join('|') !== mapPeriods.join('|')) { mapPeriods = ps; mapIdx = 0; }
  el('mapperiodrow').style.display = ps.length > 1 ? 'flex' : 'none';
  const s = el('mapslider');
  s.max = ps.length; s.value = mapIdx;
  el('mapperiodlab').textContent = mapIdx ? mapPeriods[mapIdx-1] : 'All periods';
}
function mapSlide(v){
  mapIdx = +v;
  el('mapperiodlab').textContent = mapIdx ? mapPeriods[mapIdx-1] : 'All periods';
  updateMap(filtered());
}

async function ensureMap(){
  if (!window.L) { el('mapnote').textContent = 'Map library could not load (no internet access to unpkg.com).'; return false; }
  if (!GEO) {
    const d = await fetch('/api/geo').then(r => r.json()).catch(() => ({error:'fetch failed'}));
    if (d.error) { el('mapnote').textContent = 'No coordinates yet: ' + d.error; return false; }
    GEO = d;
  }
  if (!map) {
    map = L.map('map', {worldCopyJump: true}).setView([-2.5, 118], 3);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      {attribution: '&copy; OpenStreetMap contributors', maxZoom: 12}).addTo(map);
    flowLayer = L.layerGroup().addTo(map);
  }
  setTimeout(() => map.invalidateSize(), 60);
  return true;
}

async function updateMap(f){
  if (!(await ensureMap())) return;
  flowLayer.clearLayers();
  if (mapIdx) f = f.filter(r => perKey(r) === mapPeriods[mapIdx-1]);
  const col = f[0] && f[0].flow === 'import' ? ORANGE : BLUE;
  const flows = new Map();
  for (const r of f) {
    const k = (hasPort ? r.port : '__ID__') + '|' + r.country;
    flows.set(k, (flows.get(k)||0) + (+r.value_usd||0));
  }
  const items = [...flows.entries()].map(([k, v]) => { const [p, c] = k.split('|'); return {p, c, v}; })
    .sort((a, b) => b.v - a.v);
  const shown = items.slice(0, 250);
  const maxv = shown[0] ? shown[0].v : 1;
  const miss = new Set(), portSum = new Map(), ctrSum = new Map();
  for (const {p, c, v} of shown) {
    const pp = p === '__ID__' ? GEO.indonesia : GEO.ports[p];
    if (!pp) { miss.add(p); continue; }
    portSum.set(p, (portSum.get(p)||0) + v);
    if (!c) continue;  // world mode: port markers only, no country lines
    const cc = GEO.countries[c];
    if (!cc) { miss.add(c); continue; }
    let clon = cc[1];  // route across the Pacific rather than the long way round
    if (clon - pp[1] > 180) clon -= 360;
    if (clon - pp[1] < -180) clon += 360;
    L.polyline([[pp[0], pp[1]], [cc[0], clon]],
        {color: col, weight: 1 + 6*Math.sqrt(v/maxv), opacity: .4})
      .bindTooltip(`${p === '__ID__' ? 'Indonesia' : esc_(p)} &harr; ${esc_(c)}<br>US$ ${Math.round(v).toLocaleString()}`, {sticky: true})
      .addTo(flowLayer);
    ctrSum.set(c, (ctrSum.get(c)||0) + v);
  }
  for (const [p, v] of portSum) {
    const pp = p === '__ID__' ? GEO.indonesia : GEO.ports[p];
    if (!pp) continue;
    L.circleMarker(pp, {radius: 3 + 6*Math.sqrt(v/maxv), color: '#fff', weight: 1, fillColor: '#0d366b', fillOpacity: .9})
      .bindTooltip(`${p === '__ID__' ? 'Indonesia (all ports)' : esc_(p)}<br>US$ ${Math.round(v).toLocaleString()}`).addTo(flowLayer);
  }
  for (const [c, v] of ctrSum) {
    const cc = GEO.countries[c];
    if (!cc) continue;
    L.circleMarker(cc, {radius: 2 + 5*Math.sqrt(v/maxv), color: '#fff', weight: 1, fillColor: col, fillOpacity: .8})
      .bindTooltip(`${esc_(c)}<br>US$ ${Math.round(v).toLocaleString()}`).addTo(flowLayer);
  }
  el('mapnote').textContent =
    `${mapIdx ? mapPeriods[mapIdx-1] : 'all periods'}: ` +
    `${shown.length}${items.length > shown.length ? ' of ' + items.length.toLocaleString() : ''} flows shown (largest first); ` +
    `line width and marker size scale with value` +
    (miss.size ? ` - no coordinates for: ${[...miss].slice(0, 6).join(', ')}${miss.size > 6 ? ' …' : ''}` : '');
}

function downloadCSV(){
  const f = filtered();
  if (!f.length) return;
  const esc = v => { v = String(v ?? ''); return /[",\n]/.test(v) ? '"'+v.replace(/"/g,'""')+'"' : v; };
  const cols = activeCols();
  const csv = '﻿' + cols.join(',') + '\n' + f.map(r => cols.map(c=>esc(r[c])).join(',')).join('\n');
  const flow = rows[0].flow, years = [...new Set(f.map(r=>r.year))].sort();
  const span = years.length > 1 ? years[0]+'-'+years[years.length-1] : (years[0]||'');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
  a.download = `exim_${flow}_${span}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/":
            return self.send(200, page_html(), "text/html")
        if p.path == "/api/countries":
            try:
                path = os.path.join(SCRIPT_DIR, "geo.json")
                with open(path, encoding="utf-8") as f:
                    names = sorted(json.load(f)["countries"])
                return self.send(200, json.dumps({"countries": names}),
                                 "application/json")
            except Exception as e:
                return self.send(200, json.dumps({"error": str(e), "countries": []}),
                                 "application/json")
        if p.path == "/api/geo":
            path = os.path.join(SCRIPT_DIR, "geo.json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return self.send(200, f.read(), "application/json")
            return self.send(200, json.dumps(
                {"error": "geo.json missing - run: python geocode_geo.py"}),
                "application/json")
        if p.path == "/api/ports":
            try:
                return self.send(200, json.dumps({"ports": get_ports()}),
                                 "application/json")
            except Exception as e:
                return self.send(200, json.dumps({"error": str(e), "ports": []}),
                                 "application/json")
        if p.path == "/api/expand":
            q = parse_qs(p.query)
            try:
                if MASTER is None:
                    raise RuntimeError("hs_master.json not found next to the app")
                chapters = [c for c in q["chapters"][0].split(";") if c]
                codes = expand_chapters(q["year"][0], chapters)
                return self.send(200, json.dumps({"codes": codes}), "application/json")
            except Exception as e:
                return self.send(200, json.dumps({"error": str(e), "codes": []}),
                                 "application/json")
        if p.path == "/api/exim":
            q = parse_qs(p.query)
            try:
                flow = q["flow"][0]
                codes = [c for c in q["hs"][0].split(";") if c]
                year = q["year"][0]
                month = q.get("month", [""])[0]
                rows = fetch_exim(flow, codes, year, int(month) if month else None)
                return self.send(200, json.dumps({"rows": rows}), "application/json")
            except Exception as e:
                return self.send(200, json.dumps({"error": str(e), "rows": []}),
                                 "application/json")
        self.send(404, "not found", "text/plain")


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"BPS Foreign Trade Downloader -> {url}   (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
