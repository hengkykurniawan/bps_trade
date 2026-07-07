'use strict';

const BASE = 'https://webapi.bps.go.id/v1/api/dataexim';
const FLOW = { export: 1, import: 2 };
const DATA_START_YEAR = 2014;
const MONTHS = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'];
const HS_CHAPTERS = [
  ['01','Live animals'],['02','Meat and edible meat offal'],['03','Fish and crustaceans'],['04','Dairy produce; eggs; honey'],['05','Other products of animal origin'],['06','Live trees and plants'],['07','Edible vegetables'],['08','Edible fruit and nuts'],['09','Coffee, tea, mate and spices'],['10','Cereals'],['11','Milling products; malt; starches'],['12','Oil seeds; oleaginous fruits'],['13','Lac; gums and resins'],['14','Vegetable plaiting materials'],['15','Animal/vegetable fats and oils'],['16','Preparations of meat or fish'],['17','Sugars and sugar confectionery'],['18','Cocoa and cocoa preparations'],['19','Preparations of cereals/flour/milk'],['20','Preparations of vegetables/fruit'],['21','Miscellaneous edible preparations'],['22','Beverages, spirits and vinegar'],['23','Food industry residues; animal feed'],['24','Tobacco'],['25','Salt; sulphur; earths; cement'],['26','Ores, slag and ash'],['27','Mineral fuels and oils'],['28','Inorganic chemicals'],['29','Organic chemicals'],['30','Pharmaceutical products'],['31','Fertilisers'],['32','Tanning/dyeing extracts; paints'],['33','Essential oils; perfumery; cosmetics'],['34','Soap; washing preparations; waxes'],['35','Albuminoids; glues; enzymes'],['36','Explosives; pyrotechnics; matches'],['37','Photographic/cinematographic goods'],['38','Miscellaneous chemical products'],['39','Plastics and articles thereof'],['40','Rubber and articles thereof'],['41','Raw hides, skins and leather'],['42','Leather articles; travel goods'],['43','Furskins and artificial fur'],['44','Wood and articles of wood'],['45','Cork and articles of cork'],['46','Straw/basketware manufactures'],['47','Pulp of wood'],['48','Paper and paperboard'],['49','Printed books and newspapers'],['50','Silk'],['51','Wool and animal hair'],['52','Cotton'],['53','Other vegetable textile fibres'],['54','Man-made filaments'],['55','Man-made staple fibres'],['56','Wadding, felt, nonwovens; ropes'],['57','Carpets'],['58','Special woven fabrics; lace'],['59','Impregnated/coated textile fabrics'],['60','Knitted or crocheted fabrics'],['61','Apparel, knitted or crocheted'],['62','Apparel, not knitted'],['63','Other made-up textile articles'],['64','Footwear'],['65','Headgear'],['66','Umbrellas; walking-sticks'],['67','Prepared feathers; artificial flowers'],['68','Articles of stone/plaster/cement'],['69','Ceramic products'],['70','Glass and glassware'],['71','Pearls, precious stones/metals; jewellery'],['72','Iron and steel'],['73','Articles of iron or steel'],['74','Copper and articles thereof'],['75','Nickel and articles thereof'],['76','Aluminium and articles thereof'],['78','Lead and articles thereof'],['79','Zinc and articles thereof'],['80','Tin and articles thereof'],['81','Other base metals; cermets'],['82','Tools and cutlery of base metal'],['83','Miscellaneous base-metal articles'],['84','Machinery and mechanical appliances'],['85','Electrical machinery and equipment'],['86','Railway locomotives and stock'],['87','Vehicles other than railway'],['88','Aircraft and spacecraft'],['89','Ships and boats'],['90','Optical/photographic/medical instruments'],['91','Clocks and watches'],['92','Musical instruments'],['93','Arms and ammunition'],['94','Furniture; bedding; lamps'],['95','Toys, games, sports equipment'],['96','Miscellaneous manufactured articles'],['97','Works of art; antiques']
];

let rows = [];
let cancelled = false;
let hasPort = true;
let hasCtr = true;
let MASTER = null;
let GEO = null;

const el = id => document.getElementById(id);
const html = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function boxes(container, items, name, checkedFirst = false) {
  el(container).innerHTML = items.map(([v, lab], i) =>
    `<label class="opt"><input type="checkbox" name="${name}" value="${v}" ${i === 0 && checkedFirst ? 'checked' : ''}> ${html(lab)}</label>`
  ).join('');
}

