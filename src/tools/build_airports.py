#!/usr/bin/env python3
"""Build data/airports.json from OurAirports CSV (public domain).

Usage: build_airports.py airports.csv countries.csv out.json
Keeps airports that have an IATA code and are large/medium/small airports
(heliports, seaplane bases and closed fields are dropped). Adds the IANA
time zone computed from coordinates (timezonefinder, build-time only).
"""
import csv
import json
import sys

from timezonefinder import TimezoneFinder

KEEP_TYPES = {"large_airport", "medium_airport", "small_airport"}
RANK = {"large_airport": 3, "medium_airport": 2, "small_airport": 1}


def main(airports_csv, countries_csv, out_path):
    countries = {}
    with open(countries_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            countries[row["code"]] = row["name"]

    tf = TimezoneFinder()
    rows = []
    with open(airports_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            iata = (r.get("iata_code") or "").strip().upper()
            if r["type"] not in KEEP_TYPES or len(iata) != 3 or not iata.isalpha():
                continue
            # small fields only if they have scheduled service
            if r["type"] == "small_airport" and r.get("scheduled_service") != "yes":
                continue
            lat, lon = float(r["latitude_deg"]), float(r["longitude_deg"])
            tz = tf.timezone_at(lat=lat, lng=lon) or tf.closest_timezone_at(lat=lat, lng=lon) or "UTC"
            icao = (r.get("icao_code") or r.get("gps_code") or r["ident"]).strip().upper()
            rows.append([
                iata, icao, r["name"].strip(), (r.get("municipality") or "").strip(),
                r["iso_country"], round(lat, 5), round(lon, 5), tz, RANK[r["type"]],
            ])

    # When an IATA code repeats, keep the most important airport.
    best = {}
    for row in rows:
        if row[0] not in best or row[8] > best[row[0]][8]:
            best[row[0]] = row
    data = {
        "fields": ["iata", "icao", "name", "city", "cc", "lat", "lon", "tz", "rank"],
        "countries": countries,
        "airports": sorted(best.values(), key=lambda x: x[0]),
        "source": "OurAirports (public domain), https://ourairports.com/data/",
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(best)} airports -> {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:4])

