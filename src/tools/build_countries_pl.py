#!/usr/bin/env python3
"""Build data/countries_pl.json (ISO code -> Polish country name) from CLDR via Babel.

Usage: pip install babel && python3 tools/build_countries_pl.py
"""
import json
import os

from babel import Locale

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
data = json.load(open(os.path.join(ROOT, "data", "airports.json"), encoding="utf-8"))
pl = Locale("pl").territories
codes = sorted({a[4] for a in data["airports"]})
out = {c: pl.get(c, data["countries"].get(c, c)) for c in codes}
with open(os.path.join(ROOT, "data", "countries_pl.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print(f"{len(out)} countries")
