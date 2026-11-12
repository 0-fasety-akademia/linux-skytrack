"""Leaflet map inside WebKitGTK, with a tiny JSON bridge to Python."""
import json
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gio, GLib, GObject, Gtk, WebKit

from . import db
from .version import VERSION
from .i18n import IS_PL

USER_AGENT = (f"linux-skytrack/{VERSION} (+https://github.com/jgu-linux-apps/linux-skytrack) "
              "WebKitGTK")


class MapView(Gtk.Box):
    __gsignals__ = {
        "trip-selected": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "layer-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "map-event": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),     # kind, JSON message
    }

    def __init__(self, web_dir, layer="map", dark=False, theme="system"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        self._ready = False
        self._queue = []
        if not IS_PL:
            self.call("SkyMap.setLang", {"lang": "en", "map": "Map", "sat": "Satellite",
                                         "legVisited": "visited", "legOrigin": "departure",
                                         "legPlanned": "planned", "layerGroup": "Map layer",
                                         "outline": "Outline", "offline": "No internet — outline map",
                                         "visited": "Visited", "departures": "Departures",
                                         "planned": "planned", "plan": "plan"})

        wk_data = os.path.join(db.data_dir(), "webkit")
        wk_cache = os.path.join(db.cache_dir(), "webkit")   # map tile cache lives here
        session = WebKit.NetworkSession.new(wk_data, wk_cache)

        ucm = WebKit.UserContentManager()
        ucm.register_script_message_handler("skytrack", None)
        ucm.connect("script-message-received::skytrack", self._on_message)

        self.web = WebKit.WebView(network_session=session, user_content_manager=ucm,
                                  hexpand=True, vexpand=True)
        s = self.web.get_settings()
        s.set_user_agent(USER_AGENT)
        s.set_allow_file_access_from_file_urls(True)
        s.set_enable_developer_extras(bool(os.environ.get("SKYTRACK_DEVTOOLS")))
        s.set_enable_write_console_messages_to_stdout(bool(os.environ.get("SKYTRACK_DEVTOOLS")))
        self.web.connect("context-menu", lambda *a: not os.environ.get("SKYTRACK_DEVTOOLS"))
        self.web.connect("decide-policy", self._on_policy)
        self.append(self.web)

        self.call("SkyMap.setLayer", layer)
        self.call("SkyMap.setTheme", theme, dark)
        self.web.load_uri(GLib.filename_to_uri(os.path.join(web_dir, "map.html"), None))

    # Python -> JS ----------------------------------------------------------------
    def call(self, fn, *args):
        js = f"{fn}({', '.join(json.dumps(a, ensure_ascii=False) for a in args)});"
        if self._ready:
            self.web.evaluate_javascript(js, -1, None, None, None, None, None)
        else:
            self._queue.append(js)

    def set_trips(self, infos, home=None):
        visited = sorted({i.dest.cc for i in infos if not i.planned} - {home})
        self.call("SkyMap.setData", {"trips": [i.to_js() for i in infos], "visited": visited,
                                     "home": home or ""})

    def set_mode(self, mode):
        self.call("SkyMap.setMode", mode)

    def set_live(self, data, fit=True):
        self.call("SkyMap.setLive", data, fit)

    def set_traffic(self, planes):
        self.call("SkyMap.setTraffic", planes)

    def plane_info(self, info):
        self.call("SkyMap.planeInfo", info)

    def focus(self, trip_id):
        self.call("SkyMap.focus", trip_id)

    def clear_focus(self):
        self.call("SkyMap.clearFocus")

    def set_layer(self, layer):
        self.call("SkyMap.setLayer", layer)

    def set_theme(self, theme, dark):
        self.call("SkyMap.setTheme", theme, dark)

    # JS -> Python ----------------------------------------------------------------
    def _on_message(self, _ucm, value):
        try:
            msg = json.loads(value.to_string())
        except (ValueError, TypeError):
            return
        kind = msg.get("type")
        if kind == "ready":
            self._ready = True
            queued, self._queue = self._queue, []
            for js in queued:
                self.web.evaluate_javascript(js, -1, None, None, None, None, None)
        elif kind == "select" and isinstance(msg.get("id"), int):
            self.emit("trip-selected", msg["id"])
        elif kind == "layer":
            self.emit("layer-changed", str(msg.get("value", "map")))
        elif kind in ("view", "plane", "track", "plane-closed", "map-click"):
            self.emit("map-event", kind, json.dumps(msg))

    def _on_policy(self, _web, decision, dtype):
        """Open attribution links in the default browser instead of inside the map."""
        if dtype == WebKit.PolicyDecisionType.NEW_WINDOW_ACTION or \
                dtype == WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri()
            if uri.startswith(("http://", "https://")):
                Gio.AppInfo.launch_default_for_uri(uri, None)
                decision.ignore()
                return True
        return False
