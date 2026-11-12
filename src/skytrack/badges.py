"""Badges (achievements) computed from the flight log on the fly: nothing is stored, so editing or
deleting a flight updates them by itself. Only flown trips count (pass stats.flown(...))."""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from . import geo
from .i18n import _

MOON_KM = 384400

# ISO 3166 country -> continent (Antarctica left out: no airports with scheduled flights)
_CONT = {
    "EU": "AD AL AT AX BA BE BG BY CH CY CZ DE DK EE ES FI FO FR GB GG GI GR HR HU IE IM IS IT JE LI LT LU "
          "LV MC MD ME MK MT NL NO PL PT RO RS RU SE SI SJ SK SM UA VA XK",
    "AS": "AE AF AM AZ BD BH BN BT CN GE HK ID IL IN IQ IR JO JP KG KH KP KR KW KZ LA LB LK MM MN MO MV "
          "MY NP OM PH PK PS QA SA SG SY TH TJ TL TM TR TW UZ VN YE",
    "AF": "AO BF BI BJ BW CD CF CG CI CM CV DJ DZ EG EH ER ET GA GH GM GN GQ GW KE KM LR LS LY MA MG ML "
          "MR MU MW MZ NA NE NG RE RW SC SD SH SL SN SO SS ST SZ TD TG TN TZ UG YT ZA ZM ZW",
    "NA": "AG AI AW BB BL BM BQ BS BZ CA CR CU CW DM DO GD GL GP GT HN HT JM KN KY LC MF MQ MS MX NI PA "
          "PM PR SV SX TC TT US VC VG VI",
    "SA": "AR BO BR CL CO EC FK GF GY PE PY SR UY VE",
    "OC": "AS AU CK FJ FM GU KI MH MP NC NF NR NU NZ PF PG PN PW SB TK TO TV UM VU WF WS",
}
CONTINENT = {cc: cont for cont, ccs in _CONT.items() for cc in ccs.split()}
OLD_WORLD, AMERICAS = {"EU", "AF"}, {"NA", "SA"}


@dataclass
class Badge:
    key: str
    icon: str
    name: str
    desc: str
    target: int
    value: int = 0
    earned_on: str = ""          # ISO date of the flight that earned it

    @property
    def earned(self):
        return bool(self.earned_on)

    @property
    def progress(self):
        return min(1.0, self.value / self.target) if self.target else 1.0


def continent(cc):
    return CONTINENT.get((cc or "").upper())


def _offset_h(tz, date):
    try:
        d = datetime.fromisoformat(date + "T12:00").replace(tzinfo=ZoneInfo(tz or "UTC"))
        return d.utcoffset().total_seconds() / 3600
    except Exception:  # noqa
        return 0.0


def _hour(t):
    try:
        return int((t or "").split(":")[0])
    except ValueError:
        return None


def _norm(s):
    return " ".join((s or "").split()).casefold()


# the rules ------------------------------------------------------------------------------------------
def is_atlantic(i):
    a, b = continent(i.origin.cc), continent(i.dest.cc)
    return (a in OLD_WORLD and b in AMERICAS) or (a in AMERICAS and b in OLD_WORLD)


def crosses_equator(i):
    return i.origin.lat * i.dest.lat < 0


def is_jetlag(i):
    return abs(_offset_h(i.dest.tz, i.trip.dep_date) - _offset_h(i.origin.tz, i.trip.dep_date)) >= 6


def is_night(i):
    h = _hour(i.trip.dep_time)
    return h is not None and (h >= 22 or h < 5)


