"""Free community ADS-B networks (no API key, no daily credits) and route lookup.

Live positions: adsb.lol, with airplanes.live and adsb.fi as fall-backs — all three answer in the
ADS-B Exchange v2 format ({"ac": [...]} with hex, flight, r, t, alt_baro, gs, track, baro_rate,
lat, lon, seen, seen_pos). Routes (from → to for a callsign): adsbdb.com.

Be gentle: the networks are run by volunteers. SkyTrack asks at most every 10 s for the map
and once per poll for a tracked flight, and identifies itself with its User-Agent.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from gi.repository import GLib

from . import db
from .version import REPO_URL, VERSION

USER_AGENT = f"linux-skytrack/{VERSION} (+{REPO_URL})"

# name, base url, path templates (callsign, hex, around)
PROVIDERS = [
    ("adsb.lol", os.environ.get("SKYTRACK_ADSBLOL_URL", "https://api.adsb.lol/v2"),
     "/callsign/{cs}", "/hex/{hex}", "/lat/{lat}/lon/{lon}/dist/{nm}"),
    ("airplanes.live", os.environ.get("SKYTRACK_AIRPLANESLIVE_URL", "https://api.airplanes.live/v2"),
     "/callsign/{cs}", "/hex/{hex}", "/point/{lat}/{lon}/{nm}"),
    ("adsb.fi", os.environ.get("SKYTRACK_ADSBFI_URL", "https://opendata.adsb.fi/api/v2"),
     "/callsign/{cs}", "/hex/{hex}", "/lat/{lat}/lon/{lon}/dist/{nm}"),
]
ROUTE_URL = os.environ.get("SKYTRACK_ADSBDB_URL", "https://api.adsbdb.com/v0") + "/callsign/{cs}"
# tar1090's route services (VRS standing data + plausibility check): POST {"planes": [...]}
ROUTESET_URLS = [u for u in (os.environ.get("SKYTRACK_ROUTESET_URL", ""),
                             "https://adsb.im/api/0/routeset",
                             "https://api.adsb.lol/api/0/routeset") if u]
if os.environ.get("SKYTRACK_ROUTESET_URL"):
    ROUTESET_URLS = [os.environ["SKYTRACK_ROUTESET_URL"]]
NOT_AIRCRAFT_TYPES = {"TWR", "GND", "GRND", "SERV", "EMER", "BALL"}
MAX_NM = 250


class AdsbError(Exception):
    pass


def _get(url, timeout=15, body=None):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise AdsbError(f"HTTP {e.code}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise AdsbError(str(e)) from e


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_state(a, now_s=None):
    """ADSBx-v2 aircraft dict -> live.State (or None without a position)."""
    from .live import State
    lat, lon = _num(a.get("lat")), _num(a.get("lon"))
    if lat is None or lon is None:
        lp = a.get("lastPosition") or {}
        lat, lon = _num(lp.get("lat")), _num(lp.get("lon"))
        if lat is None or lon is None:
            return None
    alt = a.get("alt_baro")
    on_ground = alt == "ground"
    alt_ft = _num(a.get("alt_geom")) if on_ground else (_num(alt) if alt is not None else _num(a.get("alt_geom")))
    gs = _num(a.get("gs"))
    rate = _num(a.get("baro_rate"))
    if rate is None:
        rate = _num(a.get("geom_rate"))
    seen = _num(a.get("seen_pos"))
    if seen is None:
        seen = _num(a.get("seen")) or 0
    now_s = now_s or time.time()
    st = State(icao24=str(a.get("hex", "")).lower().lstrip("~"),
               callsign=str(a.get("flight") or "").strip().upper(),
               country="", lat=lat, lon=lon,
               alt_m=0.0 if on_ground else (alt_ft * 0.3048 if alt_ft is not None else None),
               on_ground=on_ground, speed_ms=gs * 0.514444 if gs is not None else None,
               track=_num(a.get("track")) if a.get("track") is not None else _num(a.get("true_heading")),
               vrate=rate * 0.00508 if rate is not None else None,
               last_contact=int(now_s - seen))
    st.reg = str(a.get("r") or "")
    st.type = str(a.get("t") or "")
    st.desc = str(a.get("desc") or "")
    return st


def _aircraft(body):
    lst = body.get("ac")
    if lst is None:
        lst = body.get("aircraft")
    now = _num(body.get("now"))
    now_s = now / 1000 if now and now > 1e11 else (now or time.time())
    out = []
    for a in lst or []:
        # ground stations and airport vehicles also send ADS-B (e.g. type TWR, category C1–C3)
        if str(a.get("category", "")).startswith("C") or str(a.get("t", "")).upper() in NOT_AIRCRAFT_TYPES:
            continue
        st = to_state(a, now_s)
        if st is not None and st.icao24:
            out.append(st)
    return out


class Feed:
    """Tries the providers in order; remembers a failing one for a few minutes."""

    def __init__(self):
        self._down = {}
        self.last_provider = ""

    def _query(self, kind, **kw):
        errors = []
        for name, base, cs_t, hex_t, around_t in PROVIDERS:
            if self._down.get(name, 0) > time.time():
                continue
            tmpl = {"callsign": cs_t, "hex": hex_t, "around": around_t}[kind]
            url = base.rstrip("/") + tmpl.format(**{k: urllib.parse.quote(str(v), safe=".,-") for k, v in kw.items()})
            try:
                res = _aircraft(_get(url))
                self.last_provider = name
                return res
            except AdsbError as e:
                errors.append(f"{name}: {e}")
                self._down[name] = time.time() + 300
        raise AdsbError("; ".join(errors) or "all providers paused")

    def by_callsign(self, callsign):
        return self._query("callsign", cs=callsign)

    def by_hex(self, hexcode):
        return self._query("hex", hex=hexcode)

    def around(self, lat, lon, nm):
        nm = max(5, min(MAX_NM, int(nm)))
        return self._query("around", lat=round(lat, 3), lon=round(lon, 3), nm=nm)


# ---- routes (adsbdb) -------------------------------------------------------------------------------
_route_cache = None
_route_lock = threading.Lock()
ROUTE_TTL = 24 * 3600


def _cache_path():
    return os.path.join(db.cache_dir(), "routes.json")


def _load_cache():
    global _route_cache
    if _route_cache is None:
        try:
            with open(_cache_path(), encoding="utf-8") as f:
                _route_cache = json.load(f)
        except (OSError, ValueError):
            _route_cache = {}
    return _route_cache


def _save_cache():
    try:
        cache = {k: v for k, v in _route_cache.items() if time.time() - v.get("t", 0) < ROUTE_TTL}
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError:
        pass


def _from_routeset(item):
    codes_iata = [c for c in str(item.get("_airport_codes_iata") or "").split("-") if c]
    codes_icao = [c for c in str(item.get("airport_codes") or "").split("-") if c]
    aps = item.get("_airports") or []
    if aps and not codes_icao:
        codes_icao = [a.get("icao", "") for a in aps]
        codes_iata = [a.get("iata", "") for a in aps]
    if len(codes_icao) < 2 and len(codes_iata) < 2:
        return {}
    return {"codes": codes_iata or codes_icao, "codes_icao": codes_icao,
            "plausible": item.get("plausible") is not False, "airline": ""}


def _lookup(cs, lat, lon):
    for url in ROUTESET_URLS:
        try:
            body = _get(url, timeout=10, body={"planes": [{"callsign": cs, "lat": lat or 0, "lng": lon or 0}]})
        except AdsbError:
            continue
        items = body if isinstance(body, list) else []
        for item in items:
            if str(item.get("callsign", cs)).upper() == cs:
                r = _from_routeset(item)
                if r:
                    r["source"] = "adsb.lol" if "adsb.lol" in url else "adsb.im"
                    return r
        if items:
            break                     # the service answered: it just does not know this callsign
    try:
        body = _get(ROUTE_URL.format(cs=urllib.parse.quote(cs)), timeout=10)
    except AdsbError:
        return {}
    fr = (body.get("response") or {}) if isinstance(body.get("response"), dict) else {}
    fr = fr.get("flightroute") or {}
    if not fr:
        return {}
    o, d = fr.get("origin") or {}, fr.get("destination") or {}
    return {"codes": [o.get("iata_code") or o.get("icao_code") or "", d.get("iata_code") or d.get("icao_code") or ""],
            "codes_icao": [o.get("icao_code") or "", d.get("icao_code") or ""],
            "plausible": True, "airline": (fr.get("airline") or {}).get("name") or "", "source": "adsbdb"}


def route_lookup(callsign, lat=None, lon=None):
    """{'codes': [...], 'codes_icao': [...], 'plausible', 'airline', 'source'} or {} — blocking,
    cached. Tries the routeset services first, then adsbdb."""
    cs = (callsign or "").strip().upper()
    if not cs:
        return {}
    with _route_lock:
        cache = _load_cache()
        hit = cache.get(cs)
        if hit and time.time() - hit.get("t", 0) < ROUTE_TTL and "codes" in (hit.get("r") or {"codes": 1}):
            return hit.get("r") or {}
    r = _lookup(cs, lat, lon)
    with _route_lock:
        _load_cache()[cs] = {"t": time.time(), "r": r}
        _save_cache()
    return r


def route_async(callsign, callback, lat=None, lon=None):
    """route_lookup in a thread; callback(route_dict) on the main thread."""
    def work():
        r = route_lookup(callsign, lat, lon)
        GLib.idle_add(lambda: (callback(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def resolve_route(route, airports, pos=None):
    """(origin Airport, dest Airport) for a route dict, or (None, None). Multi-leg routes
    (A-B-C): the leg the aircraft at pos=(lat, lon) is most likely flying."""
    if not route:
        return None, None
    icao = route.get("codes_icao") or []
    iata = route.get("codes") or []
    n = max(len(icao), len(iata))
    aps = []
    for k in range(n):
        ap = (airports.get(icao[k]) if k < len(icao) and icao[k] else None) or \
             (airports.get(iata[k]) if k < len(iata) and iata[k] else None)
        aps.append(ap)
    legs = [(aps[k], aps[k + 1]) for k in range(n - 1) if aps[k] and aps[k + 1]]
    if not legs:
        return None, None
    if len(legs) == 1 or pos is None:
        return legs[0] if pos is None or len(legs) == 1 else legs[0]
    from .geo import distance_km

    def detour(leg):
        a, b = leg
        return (distance_km(pos[0], pos[1], a.lat, a.lon) + distance_km(pos[0], pos[1], b.lat, b.lon)
                - distance_km(a.lat, a.lon, b.lat, b.lon))
    return min(legs, key=detour)
