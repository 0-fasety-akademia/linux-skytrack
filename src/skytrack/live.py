"""Live flight tracking with the OpenSky Network REST API (https://opensky-network.org).

A flight number (W6 1729) becomes an ICAO callsign (WZZ1729) via data/airlines.json; a callsign
can also be typed directly (RYR5TG). OpenSky has no "find by callsign" query, so the tracker looks
in a small box around where the plane should be (cheap: 1 API credit), then wider, and once the
aircraft is found it follows its transponder address (icao24) in a small box around it.

Anonymous use: 400 credits a day; with a free OpenSky account (API client) 4000.
"""
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from gi.repository import GLib, GObject

from . import db, geo
from .i18n import _
from .version import REPO_URL, VERSION

API = os.environ.get("SKYTRACK_OPENSKY_URL", "https://opensky-network.org/api")
TOKEN_URL = os.environ.get(
    "SKYTRACK_OPENSKY_TOKEN_URL",
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token")
USER_AGENT = f"linux-skytrack/{VERSION} (+{REPO_URL})"
START_BEFORE_MIN = 40          # start looking this long before the scheduled departure
DELAY_MIN = 15                 # notify when the estimated arrival is this much later than planned
LOST_GIVE_UP_MIN = 45


class LiveError(Exception):
    def __init__(self, kind, message="", retry_after=None):
        super().__init__(message or kind)
        self.kind, self.retry_after = kind, retry_after


@dataclass
class State:
    icao24: str
    callsign: str
    country: str
    lat: float
    lon: float
    alt_m: float | None
    on_ground: bool
    speed_ms: float | None
    track: float | None
    vrate: float | None
    last_contact: int
    reg: str = ""
    type: str = ""
    desc: str = ""

    @classmethod
    def from_vector(cls, v):
        return cls(icao24=v[0], callsign=(v[1] or "").strip().upper(), country=v[2] or "",
                   lat=v[6], lon=v[5], alt_m=v[13] if v[13] is not None else v[7], on_ground=bool(v[8]),
                   speed_ms=v[9], track=v[10], vrate=v[11], last_contact=int(v[4] or 0))


# ---- flight number -> callsigns ------------------------------------------------------------------
_airlines = None


def airlines():
    global _airlines
    if _airlines is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "airlines.json")
        try:
            with open(path, encoding="utf-8") as f:
                _airlines = json.load(f)
        except (OSError, ValueError):
            _airlines = {}
    return _airlines


FLIGHT_RE = re.compile(r"^([A-Z0-9]{2})(\d{1,4})([A-Z]?)$")
CALLSIGN_RE = re.compile(r"^([A-Z]{3})([A-Z0-9]{1,5})$")


def parse_query(text):
    """'W6 1729' -> ({'WZZ1729'}, 'Wizz Air', 'W6 1729'); 'RYR5TG' -> ({'RYR5TG'}, 'Ryanair', 'RYR5TG').
    Returns (callsigns, airline name, display label) or (set(), '', text) when not understood."""
    q = re.sub(r"\s+", " ", (text or "").strip().upper())
    compact = re.sub(r"[\s\-]", "", q)
    m = FLIGHT_RE.match(compact)
    if m and not m.group(1).isdigit():
        iata, num, suffix = m.groups()
        info = airlines().get(iata)
        if info:
            n = num.lstrip("0") or "0"
            return ({f"{info[0]}{n}{suffix}", f"{info[0]}{num}{suffix}"}, info[1], f"{iata} {num}{suffix}")
    m = CALLSIGN_RE.match(compact)
    if m and any(c.isdigit() for c in m.group(2)):
        icao = m.group(1)
        name = next((v[1] for v in airlines().values() if v[0] == icao), "")
        return {compact}, name, compact
    return set(), "", q


# ---- OpenSky client --------------------------------------------------------------------------------
def credentials_path():
    return os.path.join(db.config_dir(), "opensky.json")


def load_credentials():
    try:
        with open(credentials_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d.get("client_id", ""), d.get("client_secret", "")
    except (OSError, ValueError):
        return "", ""


def save_credentials(client_id, client_secret):
    path = credentials_path()
    if not client_id and not client_secret:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    part = path + ".part"
    fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret}, f)
    os.replace(part, path)


