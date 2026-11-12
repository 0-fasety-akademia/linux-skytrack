"""Traffic layer for the 'Na żywo' map: every aircraft in the visible area, refreshed every
few seconds from the community ADS-B networks (see adsb.py). Runs only while the page is shown."""
import math
import threading
import time

from gi.repository import GLib, GObject

from . import adsb

INTERVAL = 10          # seconds between refreshes
MAX_PLANES = 700


class TrafficFeed(GObject.Object):
    __gsignals__ = {
        "planes": (GObject.SignalFlags.RUN_FIRST, None, (object,)),      # list[live.State]
        "status": (GObject.SignalFlags.RUN_FIRST, None, (str,)),         # "", "error", "wide"
    }

    def __init__(self):
        super().__init__()
        self.feed = adsb.Feed()
        self.view = None            # (lat, lon, nm)
        self.active = False
        self.planes = {}            # hex -> State (last snapshot)
        self._timer = None
        self._busy = False
        self._last = 0.0

    def set_active(self, active):
        if active == self.active:
            return
        self.active = active
        if active:
            self._kick(0.2)
        elif self._timer:
            GLib.source_remove(self._timer)
            self._timer = None

    def set_view(self, lat, lon, nm):
        self.view = (lat, lon, nm)
        if self.active and time.time() - self._last > 2:
            self._kick(0.4)

    def _kick(self, delay):
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(int(delay * 1000), self._tick)

    def _tick(self):
        self._timer = None
        if not self.active:
            return False
        if self.view is None or self._busy:
            self._kick(1 if self.view is None else 2)
            return False
        self._busy = True
        self._last = time.time()
        lat, lon, nm = self.view
        threading.Thread(target=self._work, args=(lat, lon, nm), daemon=True).start()
        return False

    def _work(self, lat, lon, nm):
        try:
            res = ("ok", self.feed.around(lat, lon, min(nm, adsb.MAX_NM)), nm)
        except adsb.AdsbError as e:
            res = ("error", e, nm)
        GLib.idle_add(self._done, res, lat, lon)

    def _done(self, res, lat, lon):
        self._busy = False
        kind, payload, nm = res
        if kind == "ok":
            planes = payload
            if len(planes) > MAX_PLANES:
                k = math.cos(math.radians(lat))
                planes.sort(key=lambda p: (p.lat - lat) ** 2 + ((p.lon - lon) * k) ** 2)
                planes = planes[:MAX_PLANES]
            self.planes = {p.icao24: p for p in planes}
            self.emit("planes", planes)
            self.emit("status", "wide" if nm > adsb.MAX_NM * 1.4 else "")
        else:
            self.emit("status", "error")
        if self.active:
            self._kick(INTERVAL if kind == "ok" else 30)
        return False


def compact(planes, skip=None):
    """Small dicts for the map."""
    return [{"h": p.icao24, "c": p.callsign, "la": round(p.lat, 4), "lo": round(p.lon, 4),
             "tr": round(p.track or 0), "g": bool(p.on_ground)} for p in planes if p.icao24 != skip]
