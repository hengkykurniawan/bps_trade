#!/usr/bin/env python3
"""One-time extraction of hs_master.json from BPS's 'HSCode Master BPS.pdf'
(fetched from the Wayback Machine; the live URL is Cloudflare-blocked).
Eras keyed by first data year the app should use them for."""
import json
import re
from pypdf import PdfReader

# (era_key, first_page, last_page) 1-based, from the PDF's list of contents
ERAS = [("2012", 346, 559), ("2017", 560, 863), ("2022", 864, 1262)]

r = PdfReader("hs_master.pdf")
out = {}
for era, p0, p1 in ERAS:
    codes = []
    n = 1  # row counter restarts per era; above 999 it is glued to the code
    for pno in range(p0 - 1, p1):
        for line in r.pages[pno].extract_text().splitlines():
            line = line.strip()
            if not line or line.startswith("Page ") or line.startswith("No HS Code"):
                continue
            m = re.match(rf"^{n}\s*(\d{{10}}|\d{{8}})\s*(.*)$", line)
            if not m:  # resync in case a row was skipped by extraction
                m2 = re.match(r"^(\d{1,5})\s+(\d{10}|\d{8})\s+(\S.*)$", line)
                if m2 and abs(int(m2.group(1)) - n) <= 3:
                    n = int(m2.group(1))
                    m = re.match(rf"^{n}\s*(\d{{10}}|\d{{8}})\s*(.*)$", line)
            if m:
                codes.append([m.group(1), m.group(2).strip()])
                n += 1
            elif codes:  # wrapped description continuation
                codes[-1][1] = (codes[-1][1] + " " + line).strip()
    # 8 rows on the 2012-era page 401 are glitched in the PDF itself:
    # "307193000]th ..." = code missing its leading 0, desc 'oth' mangled.
    for c in codes:
        if len(c[0]) == 8 and c[1].startswith("0]"):
            c[0] = "0" + c[0] + c[1][0]
            c[1] = "o" + c[1][2:]
    seen = {}
    for code, desc in codes:  # keep the longest description per code
        if code not in seen or len(desc) > len(seen[code]):
            seen[code] = desc
    out[era] = sorted(seen.items())
    chapters = {c[0][:2] for c in codes}
    print(f"era {era}: {len(codes)} codes, {len(chapters)} chapters, "
          f"code len {sorted({len(c[0]) for c in codes})}, "
          f"sample {codes[0]}, missing chapters "
          f"{sorted(set(f'{i:02d}' for i in range(1,98) if i != 77) - chapters)}")

with open("hs_master.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print("wrote hs_master.json")