def box_cost(bbox):
    """OpenSky API credits for a bounding-box query (None = whole world)."""
    if bbox is None:
        return 4
    lamin, lomin, lamax, lomax = bbox
    area = abs(lamax - lamin) * abs(lomax - lomin)
    return 1 if area <= 25 else 2 if area <= 100 else 3 if area <= 400 else 4


def box_around(lat, lon, half_lat=2.4, max_area=24.0):
    """A box of at most max_area square degrees (1 credit) centred on lat/lon."""
    half_lon = max_area / (4 * half_lat)
    lamin, lamax = max(-89.0, lat - half_lat), min(89.0, lat + half_lat)
    return (lamin, lon - half_lon, lamax, lon + half_lon)


class OpenSky:
    def __init__(self):
        self.client_id, self.client_secret = load_credentials()
        self._token, self._token_exp = None, 0
        self.remaining = None          # credits left today (X-Rate-Limit-Remaining)

    def reload_credentials(self):
        self.client_id, self.client_secret = load_credentials()
        self._token, self._token_exp = None, 0

    @property
    def authenticated(self):
        return bool(self.client_id and self.client_secret)

    def _bearer(self):
        if not self.authenticated:
            return None
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.client_id,
                                       "client_secret": self.client_secret}).encode()
        req = urllib.request.Request(TOKEN_URL, data=data, headers={
            "Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise LiveError("auth", f"HTTP {e.code}") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise LiveError("network", str(e)) from e
        self._token = d.get("access_token")
        self._token_exp = time.time() + int(d.get("expires_in", 1800))
        if not self._token:
            raise LiveError("auth", "no token")
        return self._token

    def states(self, bbox=None):
        params = {}
        if bbox:
            params = dict(zip(("lamin", "lomin", "lamax", "lomax"), (round(x, 3) for x in bbox)))
        url = API.rstrip("/") + "/states/all" + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"User-Agent": USER_AGENT}
        token = self._bearer()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                rem = r.headers.get("X-Rate-Limit-Remaining")
                body = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                ra = e.headers.get("X-Rate-Limit-Retry-After-Seconds")
                raise LiveError("rate", "429", int(ra) if ra and ra.isdigit() else 3600) from e
            if e.code in (401, 403):
                self._token = None
                raise LiveError("auth", f"HTTP {e.code}") from e
            raise LiveError("http", f"HTTP {e.code}") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise LiveError("network", str(e)) from e
        if rem is not None and rem.lstrip("-").isdigit():
            self.remaining = int(rem)
        return [State.from_vector(v) for v in (body.get("states") or []) if v and v[5] is not None and v[6] is not None]


# ---- tracker ---------------------------------------------------------------------------------------
def _dist(lat1, lon1, lat2, lon2):
    return geo.distance_km(lat1, lon1, lat2, lon2)


def _bearing(lat1, lon1, lat2, lon2):
    φ1, φ2, dλ = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dλ) * math.cos(φ2)
    x = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(dλ)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _interp(a, b, f):
    """Point at fraction f of the great circle a→b (airports)."""
    φ1, λ1, φ2, λ2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    d = 2 * math.asin(math.sqrt(math.sin((φ2 - φ1) / 2) ** 2 +
                                math.cos(φ1) * math.cos(φ2) * math.sin((λ2 - λ1) / 2) ** 2))
    if d < 1e-9:
        return a.lat, a.lon
    A, B = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
    x = A * math.cos(φ1) * math.cos(λ1) + B * math.cos(φ2) * math.cos(λ2)
    y = A * math.cos(φ1) * math.sin(λ1) + B * math.cos(φ2) * math.sin(λ2)
    z = A * math.sin(φ1) + B * math.sin(φ2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


@dataclass
class Session:
    label: str
    callsigns: set
    airline: str = ""
    origin: object = None
    dest: object = None
    trip_id: int | None = None
    sched_dep: datetime | None = None
    sched_arr: datetime | None = None
    icao24: str = ""
    state: State | None = None
    trail: list = field(default_factory=list)
    status: str = "idle"          # waiting, searching, airborne, ground, landed, lost, error, stopped
    message: str = ""
    seen_ground: bool = False
    seen_air: bool = False
    search_step: int = 0
    lost_since: float | None = None
    started: float = field(default_factory=time.time)
    events: set = field(default_factory=set)
    guessed: bool = False
    next_poll: float = 0.0
    route_tried: bool = False
    route_source: str = ""        # "log" (trip from the log), "adsbdb", "user"
    source: str = ""              # data provider of the last position
    from_map: bool = False        # picked on the traffic map (a click elsewhere ends it)


class Tracker(GObject.Object):
    __gsignals__ = {
        "update": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "event": (GObject.SignalFlags.RUN_FIRST, None, (str, str, str)),   # kind, title, body
    }

    def __init__(self, settings, airports=None):
        super().__init__()
        from . import adsb
        self.settings = settings
        self.airports = airports
        self.feed = adsb.Feed()
        self._adsb_paused_until = 0.0
        self.api = OpenSky()
        self.s = None
        self._timer = None
        self._busy = False
        self._gen = 0

    # public ------------------------------------------------------------------------------------
    @property
    def active(self):
        return self.s is not None and self.s.status not in ("stopped", "landed", "idle")

    def start(self, text, origin=None, dest=None, trip_info=None):
        callsigns, airline, label = parse_query(text)
        if not callsigns:
            return False
        s = Session(label=label, callsigns=callsigns, airline=airline, origin=origin, dest=dest)
        if dest is not None:
            s.route_source = "user"
        if trip_info is not None:
            s.route_source = "log"
            t = trip_info.trip
            s.trip_id = t.id
            s.origin, s.dest = trip_info.origin, trip_info.dest
            s.sched_dep = geo.local_dt(t.dep_date, t.dep_time, trip_info.origin.tz) if t.dep_time else None
            ad, at, _est = trip_info.arrival
            if ad and at:
                s.sched_arr = geo.local_dt(ad, at, trip_info.dest.tz)
        self._gen += 1
        self.s = s
        self._schedule(0)
        self.emit("update")
        return True

    def start_hex(self, hexcode, callsign="", origin=None, dest=None, route_source=""):
        """Track an aircraft picked on the traffic map (known transponder address)."""
        callsign = (callsign or "").strip().upper()
        cs, airline, label = parse_query(callsign) if callsign else (set(), "", "")
        s = Session(label=callsign or hexcode.upper(), callsigns=cs or ({callsign} if callsign else set()),
                    airline=airline, origin=origin, dest=dest)
        s.icao24 = hexcode.lower()
        s.from_map = True
        if origin and dest:
            s.route_source = route_source or "adsbdb"
            s.route_tried = True
        self._gen += 1
        self.s = s
        self._schedule(0)
        self.emit("update")
        return True

    def stop(self):
        self._gen += 1
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None
        if self.s:
            self.s.status = "stopped"
            self.s.message = ""
        self.emit("update")

    def clear(self):
        self.stop()
        self.s = None
        self.emit("update")

    def poll_now(self):
        if self.s and self.s.status not in ("stopped", "landed"):
            self._schedule(0)

    # scheduling --------------------------------------------------------------------------------
    def _interval(self):
        return max(15, int(self.settings["live_interval"] or 60))

    def _schedule(self, seconds):
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(int(seconds * 1000) + 1, self._tick, self._gen)
        if self.s:
            self.s.next_poll = time.time() + seconds

    def _tick(self, gen):
        self._timer = None
        if gen != self._gen or self.s is None or self._busy:
            return False
        s = self.s
        now = datetime.now(timezone.utc)
        if s.sched_dep and not s.icao24 and now < s.sched_dep - timedelta(minutes=START_BEFORE_MIN):
            wait = (s.sched_dep - timedelta(minutes=START_BEFORE_MIN) - now).total_seconds()
            s.status = "waiting"
            s.message = _('Szukanie ruszy ok. {0} min przed startem.').format(START_BEFORE_MIN)
            self.emit("update")
            self._schedule(min(max(wait, 30), 600))
            return False
        self._busy = True
        if time.time() >= self._adsb_paused_until:
            purpose = ("follow" if s.lost_since is None else "lost") if s.icao24 else "search"
            threading.Thread(target=self._worker_adsb, args=(gen, purpose), daemon=True).start()
        else:
            bbox, purpose = self._plan_query()
            threading.Thread(target=self._worker, args=(gen, bbox, purpose), daemon=True).start()
        return False

    def _estimated_position(self):
        s = self.s
        if not (s.origin and s.dest):
            return None
        if not (s.sched_dep and s.sched_arr):
            return s.origin.lat, s.origin.lon
        now = datetime.now(timezone.utc)
        total = (s.sched_arr - s.sched_dep).total_seconds()
        f = (now - s.sched_dep).total_seconds() / total if total > 0 else 0
        f = min(max(f, 0.0), 1.0)
        return _interp(s.origin, s.dest, f)

    def _plan_query(self):
        s = self.s
        if s.state is not None and s.lost_since is None:
            return box_around(s.state.lat, s.state.lon), "follow"
        if s.state is not None:
            return None, "lost"
        est = self._estimated_position()
        if est and s.search_step == 0:
            return box_around(*est), "search"
        if s.origin and s.dest and s.search_step == 1:
            lamin, lamax = sorted((s.origin.lat, s.dest.lat))
            lomin, lomax = sorted((s.origin.lon, s.dest.lon))
            if lomax - lomin < 180:
                bb = (lamin - 1.5, lomin - 1.5, lamax + 1.5, lomax + 1.5)
                return (bb if box_cost(bb) < 4 else None), "search"
        return None, "search"

    def _worker_adsb(self, gen, purpose):
        """Free community networks: by transponder address, else by callsign, else around the
        expected position (to match Ryanair-style callsigns by route)."""
        from . import adsb
        s = self.s
        try:
            if s.icao24:
                states = self.feed.by_hex(s.icao24)
            else:
                states = []
                for cs in sorted(s.callsigns, key=len):
                    states += self.feed.by_callsign(cs)
                    if states:
                        break
                if not states:
                    est = self._estimated_position()
                    if est and s.dest and s.sched_dep and datetime.now(timezone.utc) >= s.sched_dep - timedelta(minutes=5):
                        states = self.feed.around(est[0], est[1], 130)
            res = ("ok", states)
        except adsb.AdsbError as e:
            res = ("adsb-error", e)
        GLib.idle_add(self._on_result, gen, purpose, res)

    def _worker(self, gen, bbox, purpose):
        try:
            res = ("ok", self.api.states(bbox))
        except LiveError as e:
            res = ("error", e)
        GLib.idle_add(self._on_result, gen, purpose, res)

    # results -----------------------------------------------------------------------------------
    def _on_result(self, gen, purpose, res):
        self._busy = False
        if gen != self._gen or self.s is None:
            return False
        s = self.s
        kind, payload = res
        if kind == "adsb-error":           # community networks unreachable: OpenSky for a while
            self._adsb_paused_until = time.time() + 600
            self._schedule(1)
            return False
        s.source = self.feed.last_provider if kind == "ok" and time.time() >= self._adsb_paused_until else "OpenSky"
        if kind == "error":
            e = payload
            if e.kind == "rate":
                s.status = "error"
                s.message = _('Wyczerpany dzienny limit OpenSky. Następna próba za {0} min. '
                              'Darmowe konto OpenSky daje 10× większy limit.').format(max(1, (e.retry_after or 3600) // 60))
                self._schedule(min(e.retry_after or 3600, 3600))
            elif e.kind == "auth":
                s.status = "error"
                s.message = _('OpenSky odrzucił dane konta (client id / secret). Sprawdź je w ustawieniach śledzenia.')
                self.api.client_id = self.api.client_secret = ""
                self._schedule(30)
            else:
                s.message = _('Brak połączenia z OpenSky — spróbuję ponownie.')
                if s.status not in ("airborne", "ground"):
                    s.status = "error"
                self._schedule(max(self._interval(), 60))
            self.emit("update")
            return False

        states = payload
        found = None
        if s.icao24:
            found = next((st for st in states if st.icao24 == s.icao24), None)
        if found is None:
            matches = [st for st in states if st.callsign in s.callsigns]
            if matches:
                est = self._estimated_position()
                if est:
                    matches.sort(key=lambda st: _dist(st.lat, st.lon, *est))
                else:
                    matches.sort(key=lambda st: st.on_ground)
                found = matches[0]
        if found is None and not s.icao24:
            found = self._guess_by_route(states)
            if found is not None:
                s.guessed = True

        if found is None:
            self._not_found(purpose)
        else:
            self._found(found)
        self.emit("update")
        return False

    def _guess_by_route(self, states):
        """Airlines like Ryanair fly under callsigns such as RYR5TG, not RYR1234. With a known
        route: take the only airborne aircraft of that airline near the expected position that is
        heading for the destination."""
        s = self.s
        est = self._estimated_position()
        if not (est and s.dest and s.sched_dep):
            return None
        if datetime.now(timezone.utc) < s.sched_dep - timedelta(minutes=5):
            return None
        prefixes = {c[:3] for c in s.callsigns}
        cands = []
        for st in states:
            if st.callsign[:3] not in prefixes or st.on_ground or st.track is None:
                continue
            if _dist(st.lat, st.lon, *est) > 250:
                continue
            to_dest = _bearing(st.lat, st.lon, s.dest.lat, s.dest.lon)
            diff = abs((st.track - to_dest + 180) % 360 - 180)
            if diff < 35:
                cands.append(st)
        return cands[0] if len(cands) == 1 else None

    def _not_found(self, purpose):
        s = self.s
        if purpose == "follow":          # left the small box (or transponder off) — look globally
            s.lost_since = time.time()
            self._schedule(5)
            return
        if purpose == "lost" or s.state is not None:
            if s.lost_since is None:
                s.lost_since = time.time()
            near_dest = (s.dest and s.state and
                         _dist(s.state.lat, s.state.lon, s.dest.lat, s.dest.lon) < 40 and
                         (s.state.on_ground or (s.state.alt_m or 0) < 2500))
            if near_dest:
                self._landed()
                return
            if time.time() - s.lost_since > LOST_GIVE_UP_MIN * 60:
                s.status = "stopped"
                s.message = _('Samolot zniknął z zasięgu odbiorników OpenSky. Śledzenie zatrzymane.')
                return
            s.status = "lost"
            s.message = _('Brak sygnału z samolotu (np. nad morzem poza zasięgiem odbiorników). Szukam dalej…')
            self._schedule(max(self._interval(), 120))
            return
        # still searching for the first contact
        s.search_step = (s.search_step + 1) % 3
        s.status = "searching"
        cs = ", ".join(sorted(s.callsigns, key=len))
        s.message = _('Nie widzę jeszcze lotu {0}. Samolot może stać z wyłączonym transponderem albo '
                      'linia używa innego znaku wywoławczego (sprawdź go w aplikacji linii, np. RYR5TG).').format(cs)
        too_long = s.sched_dep is None and time.time() - s.started > 3 * 3600
        if too_long:
            s.status = "stopped"
            return
        self._schedule(max(self._interval(), 90) if s.search_step else max(self._interval() * 2, 180))

    def _lookup_route(self, callsign):
        s = self.s
        if s.route_tried or (s.origin is not None and s.dest is not None) or not callsign or self.airports is None:
            return
        s.route_tried = True
        from . import adsb
        sess = s

        pos = (sess.state.lat, sess.state.lon) if sess.state else None

        def done(route):
            if self.s is not sess or (sess.origin is not None and sess.dest is not None):
                return
            a, b = adsb.resolve_route(route, self.airports, pos)
            if a and b and (sess.dest is None or sess.dest.iata == b.iata):
                sess.origin, sess.dest = a, b
                sess.route_source = route.get("source") or "adsbdb"
                if not sess.airline and route.get("airline"):
                    sess.airline = route["airline"]
                self.emit("update")
        adsb.route_async(callsign, done, *(pos or (None, None)))

    def _found(self, st):
        s = self.s
        first = s.state is None
        s.icao24 = st.icao24
        s.lost_since = None
        s.search_step = 0
        prev = s.state
        s.state = st
        self._lookup_route(st.callsign)
        if not s.trail or _dist(s.trail[-1][0], s.trail[-1][1], st.lat, st.lon) > 0.3:
            s.trail.append((st.lat, st.lon))
            del s.trail[:-3000]
        if st.on_ground:
            s.seen_ground = True
            if s.seen_air and s.dest and _dist(st.lat, st.lon, s.dest.lat, s.dest.lon) < 25:
                self._landed()
                return
            if s.seen_air and not s.dest and (st.speed_ms or 0) < 40:
                self._landed()
                return
            s.status = "ground"
            s.message = ""
        else:
            if not s.seen_air and (s.seen_ground or (prev is None and not first)):
                self._event("airborne", _('{0} wystartował').format(s.label),
                            self._route_text() or _('Samolot jest w powietrzu.'))
            elif not s.seen_air and first and (st.alt_m or 0) < 3000 and (st.vrate or 0) > 2:
                self._event("airborne", _('{0} wystartował').format(s.label),
                            self._route_text() or _('Samolot jest w powietrzu.'))
            s.seen_air = True
            s.status = "airborne"
            s.message = (_('Dopasowano po trasie: {0}. Jeśli to nie ten samolot, wpisz znak wywoławczy z aplikacji linii.').format(st.callsign)
                         if s.guessed else "")
            eta = self.eta()
            if eta and s.sched_arr and eta - s.sched_arr > timedelta(minutes=DELAY_MIN):
                late = int((eta - s.sched_arr).total_seconds() // 60)
                self._event("delay", _('{0}: opóźnienie ok. {1} min').format(s.label, late),
                            _('Szacowany przylot {0} zamiast {1}.').format(
                                self.local_time(eta, s.dest), self.local_time(s.sched_arr, s.dest)))
        self._schedule(self._interval())

    def _landed(self):
        s = self.s
        s.status = "landed"
        s.message = ""
        self._event("landed", _('{0} wylądował').format(s.label),
                    (_('Witamy w {0}!').format(s.dest.short) if s.dest else _('Samolot jest na ziemi.')))
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None

    def _event(self, kind, title, body):
        s = self.s
        if kind in s.events:
            return
        s.events.add(kind)
        key = f"live:{s.trip_id or s.label}:{(s.sched_dep or datetime.now()).date()}:{kind}"
        notified = list(self.settings["notified"] or [])
        if key in notified:
            return
        notified.append(key)
        self.settings["notified"] = notified[-300:]
        self.emit("event", kind, title, body)

    # derived values for the UI ---------------------------------------------------------------------
    def _route_text(self):
        s = self.s
        if s.origin and s.dest:
            return f"{s.origin.iata} → {s.dest.iata} · {s.origin.short} → {s.dest.short}"
        return ""

    def remaining_km(self):
        s = self.s
        if not (s and s.state and s.dest):
            return None
        return _dist(s.state.lat, s.state.lon, s.dest.lat, s.dest.lon)

    def eta(self):
        """Estimated arrival (aware UTC datetime) from position and ground speed."""
        s = self.s
        rem = self.remaining_km()
        if rem is None or s.state is None or s.state.on_ground:
            return None
        kmh = (s.state.speed_ms or 0) * 3.6
        kmh = kmh if kmh > 250 else 750
        minutes = rem / kmh * 60 + (8 if rem > 40 else 3)
        return datetime.fromtimestamp(s.state.last_contact or time.time(), timezone.utc) + timedelta(minutes=minutes)

    @staticmethod
    def local_time(dt, airport=None):
        if dt is None:
            return "—"
        try:
            from zoneinfo import ZoneInfo
            if airport is not None and airport.tz:
                return dt.astimezone(ZoneInfo(airport.tz)).strftime("%H:%M")
        except Exception:
            pass
        return dt.astimezone().strftime("%H:%M")

    def map_data(self, follow=False):
        s = self.s
        if s is None:
            return None
        d = {"label": s.label, "trail": [list(p) for p in s.trail], "follow": follow}
        if s.origin:
            d["origin"] = s.origin.to_js()
        if s.dest:
            d["dest"] = s.dest.to_js()
        if s.state:
            stale = time.time() - (s.state.last_contact or time.time()) > 300 or s.status == "lost"
            d["pos"] = {"lat": s.state.lat, "lon": s.state.lon, "heading": s.state.track or 0,
                        "stale": stale}
        return d
