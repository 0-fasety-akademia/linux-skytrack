#!/usr/bin/env python3
"""Build data/popularity.json — number of scheduled routes per airport (IATA), used to put the
big airports first in lists (import template, search).

Source: OpenFlights routes.dat (Open Database License), kept in data/src/routes.dat.
Usage: python3 tools/build_popularity.py
"""
import csv
import json
import os
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    c = Counter()
    with open(os.path.join(ROOT, "data", "src", "routes.dat"), encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if len(row) >= 5:
                for code in (row[2], row[4]):
                    if len(code) == 3 and code.isalpha():
                        c[code] += 1
    out = os.path.join(ROOT, "data", "popularity.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(c.most_common()), f, separators=(",", ":"))
    print("written", out, len(c))


if __name__ == "__main__":
    main()
