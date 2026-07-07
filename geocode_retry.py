#!/usr/bin/env python3
"""Second pass for ports geocode_geo.py could not resolve: retry with the
comma-prefix, hyphen/slash parts, and generic suffixes stripped."""
import json
import re

from geocode_geo import query


def candidates(name):
    base = name.split("(")[0].strip()
    out = []
    if "," in base:
        out.append(base.split(",")[0].strip())
    for part in re.split(r"[/-]", base):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    stripped = re.sub(r"\b(BAY|RIVER|ISLAND|PORT)\b", "", base).strip()
    if stripped and stripped not in out:
        out.append(stripped)
    joined = base.replace(" ", "")  # LHOK SEUMAWE -> LHOKSEUMAWE
    if " " in base and joined not in out:
        out.append(joined)
    return out


def main():
    geo = json.load(open("geo.json", encoding="utf-8"))
    ports = json.load(open("ports.json", encoding="utf-8"))
    missing = [p for p in ports if p not in geo["ports"]]
    print(len(missing), "ports to retry")
    still = []
    for name in missing:
        pos = None
        for cand in candidates(name):
            pos = query(f"{cand}, Indonesia", "&countrycodes=id")
            if pos:
                break
        if pos:
            geo["ports"][name] = pos
            print(f"OK   {name!r} -> {pos} (as {cand!r})")
        else:
            still.append(name)
            print(f"MISS {name!r}")
    with open("geo.json", "w", encoding="utf-8") as f:
        json.dump(geo, f, ensure_ascii=False)
    print(f"resolved {len(missing)-len(still)}/{len(missing)}; still missing: {still}")


if __name__ == "__main__":
    main()
