#!/usr/bin/env python3
"""Build data/airlines.json — IATA airline code -> [ICAO code, name, radio callsign].

Source: OpenFlights airlines.dat (Open Database License, https://openflights.org/data.php),
kept in data/src/airlines.dat. Active airlines win over defunct ones with the same IATA code.

Usage: python3 tools/build_airlines.py
"""
import csv
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "data", "src", "airlines.dat")
OUT = os.path.join(ROOT, "data", "airlines.json")


# OpenFlights is no longer updated: current codes of carriers popular from Poland / Europe
OVERRIDES = {
    "E4": ["ENT", "Enter Air", "ENTER"], "QS": ["TVS", "Smartwings", "SKYTRAVEL"],
    "RR": ["RYS", "Buzz", "MAGIC SUN"], "W4": ["WMT", "Wizz Air Malta", "WIZZ AIR"],
    "W9": ["WUK", "Wizz Air UK", "WIZZ GO"], "5W": ["WAZ", "Wizz Air Abu Dhabi", "WIZZ SKY"],
    "XC": ["CAI", "Corendon Airlines", "CORENDON"], "XQ": ["SXS", "SunExpress", "SUNEXPRESS"],
    "EW": ["EWG", "Eurowings", "EUROWINGS"], "LS": ["EXS", "Jet2.com", "CHANNEX"],
    "BT": ["BTI", "airBaltic", "AIRBALTIC"], "AY": ["FIN", "Finnair", "FINNAIR"],
    "NO": ["NOS", "Neos", "MOONFLOWER"], "X3": ["TUI", "TUIfly", "TUI JET"],
    "BY": ["TOM", "TUI Airways", "TOMSON"], "DE": ["CFG", "Condor", "CONDOR"],
    "FZ": ["FDB", "flydubai", "SKY DUBAI"], "OE": ["LDM", "Lauda Europe", "LAUDA MOTION"],
    "PQ": ["SQP", "SkyUp Airlines", "SKYUP"], "GQ": ["SEH", "Sky Express", "AIR CRETE"],
    "V7": ["VOE", "Volotea", "VOLOTEA"], "VY": ["VLG", "Vueling", "VUELING"],
    "HV": ["TRA", "Transavia", "TRANSAVIA"], "TO": ["TVF", "Transavia France", "FRANCE SOLEIL"],
    "U2": ["EZY", "easyJet", "EASY"], "5F": ["FIA", "FlyOne", "FLY ONE"],
    "H4": ["HYS", "HiSky Europe", "SKY FLOW"], "XR": ["CXI", "Corendon Airlines Europe", "TOURISTER"],
    "A3": ["AEE", "Aegean Airlines", "AEGEAN"], "OA": ["OAL", "Olympic Air", "OLYMPIC"],
    "PC": ["PGT", "Pegasus Airlines", "SUNTURK"], "AJ": ["AZS", "AJet", "ANATOLIAN"],
    "G9": ["ABY", "Air Arabia", "ARABIA"], "MS": ["MSR", "EgyptAir", "EGYPTAIR"],
    "DY": ["NOZ", "Norwegian", "NORSEMAN"], "D8": ["IBK", "Norwegian Air International", "NORTRANS"],
    "SK": ["SAS", "SAS", "SCANDINAVIAN"], "4U": ["GWI", "Germanwings", "GERMANWINGS"],
    "LG": ["LGL", "Luxair", "LUXAIR"], "OK": ["CSA", "Czech Airlines", "CSA"],
    "JU": ["ASL", "Air Serbia", "AIR SERBIA"], "RO": ["ROT", "TAROM", "TAROM"],
    "FB": ["LZB", "Bulgaria Air", "FLYING BULGARIA"], "OU": ["CTN", "Croatia Airlines", "CROATIA"],
    "ZB": ["ABN", "Air Albania", "AIR ALBANIA"], "KM": ["KMM", "KM Malta Airlines", "KOMALTA"],
    "UX": ["AEA", "Air Europa", "EUROPA"], "IB": ["IBE", "Iberia", "IBERIA"],
    "TP": ["TAP", "TAP Air Portugal", "AIR PORTUGAL"], "AZ": ["ITY", "ITA Airways", "ITARROW"],
    "SN": ["BEL", "Brussels Airlines", "BEELINE"], "EI": ["EIN", "Aer Lingus", "SHAMROCK"],
}


def main():
    best = {}
    with open(SRC, encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if len(row) < 8:
                continue
            _id, name, _alias, iata, icao, callsign, _country, active = row[:8]
            iata, icao = iata.strip().upper(), icao.strip().upper()
            if len(iata) != 2 or iata in ("\\N", "--") or not icao.isalpha() or len(icao) != 3:
                continue
            score = (active == "Y", )
            if iata not in best or score > best[iata][0]:
                cs = "" if callsign in ("\\N", "") else callsign.strip()
                best[iata] = (score, [icao, name.strip(), cs])
    data = {k: v[1] for k, v in sorted(best.items())}
    data.update(OVERRIDES)
    data = dict(sorted(data.items()))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("written", OUT, len(data), "airlines")


if __name__ == "__main__":
    main()
