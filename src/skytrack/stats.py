"""Enrich trips with distance/duration and aggregate them by year/month/day."""
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date

from . import geo

from .i18n import IS_PL

if IS_PL:
    MONTHS = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec",
              "sierpień", "wrzesień", "październik", "listopad", "grudzień"]
    MONTHS_GEN = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]
    WEEKDAYS = ["pon", "wt", "śr", "czw", "pt", "sob", "nd"]
    MONTHS_LONG_GEN = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
                       "września", "października", "listopada", "grudnia"]
else:
    MONTHS = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
    MONTHS_GEN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    MONTHS_LONG_GEN = MONTHS


@dataclass
class TripInfo:
    trip: object
    origin: object
    dest: object
    km: float
    minutes: int
    approx: bool
    planned: bool = False

    @property
    def arrival(self):
        """(date, time, estimated?) local at destination, or (None, None, True)."""
        t = self.trip
        if t.arr_time:
            return t.arr_date or t.dep_date, t.arr_time, False
        d, tm = geo.arrival_estimate(t.dep_date, t.dep_time, self.origin.tz, self.minutes, self.dest.tz)
        return d, tm, True

    @property
    def countdown(self):
        return geo.countdown_label(self.trip.dep_date, self.trip.dep_time, self.origin.tz)

    @property
    def year(self):
        return int(self.trip.dep_date[:4])

    @property
    def month(self):
        return int(self.trip.dep_date[5:7])

    @property
    def route(self):
        return f"{self.trip.origin} → {self.trip.dest}"

    def to_js(self):
        t = self.trip
        return {"id": t.id, "from": self.origin.to_js(), "to": self.dest.to_js(),
                "km": round(self.km), "date": t.dep_date, "time": t.dep_time,
                "flight": t.flight_no, "label": f"{t.origin} → {t.dest}", "planned": self.planned,
                "dateLabel": nice_date(t.dep_date)}


def nice_date(d, with_weekday=False):
    try:
        dt = date.fromisoformat(d)
    except ValueError:
        return d
    s = f"{dt.day} {MONTHS_GEN[dt.month - 1]} {dt.year}"
    return f"{WEEKDAYS[dt.weekday()]}, {s}" if with_weekday else s


def enrich(trips, airports):
    out = []
    for t in trips:
        a, b = airports.get(t.origin), airports.get(t.dest)
        if not a or not b:
            continue
        km = geo.distance_km(a.lat, a.lon, b.lat, b.lon)
        real = geo.real_minutes(t.dep_date, t.dep_time, a.tz, t.arr_date or t.dep_date,
                                t.arr_time, b.tz) if t.arr_time else None
        minutes = real if real is not None else geo.estimate_minutes(km)
        out.append(TripInfo(t, a, b, km, minutes, real is None,
                            geo.is_future(t.dep_date, t.dep_time, a.tz)))
    return out


def flown(infos):
    return [i for i in infos if not i.planned]


def planned(infos):
    return sorted([i for i in infos if i.planned], key=lambda i: (i.trip.dep_date, i.trip.dep_time))


def years(infos):
    return sorted({i.year for i in infos}, reverse=True)


def filter_year(infos, year):
    return [i for i in infos if year is None or i.year == year]


def _region(var_names):
    import os
    for var in var_names:
        val = os.environ.get(var, "")
        if "_" in val:
            cc = val.split("_", 1)[1][:2].upper()
            if cc.isalpha() and len(cc) == 2:
                return cc
    return None


# "Formats" region (Ubuntu: Settings → Region & Language → Formats) — set even with an English UI
FORMAT_VARS = ("LC_ALL", "LC_ADDRESS", "LC_TELEPHONE", "LC_MEASUREMENT", "LC_PAPER", "LC_TIME", "LC_MONETARY")


def locale_country():
    """Country from the system locale, e.g. pl_PL.UTF-8 -> 'PL' (None if unknown)."""
    return _region(FORMAT_VARS) or _region(("LC_MESSAGES", "LANG"))


def home_country(infos, setting=None):
    """Country you live in. Order: the user's choice, the regional formats, the Polish system
    language (pl_PL), the origin of your first flight (not 'the most frequent origin', which
    ties on a simple there-and-back trip), and only then the region of an English language
    setting — en_US is often used outside the US."""
    if setting:
        return setting
    cc = _region(FORMAT_VARS)
    if cc:
        return cc
    lang_cc = _region(("LC_MESSAGES", "LANG"))
    if IS_PL and lang_cc:
        return lang_cc
    first = min(infos, key=lambda i: (i.trip.dep_date, i.trip.dep_time), default=None)
    if first:
        return first.origin.cc
    return lang_cc


def visited_countries(infos, home=None):
    """Countries you flew to (arrivals), without the home country, most visited first."""
    out = {}
    for i in sorted(infos, key=lambda x: (x.trip.dep_date, x.trip.dep_time)):
        cc = i.dest.cc
        if cc == home:
            continue
        c = out.setdefault(cc, {"cc": cc, "name": i.dest.country, "visits": [], "airports": []})
        c["visits"].append(i)
        if i.dest.iata not in c["airports"]:
            c["airports"].append(i.dest.iata)
    for c in out.values():
        c["first"] = c["visits"][0].trip.dep_date
        c["last"] = c["visits"][-1].trip.dep_date
    return sorted(out.values(), key=lambda c: (-len(c["visits"]), c["name"]))


def totals(infos, home=None):
    km = sum(i.km for i in infos)
    airports = {i.trip.origin for i in infos} | {i.trip.dest for i in infos}
    countries = {i.dest.cc for i in infos} - {home}
    longest = max(infos, key=lambda i: i.km, default=None)
    return {
        "km": km,
        "flights": len(infos),
        "minutes": sum(i.minutes for i in infos),
        "approx": any(i.approx for i in infos),
        "airports": len(airports),
        "countries": len(countries),
        "destinations": len({i.trip.dest for i in infos}),
        "longest": longest,
        "laps": km / geo.EARTH_CIRCUMFERENCE_KM,
    }


def tree(infos):
    """{year: {month: {day: [TripInfo]}}} sorted newest first."""
    out = OrderedDict()
    for i in sorted(infos, key=lambda x: (x.trip.dep_date, x.trip.dep_time), reverse=True):
        y, m, d = i.year, i.month, i.trip.dep_date
        out.setdefault(y, OrderedDict()).setdefault(m, OrderedDict()).setdefault(d, []).append(i)
    for months in out.values():           # flights within a day: chronological
        for days in months.values():
            for d in days:
                days[d].reverse()
    return out


def chart_series(infos, year):
    """(labels, km values) — per year when year is None, else per month."""
    if year is None:
        ys = sorted({i.year for i in infos})
        if ys:
            ys = list(range(ys[0], ys[-1] + 1))
        return [str(y) for y in ys], [sum(i.km for i in infos if i.year == y) for y in ys]
    vals = [0.0] * 12
    for i in infos:
        if i.year == year:
            vals[i.month - 1] += i.km
    return [m[:3] for m in MONTHS_GEN], vals


def long_date(iso):
    """'2026-11-09' -> '9 listopada 2026' / '9 November 2026'."""
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return f"{d} {MONTHS_LONG_GEN[m - 1]} {y}"
    except (ValueError, AttributeError, IndexError):
        return iso or ""
