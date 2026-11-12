"""SkyTrack application: actions, notifications, About."""
import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import live, db, geo, stats, theme
from .airports import AirportDB, default_path
from .version import APP_ID, APP_NAME, REPO_URL, VERSION
from .i18n import _

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))



class SkyTrackApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        GLib.set_application_name(APP_NAME)
        self.window = None
        self.web_dir = os.path.join(BASE_DIR, "web")
        self.icon_dir = os.path.join(BASE_DIR, "icons")
        self.template_dir = os.path.join(BASE_DIR, "templates")
        self.add_main_option("add", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Open the add-trip dialog", None)
        self._add_on_start = False

    # Lifecycle -------------------------------------------------------------------------
    def do_handle_local_options(self, options):
        if options.contains("add"):
            self.register(None)
            if self.get_is_remote():
                self.activate_action("add-trip", None)
                return 0
            self._add_on_start = True
        return -1

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.settings = db.Settings()
        self.store = db.TripStore()
        self.airports = None      # loaded behind the splash screen (see do_activate)
        self.tracker = None

        display = Gdk.Display.get_default()
        icons = Gtk.IconTheme.get_for_display(display)
        for sub in ("scalable/apps", "symbolic/apps"):
            path = os.path.join(self.icon_dir, "hicolor", sub)
            if os.path.isdir(path):
                icons.add_search_path(path)
        if self.settings["theme"] not in theme.THEMES:
            self.settings["theme"] = "system"
        theme.apply(self.settings["theme"])

        for name, cb, accels in (
            ("add-trip", lambda *_: self._show(add=True), ["<Control>n"]),
            ("show", lambda *_: self._show(), []),
            ("show-trips", lambda *_: self._show(page="trips"), ["<Control>1"]),
            ("show-stats", lambda *_: self._show(page="stats"), ["<Control>3"]),
            ("show-summary", lambda *_: self._show(page="summary"), ["<Control>5"]),
            ("show-live", lambda *_: self._show(page="live"), ["<Control>4"]),
            ("about", self._on_about, []),
            ("open-data", self._on_open_data, []),
            ("import", lambda *_: (self._show(), self.window.when_unlocked(self.window.import_csv)),
             ["<Control>i"]),
            ("export", lambda *_: (self._show(), self.window.when_unlocked(self.window.export_csv)),
             ["<Control>e"]),
            ("save-template", lambda *_: (self._show(), self.window.when_unlocked(self.window.save_template)),
             []),
            ("backup", lambda *_: (self._show(), self.window.when_unlocked(self.window.show_backup)), []),
            ("show-plans", lambda *_: self._show(page="plans"), ["<Control>2"]),
            ("quit", lambda *_: self.quit_all(), ["<Control>q"]),
            ("lock", lambda *_: self.window and self.window.lock(), ["<Control>l"]),
            ("change-password", lambda *_: self.window and self.window.change_password(), []),
        ):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)
            if accels:
                self.set_accels_for_action(f"app.{name}", accels)
        theme_act = Gio.SimpleAction.new_stateful("theme", GLib.VariantType.new("s"),
                                                  GLib.Variant.new_string(self.settings["theme"]))
        theme_act.connect("change-state", self._on_theme)
        self.add_action(theme_act)
        self.set_accels_for_action("window.close", ["<Control>w"])
        self._loading = False
        self._pending = []


    def do_activate(self):
        add, self._add_on_start = self._add_on_start, False
        if self.window is not None:
            self._show(add=add)
            return
        self._pending.append({"add": add})
        if self._loading:
            return
        self._loading = True
        from .splash import Splash
        self.splash = Splash(self, os.path.join(self.icon_dir, "splash.png"))
        self.splash.present()
        GLib.timeout_add(120, self._load_step, 0)   # let the splash draw first

    def _load_step(self, n):
        """Load in steps so the splash screen can show progress."""
        sp = self.splash
        if n == 0:
            sp.step(0.15, _('Wczytywanie lotnisk…'))
            GLib.timeout_add(30, self._load_step, 1)
        elif n == 1:
            self.airports = AirportDB(default_path())
            self.tracker = live.Tracker(self.settings, self.airports)
            self.tracker.connect("event", lambda _t, kind, title, body:
                                 self.notify(f"live-{kind}", title, body))
            sp.step(0.55, _('Przygotowanie mapy…'))
            GLib.timeout_add(30, self._load_step, 2)
        elif n == 2:
            from .window import MainWindow
            self.window = MainWindow(self)
            sp.step(1.0, _('Gotowe'))
            GLib.timeout_add_seconds(300, self._check_upcoming)
            GLib.timeout_add_seconds(120, self._check_live)
            GLib.timeout_add_seconds(5, lambda: (self._check_upcoming(), False)[1])
            # keep the splash up for a moment, like other big apps do
            import time
            wait = max(0, int((1.6 - (time.monotonic() - sp.shown_at)) * 1000))
            GLib.timeout_add(wait + 150, self._load_step, 3)
        else:
            self._loading = False
            pending, self._pending = self._pending, []
            self._show(add=any(p.get("add") for p in pending),
                       page=next((p["page"] for p in pending if p.get("page")), None))
            sp.close()
            self.splash = None
        return False

    def quit_all(self):
        if getattr(self, "_quitting", False):
            return
        self._quitting = True
        if self.window:
            self.window.atc.turn_off()
            self.window.save_state()
        self.quit()

    def _show(self, add=False, page=None):
        if self.window is None:
            if page:
                self._pending.append({"page": page})
            self.activate()
            if self.window is None:
                return
        self.window.set_visible(True)
        self.window.present()
        win = self.window
        if page:
            win.when_unlocked(lambda: win.stack.set_visible_child_name(page))
        if add:
            win.when_unlocked(lambda: (win.stack.set_visible_child_name("trips"), win.add_trip()))
        if win.locked:
            win.lock_page.focus_first()

    def _check_live(self):
        """Start tracking one of my flights on its departure day (when it has a flight number)."""
        if not self.window or self.window.locked or not self.settings["live_auto"]:
            return True
        if self.tracker.active:
            return True
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        for i in sorted(self.window.all_infos, key=lambda x: (x.trip.dep_date, x.trip.dep_time)):
            t = i.trip
            if not t.flight_no or not t.dep_time:
                continue
            dep = geo.local_dt(t.dep_date, t.dep_time, i.origin.tz)
            if dep is None:
                continue
            ad, at, _e = i.arrival
            arr = geo.local_dt(ad, at, i.dest.tz) if ad and at else dep + timedelta(minutes=i.minutes)
            if dep - timedelta(minutes=live.START_BEFORE_MIN) <= now <= arr + timedelta(minutes=60):
                key = f"live-auto:{t.id}:{t.dep_date}"
                notified = list(self.settings["notified"] or [])
                if key in notified:
                    continue            # already tracked once (or stopped by the user)
                self.settings["notified"] = (notified + [key])[-300:]
                self.window.live_page.track_trip(i)
                break
        return True

    def _check_upcoming(self):
        """Notify once when a planned flight departs within 24 hours (not while locked)."""
        if not self.window or self.window.locked:
            return True
        from datetime import datetime
        from zoneinfo import ZoneInfo
        notified = list(self.settings["notified"] or [])
        changed = False
        for i in stats.planned(self.window.all_infos):
            t = i.trip
            dep = geo.local_dt(t.dep_date, t.dep_time or "00:00", i.origin.tz)
            if not dep:
                continue
            hours = (dep - datetime.now(ZoneInfo(i.origin.tz))).total_seconds() / 3600
            key = f"{t.id}:{t.dep_date}:{t.dep_time}"
            if 0 < hours <= 24 and key not in notified:
                when = f"{stats.nice_date(t.dep_date, True)}" + (f", {t.dep_time}" if t.dep_time else "")
                self.notify(f"upcoming-{t.id}", _('Lot {0}: {1} → {2}').format(i.countdown, t.origin, t.dest),
                            f"{i.origin.short} → {i.dest.short} · {when}\n"
                            f"{geo.fmt_km(i.km)} · {geo.fmt_duration(i.minutes, i.approx)}")
                notified.append(key)
                changed = True
        if changed:
            self.settings["notified"] = notified[-200:]
        return True

    def _on_theme(self, action, value):
        name = value.get_string()
        if name not in theme.THEMES:
            return
        action.set_state(value)
        self.settings["theme"] = name
        theme.apply(name)
        if self.window:
            self.window.apply_theme(name)

    # Misc ------------------------------------------------------------------------------------
    def notify(self, nid, title, body):
        n = Gio.Notification.new(title)
        n.set_body(body)
        n.set_icon(Gio.ThemedIcon.new("linux-skytrack"))
        n.set_default_action("app.show")
        self.send_notification(nid, n)

    def _on_open_data(self, *_a):
        if self.window and self.window.locked:
            return
        Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(db.data_dir(), None), None)

    def _on_about(self, *_a):
        about = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon="linux-skytrack",
            developer_name="Created by: JGu\nSupported by Claude",
            version=VERSION,
            website=REPO_URL,
            issue_url=REPO_URL + "/issues",
            comments=_('Dziennik lotów dla Ubuntu: podróże na mapie (także offline), kilometry i statystyki, podsumowanie roku, śledzenie lotów na żywo i kopie zapasowe. Zdjęcia z podróży z Linux iCloud Photos.'),
            license_type=Gtk.License.CUSTOM,
            license=_('Freeware: darmowy do użytku i do rozpowszechniania w niezmienionej formie. '
                      'Modyfikowanie zabronione. Pełny tekst: plik LICENSE '
                      '(/usr/share/doc/linux-skytrack/LICENSE).'),
            developers=["JGu"],
        )
        about.add_credit_section("Supported by", ["Claude"])
        about.add_legal_section(_('Dane lotnisk — OurAirports'), None, Gtk.License.CUSTOM,
                                "Public domain. https://ourairports.com/data/")
        about.add_legal_section("Leaflet", "© 2010–2023 Volodymyr Agafonkin, © 2010–2011 CloudMade",
                                Gtk.License.BSD, None)
        about.add_legal_section(_('Mapa — OpenStreetMap'), "© OpenStreetMap contributors",
                                Gtk.License.CUSTOM, _('Dane mapy na licencji ODbL. https://www.openstreetmap.org/copyright'))
        about.add_legal_section(_('Zdjęcia satelitarne — Esri World Imagery'),
                                "Esri, Maxar, Earthstar Geographics, GIS User Community",
                                Gtk.License.CUSTOM, _('Użycie zgodnie z warunkami Esri.'))
        about.add_legal_section(_('Śledzenie na żywo — The OpenSky Network'), None, Gtk.License.CUSTOM,
                                _('Dane OpenSky Network do użytku niekomercyjnego. https://opensky-network.org'))
        about.add_legal_section(_('Mapa offline — Natural Earth'), "world-atlas © Mike Bostock (ISC)",
                                Gtk.License.CUSTOM, _('Kontury państw: Natural Earth, domena publiczna. '
                                                      'topojson-client: licencja ISC.'))
        about.add_legal_section(_('Ruch lotniczy — adsb.lol, airplanes.live, adsb.fi, adsbdb'), None, Gtk.License.CUSTOM,
                                _('Dane społecznościowych sieci ADS-B (adsb.lol: ODbL) i trasy z adsbdb.com, do użytku niekomercyjnego.'))
        about.add_legal_section(_('Nasłuch wieży (LIVE) — LiveATC.net'), None, Gtk.License.CUSTOM,
                                _('Oficjalna strona odsłuchu LiveATC.net wyświetlana jak w przeglądarce; '
                                  'obowiązują warunki LiveATC.net. SkyTrack nie jest powiązany z LiveATC.'))
        about.add_legal_section(_('Linie lotnicze i trasy — OpenFlights'), None, Gtk.License.CUSTOM,
                                _('Open Database License (ODbL). https://openflights.org/data.php'))
        about.present(self.window)


def _crash_log():
    """Keep a crash log: Python errors and hard crashes (with the Python stack) are written to
    ~/.cache/linux-skytrack/crash.log, so a crash can be explained afterwards."""
    import faulthandler
    import time
    import traceback
    try:
        path = os.path.join(db.cache_dir(), "crash.log")
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            os.replace(path, path + ".old")
        f = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    f.write(f"\n=== SkyTrack {VERSION} started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    faulthandler.enable(file=f, all_threads=True)
    old = sys.excepthook

    def hook(tp, val, tb):
        f.write(time.strftime("%H:%M:%S ") + "".join(traceback.format_exception(tp, val, tb)))
        old(tp, val, tb)
    sys.excepthook = hook
    main._crash_file = f   # keep it open for the whole run


def main():
    _crash_log()
    app = SkyTrackApp()
    return app.run(sys.argv)
