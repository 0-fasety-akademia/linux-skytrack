"""Offline airport database (OurAirports, public domain) with search."""
import json
import os
import unicodedata

from .i18n import IS_PL
from dataclasses import dataclass


@dataclass(frozen=True)
class Airport:
    iata: str
    icao: str
    name: str
    city: str
    cc: str
    country: str
    lat: float
    lon: float
    tz: str
    rank: int

    @property
    def label(self):
        city = f"{self.city}, " if self.city and self.city not in self.name else ""
        return f"{self.iata} – {city}{self.name}"

    @property
    def short(self):
        return self.city or self.name

    def to_js(self):
        return {"iata": self.iata, "icao": self.icao, "name": self.name, "city": self.city,
                "country": self.country, "lat": self.lat, "lon": self.lon, "tz": self.tz}


# Polish names of popular destinations, so "Londyn" or "Nowy Jork" also match.
CITY_PL = {
    "London": "Londyn", "Paris": "Paryż", "Rome": "Rzym", "Milan": "Mediolan",
    "Munich": "Monachium", "Copenhagen": "Kopenhaga", "Stockholm": "Sztokholm",
    "Vienna": "Wiedeń", "Athens": "Ateny", "Lisbon": "Lizbona", "Brussels": "Bruksela",
    "New York": "Nowy Jork", "Washington": "Waszyngton", "Beijing": "Pekin",
    "Tokyo": "Tokio", "Cairo": "Kair", "Moscow": "Moskwa", "Warsaw": "Warszawa",
    "Cracow": "Kraków", "Kraków": "Kraków", "Venice": "Wenecja", "Naples": "Neapol",
    "Florence": "Florencja", "Geneva": "Genewa", "Zurich": "Zurych", "Cologne": "Kolonia",
    "Frankfurt am Main": "Frankfurt", "Nuremberg": "Norymberga", "Dresden": "Drezno",
    "Seville": "Sewilla", "Valencia": "Walencja", "The Hague": "Haga", "Edinburgh": "Edynburg",
    "Dublin": "Dublin", "Reykjavik": "Rejkiawik", "Helsinki": "Helsinki", "Vilnius": "Wilno",
    "Kyiv": "Kijów", "Lviv": "Lwów", "Bucharest": "Bukareszt", "Belgrade": "Belgrad",
    "Larnaca": "Larnaka", "Heraklion": "Heraklion", "Rhodes": "Rodos", "Corfu": "Korfu",
    "Crete": "Kreta", "Sicily": "Sycylia", "Tenerife": "Teneryfa", "Hurghada": "Hurghada",
    "Mexico City": "Meksyk", "Singapore": "Singapur", "Jerusalem": "Jerozolima",
    "Lisboa": "Lizbona", "Kerkyra (Corfu)": "Korfu", "Heraklion": "Heraklion", "Chania": "Chania", "Dubai": "Dubaj", "Prague": "Praga", "Istanbul": "Stambuł",
    "Riga": "Ryga", "Palma De Mallorca": "Majorka", "Gothenburg": "Göteborg",
    "Hanover": "Hanower", "Brunswick": "Brunszwik", "Zagreb": "Zagrzeb", "Bratislava": "Bratysława",
    "Tbilisi": "Tbilisi", "Antwerp": "Antwerpia", "Algiers": "Algier", "Havana": "Hawana", "Wien": "Wiedeń", "München": "Monachium",
}


# Main airport of multi-airport cities, preferred when a city name is typed.
HUBS = {"LHR", "JFK", "CDG", "FCO", "MXP", "HND", "ICN", "PEK", "PVG", "IST", "SVO", "ORD",
        "IAD", "YYZ", "GRU", "EZE", "BKK", "KIX", "TPE", "DXB", "SYD", "MEL", "ARN", "OSL",
        "BCN", "MAD", "BER", "WAW", "KRK", "GDN", "LIS", "ATH", "VIE", "ZRH", "AMS", "FRA",
        "MUC", "BRU", "DUB", "CPH", "HEL", "PRG", "BUD", "OTP", "SOF", "MIA", "LAX", "SFO",
        "EWR", "BOS", "DOH", "AUH", "SIN", "KUL", "DEL", "BOM", "CAI", "JNB", "MEX", "YUL"}


# Holiday names people type in Polish (island / region / country) -> airport codes, search only.
# OurAirports gives the municipality, which is sometimes a suburb: show the city people know.
CITY_FIX = {
    "ATH": "Athens", "MXP": "Milan", "BGY": "Bergamo", "LIN": "Milan", "CDG": "Paris", "ORY": "Paris",
    "BVA": "Paris", "STN": "London", "LTN": "London", "NCE": "Nice", "OSL": "Oslo", "HEL": "Helsinki",
    "BRU": "Brussels", "CRL": "Brussels", "KRK": "Kraków", "WMI": "Warsaw", "RZE": "Rzeszów", "SZZ": "Szczecin",
    "KBP": "Kyiv", "TIA": "Tirana", "OTP": "Bucharest", "SAW": "Istanbul", "CHQ": "Chania", "KGS": "Kos",
    "JTR": "Santorini", "LPA": "Gran Canaria", "EFL": "Kefalonia", "IBZ": "Ibiza", "KEF": "Reykjavík",
    "TFS": "Tenerife", "TFN": "Tenerife", "NRT": "Tokyo", "HND": "Tokyo", "EWR": "Newark",
}

