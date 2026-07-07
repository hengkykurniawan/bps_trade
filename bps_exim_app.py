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
    path = os.path.join(SCRIPT_DIR, "docs", "index.html")
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    year_now = date.today().year
    years = list(range(year_now, DATA_START_YEAR - 1, -1))
    cfg = json.dumps({"years": years, "months": MONTHS, "chapters": HS_CHAPTERS,
                      "hasMaster": MASTER is not None, "isLocalServer": True})
    return html.replace("__CFG__", cfg)


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