function initBoxes() {
  const yearNow = new Date().getFullYear();
  boxes('years', Array.from({ length: yearNow - DATA_START_YEAR + 1 }, (_, i) => [yearNow - i, yearNow - i]), 'year', true);
  boxes('monthsbox', MONTHS.map((m, i) => [i + 1, String(i + 1).padStart(2, '0') + ' ' + m]), 'month', false);
  boxes('chapters', HS_CHAPTERS.map(([c, d]) => [c, `[${c}] ${d}`]), 'hs', false);
}

async function loadStaticData() {
  try {
    const r = await fetch('hs_master.json', { cache: 'no-store' });
    if (r.ok) {
      const txt = await r.text();
      MASTER = txt.trim() ? JSON.parse(txt) : null;
    }
  } catch (_) {
    MASTER = null;
  }
  try {
    const r = await fetch('geo.json', { cache: 'no-store' });
    if (r.ok) {
      GEO = await r.json();
      fillInputSelect('portsel', Object.keys(GEO.ports || {}).sort(), 'all ports');
      fillInputSelect('ctrsel', Object.keys(GEO.countries || {}).sort(), 'all countries');
    }
  } catch (_) {
    GEO = null;
  }
}

function fillInputSelect(id, values, label) {
  const s = el(id);
  s.innerHTML = `<option value="">(${label} - ${values.length})</option>` + values.map(v => `<option>${html(v)}</option>`).join('');
}

function picked(name) {
  return [...document.querySelectorAll(`input[name=${name}]:checked`)].map(b => b.value);
}

function setAll(container, on) {
  el(container).querySelectorAll('input[type=checkbox]').forEach(b => {
    if (b.closest('label').style.display !== 'none') b.checked = on;
  });
}