def definitions():
    """(key, icon, name, description, target, metric) — metric(state) -> current value."""
    km = lambda s: int(s["km"])                                    # noqa: E731
    D = []
    for t, icon in ((1000, "🛫"), (10000, "🌍")):
        D.append((f"km{t}", icon, _('{0} km w powietrzu').format(geo.fmt_km(t).replace(" km", "")),
                  _('Przeleć łącznie {0}').format(geo.fmt_km(t)), t, km))
    D.append(("earth", "🌐", _('Dookoła Ziemi'), _('Przeleć łącznie długość równika (40 075 km)'),
              round(geo.EARTH_CIRCUMFERENCE_KM), km))
    D.append(("moon", "🌙", _('Na Księżyc'), _('Przeleć łącznie odległość do Księżyca (384 400 km)'), MOON_KM, km))
    D.append(("flights1", "✈️", _('Pierwszy lot'), _('Zapisz pierwszy odbyty lot'), 1, lambda s: s["flights"]))
    for n in (10, 50, 100):
        D.append((f"flights{n}", "🎫", _('{0} lotów').format(n), _('Odbądź {0} lotów').format(n), n,
                  lambda s: s["flights"]))
    for n in (5, 10, 25, 50):
        D.append((f"countries{n}", "🗺️", _('{0} krajów').format(n),
                  _('Przyleć do {0} krajów poza krajem zamieszkania').format(n), n, lambda s: len(s["countries"])))
    for n in (10, 25, 50):
        D.append((f"airports{n}", "📍", _('{0} lotnisk').format(n), _('Odwiedź {0} różnych lotnisk').format(n), n,
                  lambda s: len(s["airports"])))
    D.append(("cont2", "🧭", _('Dwa kontynenty'), _('Bądź na 2 kontynentach'), 2, lambda s: len(s["continents"])))
    D.append(("cont4", "🧭", _('Cztery kontynenty'), _('Bądź na 4 kontynentach'), 4, lambda s: len(s["continents"])))
    D.append(("cont6", "🏆", _('Wszystkie kontynenty'),
              _('Bądź na 6 zamieszkanych kontynentach'), 6, lambda s: len(s["continents"])))
    D.append(("atlantic", "🌊", _('Nad Atlantykiem'), _('Leć między Europą lub Afryką a Ameryką'), 1,
              lambda s: s["atlantic"]))
    D.append(("equator", "🌐", _('Przez równik'), _('Leć z jednej półkuli na drugą'), 1, lambda s: s["equator"]))
    D.append(("long", "🛬", _('Długi dystans'), _('Jeden lot co najmniej 5 000 km'), 1, lambda s: s["long"]))
    D.append(("ultra", "🚀", _('Ultra'), _('Jeden lot co najmniej 10 000 km'), 1, lambda s: s["ultra"]))
    D.append(("jetlag", "😴", _('Jet lag'), _('Lot z różnicą czasu co najmniej 6 godzin'), 1, lambda s: s["jetlag"]))
    D.append(("night", "🌃", _('Lot nocny'), _('Wylot między 22:00 a 5:00'), 1, lambda s: s["night"]))
    D.append(("twoday", "⏱️", _('Dwa loty jednego dnia'), _('Dwa odloty tego samego dnia'), 2,
              lambda s: s["max_per_day"]))
    D.append(("loyal", "💺", _('Wierny przewoźnikowi'), _('10 lotów jedną linią lotniczą'), 10,
              lambda s: s["max_airline"]))
    D.append(("planes", "🛩️", _('Kolekcjoner samolotów'), _('Leć 5 różnymi typami samolotów'), 5,
              lambda s: len(s["aircraft"])))
    D.append(("months", "📅", _('Cały kalendarz'), _('Loty w każdym z 12 miesięcy (w dowolnych latach)'), 12,
              lambda s: len(s["months"])))
    return D


def compute(flown, home=None):
    """flown: TripInfo list of flown trips. Returns the badge list; earned_on is the date of the flight
    that reached the target (scanning the log in order)."""
    state = {"km": 0.0, "flights": 0, "countries": set(), "airports": set(), "continents": set(),
             "atlantic": 0, "equator": 0, "long": 0, "ultra": 0, "jetlag": 0, "night": 0,
             "max_per_day": 0, "max_airline": 0, "aircraft": set(), "months": set()}
    per_day, per_airline = {}, {}
    defs = definitions()
    badges = [Badge(k, icon, name, desc, target) for k, icon, name, desc, target, _m in defs]
    for i in sorted(flown, key=lambda x: (x.trip.dep_date, x.trip.dep_time or "")):
        t = i.trip
        state["km"] += i.km
        state["flights"] += 1
        if i.dest.cc != home:
            state["countries"].add(i.dest.cc)
        state["airports"] |= {t.origin, t.dest}
        state["continents"] |= {c for c in (continent(i.origin.cc), continent(i.dest.cc)) if c}
        state["atlantic"] += is_atlantic(i)
        state["equator"] += crosses_equator(i)
        state["long"] += i.km >= 5000
        state["ultra"] += i.km >= 10000
        state["jetlag"] += is_jetlag(i)
        state["night"] += is_night(i)
        per_day[t.dep_date] = per_day.get(t.dep_date, 0) + 1
        state["max_per_day"] = max(state["max_per_day"], per_day[t.dep_date])
        if _norm(t.airline):
            per_airline[_norm(t.airline)] = per_airline.get(_norm(t.airline), 0) + 1
            state["max_airline"] = max(state["max_airline"], per_airline[_norm(t.airline)])
        if _norm(t.aircraft):
            state["aircraft"].add(_norm(t.aircraft))
        state["months"].add(t.dep_date[5:7])
        for b, d in zip(badges, defs):
            if not b.earned and d[5](state) >= b.target:
                b.earned_on = t.dep_date
    for b, d in zip(badges, defs):
        b.value = d[5](state)
    return badges
