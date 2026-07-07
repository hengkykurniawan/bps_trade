#!/usr/bin/env python3
"""
BPS Foreign Trade (ekspor-impor) -> CSV exporter.

Pulls HS-code level export/import data from the `dataexim` endpoint of
webapi.bps.go.id (the API behind the website's ekspor-impor pages) and
writes a tidy, one-row-per-value CSV.

  # annual exports of HS chapter 01 (live animals), 2023
  python bps_exim.py get --flow export --hs 01 --year 2023

  # monthly imports, several chapters, several years
  python bps_exim.py get --flow import --hs 01 27 --year 2022 2023 --monthly

  # full HS code (8-digit BTKI, e.g. crude palm oil)
  python bps_exim.py get --flow export --hs 15111000 --year 2023

  # only some months
  python bps_exim.py get --flow export --hs 01 --year 2023 --monthly --month 1 2 3

CSV columns:
  flow, year, month_id, month, hs_code, hs_desc, port, country,
  value_usd, netweight_kg

port = pelabuhan keluar/masuk barang; country = negara tujuan (export)
or negara asal (import).

HS level is auto-detected from the code length: 2 digits -> jenishs=1
(chapter), longer -> jenishs=2 (full code, must match BPS's HS master
for that year: https://www.bps.go.id/assets/docs/HSCode%20Master%20BPS.pdf).

API key is read from `.bps_key` next to this script (or pass --key).
"""

import argparse
import csv
import gzip
import json
import os
import re
import sys
import time
import urllib.request

BASE = "https://webapi.bps.go.id/v1/api/dataexim"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

FLOW = {"export": 1, "import": 2}


def load_key(cli_key):
    if cli_key:
        return cli_key.strip()
    path = os.path.join(SCRIPT_DIR, ".bps_key")
    if os.path.exists(path):
        return open(path).read().strip()
    sys.exit("No API key: put it in .bps_key next to this script or pass --key.")


def http_json(url, retries=4):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url}\n  {last}")


def split_bracketed(s):
    """'[01] Live animals' -> ('01', 'Live animals'); pass through otherwise."""
    m = re.match(r"\[([^\]]*)\]\s*(.*)", s or "")
    return (m.group(1), m.group(2)) if m else ("", s or "")


def fetch_exim(flow, hs_codes, year, month, key):
    """hs_codes: list of codes at the SAME level (all 2-digit or all full).
    The API accepts up to 20 ';'-separated codes per request."""
    jenishs = 1 if len(hs_codes[0]) <= 2 else 2
    periode = 1 if month else 2
    url = (f"{BASE}/sumber/{FLOW[flow]}/periode/{periode}"
           f"/kodehs/{'%3B'.join(hs_codes)}"
           f"/jenishs/{jenishs}/tahun/{year}/bulan/{month or 1}/key/{key}")
    d = http_json(url)
    if d.get("status") == "Error":
        raise RuntimeError(f"BPS: {d.get('message', 'unknown error')}")
    if d.get("data-availability") != "available":
        return None
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


def cmd_get(args, key):
    months = [None]
    if args.monthly:
        months = args.month or list(range(1, 13))

    # one request carries at most 20 HS codes, all at a single level,
    # so batch 2-digit chapters and full codes separately, 20 per request
    chapters = [h for h in args.hs if len(h) <= 2]
    full = [h for h in args.hs if len(h) > 2]
    batches = [lst[i:i + 20] for lst in (chapters, full) if lst
               for i in range(0, len(lst), 20)]

    all_rows = []
    for batch in batches:
        for year in args.year:
            for month in months:
                rows = fetch_exim(args.flow, batch, year, month, key)
                tag = (f"{args.flow} hs {','.join(batch)} {year}"
                       + (f"-{month:02d}" if month else ""))
                if rows is None:
                    print(f"  {tag}: no data")
                    continue
                print(f"  {tag}: {len(rows)} rows")
                all_rows.extend(rows)

    if not all_rows:
        print("Nothing to write.")
        return

    if args.out_file:
        fname = args.out_file
    else:
        span = f"{args.year[0]}" if len(args.year) == 1 else f"{args.year[0]}-{args.year[-1]}"
        gran = "monthly" if args.monthly else "annual"
        fname = f"exim_{args.flow}_hs{'-'.join(args.hs)}_{span}_{gran}.csv"
    if args.gzip and not fname.endswith(".gz"):
        fname += ".gz"
    path = fname if os.path.isabs(fname) else os.path.join(args.out, fname)

    opener = (lambda p: gzip.open(p, "wt", newline="", encoding="utf-8-sig")) if args.gzip \
        else (lambda p: open(p, "w", newline="", encoding="utf-8-sig"))
    with opener(path) as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader(); w.writerows(all_rows)
    size = os.path.getsize(path)
    print(f"\nWrote {len(all_rows)} rows -> {path}  ({size/1024:.0f} KB)")


def main():
    ap = argparse.ArgumentParser(description="BPS Foreign Trade (dataexim) -> CSV.")
    ap.add_argument("--out", default=SCRIPT_DIR, help="output base folder")
    ap.add_argument("--key")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pg = sub.add_parser("get", help="export data to CSV")
    pg.add_argument("--flow", required=True, choices=["export", "import"])
    pg.add_argument("--hs", required=True, nargs="+",
                    help="HS code(s): 2-digit chapter or full BTKI code")
    pg.add_argument("--year", required=True, nargs="+")
    pg.add_argument("--monthly", action="store_true",
                    help="monthly detail (default: annual totals)")
    pg.add_argument("--month", type=int, nargs="+", metavar="1-12",
                    help="with --monthly: only these months (default: all 12)")
    pg.add_argument("--gzip", action="store_true", help="write compact .csv.gz")
    pg.add_argument("--out-file", help="explicit output filename")

    args = ap.parse_args()
    key = load_key(args.key)
    cmd_get(args, key)


if __name__ == "__main__":
    main()
