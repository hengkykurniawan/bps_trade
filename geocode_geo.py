#!/usr/bin/env python3
"""One-time build of geo.json: coordinates for every BPS port and partner
country, geocoded via OpenStreetMap Nominatim (1 req/sec per usage policy).
Inputs: ports.json (from the app) and countries_raw.json (harvested from the
API). Ports are geocoded within Indonesia only."""
import json
import time
import urllib.parse
import urllib.request

UA = "bps-exim-local-app/1.0 (one-time geocoding of port/country names)"

# BPS spellings that Nominatim won't resolve as-is
COUNTRY_FIX = {
    "ANTARTICA": "Antarctica",
    "COTE DIVOIRE": "Ivory Coast",
    "GERMANY, FED. REP. OF": "Germany",
    "IRAN (ISLAMIC REPUBLIC OF)": "Iran",
    "KOREA, DEM. PEOPLES REP.": "North Korea",
    "KOREA, REPUBLIC OF": "South Korea",
    "LAO PEOPLES DEM. REP.": "Laos",
    "LIBYAN ARAB JAMAHIRIYA": "Libya",
    "MICRONESIA, FED. STATES OF": "Federated States of Micronesia",
    "MOLDOVA, REPUBLIC OF": "Moldova",
    "REP. OF MACEDONIA": "North Macedonia",
    "RUSSIA FEDERATION": "Russia",
    "SYRIA ARAB REPUBLIC": "Syria",
    "TANZANIA, UNITED REP. OF": "Tanzania",
    "EAST TIMOR": "Timor-Leste",
    "PALESTINA": "Palestine",
    "CHRISTMAS ISLANDS": "Christmas Island",
    "NORFOLK ISLANDS": "Norfolk Island",
    "FAEROE ISLANDS": "Faroe Islands",
    "U.S MINOR OUTLYING ISLAND": "United States Minor Outlying Islands",
    "U.S. VIRGIN ISLANDS": "United States Virgin Islands",
    "SOUTH GEORGIA AND THE SOUTH SA": "South Georgia and the South Sandwich Islands",
    "NETHERLANDS ANTILLES": "Curacao",
    "DEMOCRATIC REP. OF THE CONGO": "Democratic Republic of the Congo",
    "GUINEA BISSAU": "Guinea-Bissau",
    "SAINT MARTIN (FRENCH PART)": "Saint-Martin",
    "SINT MAARTEN (DUTCH PART)": "Sint Maarten",
    "VIRGIN ISLANDS (BRITISH)": "British Virgin Islands",
    "WALLIS AND FUTUNA ISLANDS": "Wallis and Futuna",
    "PITCAIRN": "Pitcairn Islands",
    "SWAZILAND": "Eswatini",
    "SAINT HELENA": "Saint Helena",
    "CONGO": "Republic of the Congo",
}


def query(q, extra=""):
    url = ("https://nominatim.openstreetmap.org/search?format=json&limit=1"
           f"&q={urllib.parse.quote(q)}{extra}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            hits = json.loads(r.read())
    except Exception:
        hits = []
    time.sleep(1.1)
    return [round(float(hits[0]["lat"]), 4), round(float(hits[0]["lon"]), 4)] if hits else None


def main():
    ports = json.load(open("ports.json", encoding="utf-8"))
    countries = json.load(open("countries_raw.json", encoding="utf-8"))
    geo = {"ports": {}, "countries": {}, "indonesia": [-2.5, 118.0]}
    log = open("geocode.log", "w", encoding="utf-8")

    def note(msg):
        log.write(msg + "\n"); log.flush(); print(msg)

    for i, name in enumerate(countries):
        q = COUNTRY_FIX.get(name, name.title())
        pos = query(q)
        if pos:
            geo["countries"][name] = pos
        else:
            note(f"MISS country {name!r} (tried {q!r})")
        if i % 25 == 0:
            note(f"...countries {i}/{len(countries)}")

    for i, name in enumerate(ports):
        # 'SOEKARNO-HATTA (U)' -> 'SOEKARNO-HATTA'; 'KABIL/PANAU' -> try both parts
        base = name.split("(")[0].strip()
        pos = None
        for cand in [base] + [p.strip() for p in base.split("/") if p.strip()]:
            pos = query(f"{cand}, Indonesia", "&countrycodes=id")
            if pos:
                break
        if pos:
            geo["ports"][name] = pos
        else:
            note(f"MISS port {name!r}")
        if i % 25 == 0:
            note(f"...ports {i}/{len(ports)}")

    with open("geo.json", "w", encoding="utf-8") as f:
        json.dump(geo, f, ensure_ascii=False)
    note(f"DONE: {len(geo['countries'])}/{len(countries)} countries, "
         f"{len(geo['ports'])}/{len(ports)} ports -> geo.json")


if __name__ == "__main__":
    main()