SEARCH_ALIASES = {
    "ATH": "ateny", "OTP": "bukareszt", "KBP": "kijow", "BRU": "bruksela", "CRL": "bruksela",
    "CFU": "korfu", "HER": "kreta", "CHQ": "kreta", "KGS": "kos", "ZTH": "zakintos zakynthos",
    "JMK": "mykonos", "JTR": "santorini", "RHO": "rodos", "EFL": "kefalonia", "PVK": "lefkada preweza",
    "SKG": "saloniki", "PMI": "majorka", "IBZ": "ibiza", "TFS": "teneryfa", "TFN": "teneryfa",
    "LPA": "gran canaria", "FUE": "fuerteventura", "ACE": "lanzarote", "CTA": "sycylia katania",
    "PMO": "sycylia palermo", "OLB": "sardynia", "CAG": "sardynia", "MLA": "malta", "LCA": "cypr",
    "PFO": "cypr", "AYT": "antalya turcja", "DLM": "dalaman turcja", "BJV": "bodrum turcja",
    "HRG": "hurghada egipt", "SSH": "szarm el-szejk egipt", "RMF": "marsa alam egipt",
    "TIA": "tirana albania", "DBV": "dubrownik chorwacja", "SPU": "split chorwacja",
    "ZAD": "zadar chorwacja", "FNC": "madera", "PDL": "azory", "AGP": "malaga costa del sol",
    "ALC": "alicante costa blanca", "FAO": "faro algarve", "NAP": "neapol", "BRI": "bari apulia",
    "MLE": "malediwy", "DPS": "bali", "HKT": "phuket tajlandia", "PUJ": "punta cana dominikana",
}


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace("ł", "l")


class AirportDB:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        countries = data.get("countries", {})
        try:
            with open(os.path.join(os.path.dirname(path), "countries_pl.json"), encoding="utf-8") as f:
                self.countries_pl = json.load(f) if IS_PL else {}
        except (OSError, ValueError):
            self.countries_pl = {}
        self.countries_en = countries
        try:
            with open(os.path.join(os.path.dirname(path), "popularity.json"), encoding="utf-8") as f:
                self.popularity = json.load(f)     # scheduled routes per airport (OpenFlights)
        except (OSError, ValueError):
            self.popularity = {}
        self.by_iata = {}
        self.by_icao = {}
        self._index = []
        for iata, icao, name, city, cc, lat, lon, tz, rank in data["airports"]:
            city = CITY_FIX.get(iata, city)
            en = countries.get(cc, cc)
            ap = Airport(iata, icao, name, city, cc, self.countries_pl.get(cc, en), lat, lon, tz, rank)
            self.by_iata[iata] = ap
            self.by_icao.setdefault(icao, ap)
            pl = CITY_PL.get(city, "")
            alias = SEARCH_ALIASES.get(iata, "")
            self._index.append((ap, _norm(f"{city} {pl} {alias} {name} {en} {ap.country}"),
                                _norm(f"{pl} {alias}")))

    def country_name(self, cc):
        return self.countries_pl.get(cc) or self.countries_en.get(cc, cc)

    def get(self, code):
        if not code:
            return None
        code = code.strip().upper()
        return self.by_iata.get(code) or self.by_icao.get(code)

    def search(self, query, limit=8):
        q = _norm(query.strip())
        if not q:
            return []
        scored = []
        for ap, hay, pl in self._index:
            if pl and q in pl.split():            # exact holiday name: 'kos', 'kreta', 'cypr'
                score = 102                        # (beats Sihanoukville's IATA code KOS)
            elif ap.iata.lower() == q:
                score = 100
            elif ap.icao.lower() == q:
                score = 90
            elif _norm(ap.city).startswith(q) or (pl and any(w.startswith(q) for w in [pl] + pl.split())):
                score = 60
            elif hay.startswith(q) or f" {q}" in f" {hay}":
                score = 40
            elif len(q) >= 3 and q in hay:
                score = 20
            else:
                continue
            pop = self.popularity.get(ap.iata, 0)
            scored.append((score + ap.rank * 5 + (4 if ap.iata in HUBS else 0) + min(4, pop // 100), ap))
        scored.sort(key=lambda x: (-x[0], -self.popularity.get(x[1].iata, 0), x[1].iata))
        return [ap for _, ap in scored[:limit]]


def default_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "..", "data", "airports.json"),
              "/usr/share/linux-skytrack/data/airports.json"):
        if os.path.exists(p):
            return os.path.abspath(p)
    raise FileNotFoundError("airports.json not found")


def flag(cc):
    """Emoji flag from an ISO 3166 code ('PL' -> 🇵🇱)."""
    if not cc or len(cc) != 2 or not cc.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc.upper())
