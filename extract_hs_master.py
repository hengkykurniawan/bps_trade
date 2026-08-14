#!/usr/bin/env python3
"""Extract every HS classification era from BPS's HS Code Master PDF.

The output is a compact JSON object keyed by the first year of each era. Each
row is stored as ``[code, description]`` so the browser can search it quickly.
"""

import json
import re
from pathlib import Path

from pypdf import PdfReader


SOURCE = Path("hs_master.pdf")
OUTPUT = Path("hs_master.json")

# (era key, label, first page, last page, permitted code lengths)
ERAS = [
    ("1999", "1999-2008", 3, 189, {10}),
    ("2009", "2009-2011", 190, 345, {9}),
    ("2012", "2012-2016", 346, 559, {8, 10}),
    ("2017", "2017-2021", 560, 863, {8}),
    ("2022", "2022-now", 864, 1262, {8}),
]

SKIP_PREFIXES = (
    "No HS Code",
    "HS CODE MASTER",
    "http://www.bps.go.id/exim",
    "https://www.bps.go.id/exim",
    "Page ",
)


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def match_row(line: str, expected: int, lengths: set[int]):
    code_pattern = "|".join(rf"\d{{{length}}}" for length in sorted(lengths, reverse=True))
    for row_number in range(max(1, expected - 3), expected + 4):
        match = re.match(rf"^{row_number}\s*({code_pattern})\s*(.*)$", line)
        if match:
            return row_number, match.group(1), match.group(2)
    return None


def extract_era(reader: PdfReader, first_page: int, last_page: int, lengths: set[int]):
    rows = []
    expected = 1

    for page_number in range(first_page - 1, last_page):
        text = reader.pages[page_number].extract_text() or ""
        for raw_line in text.splitlines():
            line = normalized(raw_line)
            if not line or line.startswith(SKIP_PREFIXES):
                continue

            match = match_row(line, expected, lengths)
            if match:
                row_number, code, description = match
                rows.append([code, description])
                expected = row_number + 1
            elif rows:
                rows[-1][1] = normalized(f"{rows[-1][1]} {line}")

    # A handful of 2012-era rows on PDF page 401 contain a damaged leading
    # zero and the first character of "other" glued into the extracted code.
    for row in rows:
        code, description = row
        if len(code) == 8 and description.startswith("0]"):
            row[0] = "0" + code + description[0]
            row[1] = "o" + description[2:]

    unique = {}
    for code, description in rows:
        description = normalized(description)
        if code not in unique or len(description) > len(unique[code]):
            unique[code] = description
    return sorted(unique.items())


def main():
    reader = PdfReader(SOURCE)
    output = {}

    for key, label, first_page, last_page, lengths in ERAS:
        rows = extract_era(reader, first_page, last_page, lengths)
        if not rows:
            raise RuntimeError(f"No rows extracted for {label}")
        output[key] = rows
        code_lengths = sorted({len(code) for code, _ in rows})
        print(
            f"{label}: {len(rows):,} unique codes; "
            f"code lengths {code_lengths}; first {rows[0][0]}; last {rows[-1][0]}"
        )

    OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