function filterChapters() {
  const q = el('hsfilter').value.toLowerCase();
  el('chapters').querySelectorAll('label').forEach(l => {
    l.style.display = l.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

function eraForYear(y) {
  y = Number(y);
  return y <= 2016 ? '2012' : (y <= 2021 ? '2017' : '2022');
}

function expandChapters(year, chapters) {
  if (!MASTER) throw new Error('hs_master.json is missing or empty, so full HS expansion is unavailable. Use 2-digit chapter totals or enter full HS codes manually.');
  const era = eraForYear(year);
  const want = new Set(chapters);
  return (MASTER[era] || []).filter(x => want.has(String(x[0]).slice(0, 2))).map(x => String(x[0]));
}

function splitBracketed(s) {
  const m = String(s || '').match(/^\[([^\]]*)\]\s*(.*)/);
  return m ? [m[1], m[2]] : ['', s || ''];
}

function requestUrls(url, mode) {
  const encoded = encodeURIComponent(url);
  const map = {
    direct: [url],
    allorigins: [`https://api.allorigins.win/raw?url=${encoded}`],
    corsproxyio: [`https://corsproxy.io/?${encoded}`],
    codetabs: [`https://api.codetabs.com/v1/proxy/?quest=${encoded}`],
    auto: [url, `https://api.allorigins.win/raw?url=${encoded}`, `https://corsproxy.io/?${encoded}`, `https://api.codetabs.com/v1/proxy/?quest=${encoded}`]
  };
  return map[mode] || map.auto;
}

async function fetchJsonWithFallback(url) {
  const mode = el('requestmode').value || 'auto';
  const errors = [];
  for (const candidate of requestUrls(url, mode)) {
    try {
      const r = await fetch(candidate, { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const text = await r.text();
      return JSON.parse(text);
    } catch (e) {
      errors.push(`${candidate.includes('webapi.bps') ? 'direct' : new URL(candidate).hostname}: ${e.message || e}`);
    }
  }
  throw new Error('Could not fetch BPS data. Attempts: ' + errors.join(' | '));
}

async function fetchExim(flow, hsCodes, year, month, key) {
  const jenishs = String(hsCodes[0]).length <= 2 ? 1 : 2;
  const periode = month ? 1 : 2;
  const hs = encodeURIComponent(hsCodes.join(';'));
  const url = `${BASE}/sumber/${FLOW[flow]}/periode/${periode}/kodehs/${hs}/jenishs/${jenishs}/tahun/${year}/bulan/${month || 1}/key/${encodeURIComponent(key)}`;
  const d = await fetchJsonWithFallback(url);
  if (d.status === 'Error') throw new Error(d.message || 'BPS API error');
  if (d['data-availability'] !== 'available') return [];
  return (d.data || []).map(r => {
    const [hs_code, hs_desc] = splitBracketed(r.kodehs);
    const [month_id, month_name] = splitBracketed(r.bulan || '');
    return {
      flow, year: r.tahun, month_id, month: month_name,
      hs_code, hs_desc, port: r.pod || '', country: r.ctr || '',
      value_usd: Number(r.value) || 0,
      netweight_kg: Number(r.netweight) || 0
    };
  });
}

function chunk(arr, n = 20) {
  return Array.from({ length: Math.ceil(arr.length / n) }, (_, i) => arr.slice(i * n, i * n + n));
}

async function fetchAll() {
  const key = el('apikey').value.trim();
  const flow = document.querySelector('input[name=flow]:checked').value;
  const years = picked('year');
  const months = picked('month').length ? picked('month') : [''];
  const chapters = picked('hs');
  const full = el('fullhs').value.split(/[\s,;]+/).filter(Boolean);
  const bad = full.filter(c => !/^\d{3,10}$/.test(c));
  const level = document.querySelector('input[name=hslevel]:checked').value;

  el('log').textContent = '';
  if (!key) return log('Enter your BPS API key first.');
  if (!years.length) return log('Pick at least one year.');
  if (!chapters.length && !full.length) return log('Pick at least one HS chapter or enter a full HS code.');
  if (bad.length) return log('These do not look like HS codes: ' + bad.join(', '));

  const jobs = [];
  try {
    if (chapters.length && level === '2') {
      for (const b of chunk(chapters)) for (const y of years) for (const m of months) jobs.push({ b, y, m });
    }
    if (chapters.length && level === '8') {
      for (const y of years) {
        const codes = expandChapters(y, chapters);
        for (const b of chunk(codes)) for (const m of months) jobs.push({ b, y, m });
      }
    }
    if (full.length) {
      for (const b of chunk(full)) for (const y of years) for (const m of months) jobs.push({ b, y, m });
    }
  } catch (e) {
    return log(e.message || String(e));
  }

  rows = [];
  cancelled = false;
  el('go').disabled = true;
  el('cancel').hidden = false;
  el('bar').style.display = 'block';
  el('bar').firstElementChild.style.width = '0%';
  el('results').hidden = true;
  el('vizcard').hidden = true;

  let done = 0;
  let empty = 0;
  const run = async job => {
    const r = await fetchExim(flow, job.b, job.y, job.m, key);
    if (!r.length) empty++;
    rows.push(...r);
    done++;
    el('bar').firstElementChild.style.width = `${100 * done / jobs.length}%`;
    el('progtext').textContent = `${done}/${jobs.length} requests, ${rows.length.toLocaleString()} rows`;
  };

  try {
    const queue = [...jobs];
    const workers = Array.from({ length: Math.min(4, jobs.length) }, async () => {
      while (queue.length && !cancelled) await run(queue.shift());
    });
    await Promise.all(workers);
    if (cancelled) log('Cancelled - showing what was fetched so far.');
  } catch (e) {
    log('Error: ' + (e.message || e));
  }

  el('go').disabled = false;
  el('cancel').hidden = true;
  postProcess(empty);
}

function postProcess(empty) {
  hasPort = el('incport').checked;
  hasCtr = el('incctr').checked;
  const onePort = el('portsel').value;
  const oneCtr = el('ctrsel').value;
  let note = '';

  if (hasPort && onePort) {
    rows = rows.filter(r => r.port === onePort);
    note += ` for ${onePort}`;
  }
  if (hasCtr && oneCtr) {
    rows = rows.filter(r => r.country === oneCtr);
    note += ` for ${oneCtr}`;
  }
  if (!hasPort || !hasCtr) {
    const agg = new Map();
    for (const r of rows) {
      const p = hasPort ? r.port : '';
      const c = hasCtr ? r.country : '';
      const k = [r.flow, r.year, r.month_id, r.month, r.hs_code, r.hs_desc, p, c].join('|');
      const a = agg.get(k);
      if (a) {
        a.value_usd += Number(r.value_usd) || 0;
        a.netweight_kg += Number(r.netweight_kg) || 0;
      } else {
        agg.set(k, { ...r, port: p, country: c });
      }
    }
    rows = [...agg.values()];
    note += !hasPort && !hasCtr ? ' (world totals: aggregated over ports & countries)' : !hasPort ? ' (aggregated over ports)' : ' (world: aggregated over countries)';
  }

  rows.sort((a, b) =>
    (Number(a.year) - Number(b.year)) ||
    ((Number(a.month_id) || 0) - (Number(b.month_id) || 0)) ||
    String(a.hs_code).localeCompare(String(b.hs_code)) ||
    String(a.port).localeCompare(String(b.port)) ||
    String(a.country).localeCompare(String(b.country))
  );
  el('progtext').textContent = `${rows.length.toLocaleString()} rows${note}` + (empty ? ` (${empty} empty request(s) skipped)` : '');
  if (rows.length) {
    buildFilters();
    el('results').hidden = false;
    el('vizcard').hidden = false;
    render();
  }
}

function log(msg) {
  el('log').textContent = msg;
}

function fillSelect(id, values, label) {
  const s = el(id);
  s.innerHTML = `<option value="">(all ${label} - ${values.length})</option>` + values.map(v => `<option>${html(v)}</option>`).join('');
}

function buildFilters() {
  el('fport').closest('.f').style.display = hasPort ? '' : 'none';
  el('fctr').closest('.f').style.display = hasCtr ? '' : 'none';
  if (hasPort) fillSelect('fport', [...new Set(rows.map(r => r.port))].sort(), 'ports');
  if (hasCtr) fillSelect('fctr', [...new Set(rows.map(r => r.country))].sort(), 'countries');
  
  const uniqueHs = [...new Set(rows.map(r => r.hs_code))].sort();
  const s = el('fhs');
  let htmlOpts = `<option value="">(all HS - ${uniqueHs.length})</option>`;
  if (uniqueHs.length > 1) {
    htmlOpts += `<option value="_total_">Total HS (sum of all)</option>`;
  }
  htmlOpts += uniqueHs.map(v => `<option value="${v}">${html(v)}</option>`).join('');
  s.innerHTML = htmlOpts;
  
  el('fsearch').value = '';
}

function filtered() {
  const p = el('fport').value;
  const c = el('fctr').value;
  const h = el('fhs').value;
  const q = el('fsearch').value.toLowerCase();
  
  let res = rows.filter(r =>
    (!p || r.port === p) && (!c || r.country === c) &&
    ((!h || h === '_total_') || r.hs_code === h) &&
    (!q || Object.values(r).join(' ').toLowerCase().includes(q))
  );
  
  if (h === '_total_') {
    const agg = new Map();
    for (const r of res) {
      const k = [r.flow, r.year, r.month_id, r.month, r.port, r.country].join('|');
      const a = agg.get(k);
      if (a) {
        a.value_usd += Number(r.value_usd) || 0;
        a.netweight_kg += Number(r.netweight_kg) || 0;
      } else {
        agg.set(k, {
          ...r,
          hs_code: 'Total',
          hs_desc: 'Total of selected HS codes',
          value_usd: Number(r.value_usd) || 0,
          netweight_kg: Number(r.netweight_kg) || 0
        });
      }
    }
    res = [...agg.values()];
  }
  return res;
}

const COLS = ['flow', 'year', 'month_id', 'month', 'hs_code', 'hs_desc', 'port', 'country', 'value_usd', 'netweight_kg'];
const NUM = new Set(['value_usd', 'netweight_kg']);
const activeCols = () => COLS.filter(c => (hasPort || c !== 'port') && (hasCtr || c !== 'country'));

function render() {
  const f = filtered();
  const usd = f.reduce((s, r) => s + (Number(r.value_usd) || 0), 0);
  const kg = f.reduce((s, r) => s + (Number(r.netweight_kg) || 0), 0);
  el('stats').innerHTML =
    `<span><div class="statlab">rows (filtered / fetched)</div><b>${f.length.toLocaleString()} / ${rows.length.toLocaleString()}</b></span>` +
    `<span><div class="statlab">total value (US$)</div><b>${usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</b></span>` +
    `<span><div class="statlab">total net weight (kg)</div><b>${kg.toLocaleString(undefined, { maximumFractionDigits: 0 })}</b></span>`;

  const cap = 1000;
  const show = f.slice(0, cap);
  const cols = activeCols();
  el('tbl').innerHTML = '<tr>' + cols.map(c => `<th class="${NUM.has(c) ? 'num' : ''}">${c}</th>`).join('') + '</tr>' +
    show.map(r => '<tr>' + cols.map(c => {
      let v = r[c] ?? '';
      if (NUM.has(c)) v = Number(v).toLocaleString();
      return `<td class="${NUM.has(c) ? 'num' : ''}">${html(v)}</td>`;
    }).join('') + '</tr>').join('');
  el('tablenote').textContent = f.length > cap ? `Preview limited to ${cap.toLocaleString()} rows - CSV contains all ${f.length.toLocaleString()} filtered rows.` : '';
  renderCharts(f);
}

function fmtV(v) {
  return v >= 1e9 ? (v / 1e9).toFixed(1) + 'B' : v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(0) + 'K' : String(Math.round(v));
}

function barChart(id, data) {
  const max = Math.max(...data.map(d => d[1]), 1);
  el(id).innerHTML = data.map(([name, v]) =>
    `<div class="barrow" title="${html(name)}: US$ ${Math.round(v).toLocaleString()}"><div class="barname">${html(name)}</div><div class="bartrack"><div class="bar" style="width:${Math.max(1, 100 * v / max)}%"></div></div><div class="barval">${fmtV(v)}</div></div>`
  ).join('') || '<div class="mini">No data</div>';
}

function renderCharts(f) {
  const sum = keyf => {
    const m = new Map();
    for (const r of f) {
      const k = keyf(r) || '(blank)';
      m.set(k, (m.get(k) || 0) + (Number(r.value_usd) || 0));
    }
    return m;
  };
  const per = [...sum(r => r.month_id ? `${r.year}-${String(r.month_id).padStart(2, '0')}` : String(r.year)).entries()].sort((a, b) => a[0].localeCompare(b[0]));
  el('t_time').textContent = `Value by ${per[0] && per[0][0].includes('-') ? 'month' : 'year'} (US$)`;
  barChart('c_time', per);
  const top = keyf => [...sum(keyf).entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  el('c_ctr_wrap').style.display = hasCtr ? '' : 'none';
  if (hasCtr) barChart('c_ctr', top(r => r.country));
  barChart('c_hs', top(r => r.hs_code));
  el('c_port_wrap').style.display = hasPort ? '' : 'none';
  if (hasPort) barChart('c_port', top(r => r.port));
}

function downloadCSV() {
  const f = filtered();
  if (!f.length) return;
  const esc = v => {
    v = String(v ?? '');
    return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  };
  const cols = activeCols();
  const csv = '\ufeff' + cols.join(',') + '\n' + f.map(r => cols.map(c => esc(r[c])).join(',')).join('\n');
  const flow = rows[0].flow;
  const years = [...new Set(f.map(r => r.year))].sort();
  const span = years.length > 1 ? years[0] + '-' + years[years.length - 1] : (years[0] || '');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  a.download = `exim_${flow}_${span}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function wire() {
  initBoxes();
  el('apikey').value = localStorage.getItem('bps_api_key') || '';
  el('requestmode').value = localStorage.getItem('bps_request_mode') || 'auto';
  el('savekey').addEventListener('click', () => {
    localStorage.setItem('bps_api_key', el('apikey').value.trim());
    localStorage.setItem('bps_request_mode', el('requestmode').value);
    el('progtext').textContent = 'Settings saved in this browser.';
  });
  el('clearkey').addEventListener('click', () => {
    localStorage.removeItem('bps_api_key');
    el('apikey').value = '';
    el('progtext').textContent = 'API key cleared.';
  });
  el('requestmode').addEventListener('change', () => localStorage.setItem('bps_request_mode', el('requestmode').value));
  el('hsfilter').addEventListener('input', filterChapters);
  document.querySelectorAll('[data-setall]').forEach(btn => btn.addEventListener('click', ev => {
    ev.preventDefault();
    const [id, on] = btn.dataset.setall.split(':');
    setAll(id, on === '1');
  }));
  el('go').addEventListener('click', fetchAll);
  el('cancel').addEventListener('click', () => { cancelled = true; });
  ['fport', 'fctr', 'fhs'].forEach(id => el(id).addEventListener('change', render));
  el('fsearch').addEventListener('input', render);
  el('download').addEventListener('click', downloadCSV);
  loadStaticData();
}

wire();
