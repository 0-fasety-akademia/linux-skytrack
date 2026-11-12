"""'Na żywo' page: track a flight by number (or callsign) on its own map, with OpenSky data."""
import time
from datetime import date, datetime, timedelta

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, GObject, Gtk

import json

from . import adsb, geo, live, stats
from .traffic import TrafficFeed, compact
from .i18n import _
from .mapview import MapView
from .trip_dialog import AirportRow

STATUS = {
    "idle": ("", ""),
    "waiting": ("skytrack-plane-symbolic", "Czeka na start"),
    "searching": ("system-search-symbolic", "Szukam samolotu…"),
    "airborne": ("skytrack-plane-symbolic", "W powietrzu"),
    "ground": ("mark-location-symbolic", "Na ziemi"),
    "landed": ("emblem-ok-symbolic", "Wylądował"),
    "lost": ("network-wireless-signal-none-symbolic", "Brak sygnału"),
    "error": ("dialog-warning-symbolic", "Problem z danymi"),
    "stopped": ("media-playback-stop-symbolic", "Zatrzymane"),
}
INTERVALS = [15, 30, 60, 120]


def esc(s):
    return GLib.markup_escape_text(str(s))


def _ago(ts):
    if not ts:
        return "—"
    s = int(time.time() - ts)
    if s < 60:
        return _('{0} s temu').format(max(s, 0))
    if s < 3600:
        return _('{0} min temu').format(s // 60)
    return _('{0} h temu').format(s // 3600)


class LivePage(Adw.Bin):
    __gsignals__ = {"show-trip": (GObject.SignalFlags.RUN_FIRST, None, (int,))}

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.tracker = app.tracker
        self._fit_next = True
        self._infos = []
        self._visible = False
        self.traffic = TrafficFeed()
        self._icao_names = None

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, shrink_start_child=False,
                          resize_start_child=False, position=400)
        side_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, width_request=340)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=18, margin_bottom=18,
                       margin_start=16, margin_end=16)
        side_scroll.set_child(side)
        side_scroll.add_css_class("trip-sidebar")

        # query ----------------------------------------------------------------------------------
        g_q = Adw.PreferencesGroup(title=_('Śledź lot'),
                                   description=_('Numer lotu (np. W6 1729, LO 3803) albo znak wywoławczy (np. RYR5TG).'))
        self.q_row = Adw.EntryRow(title=_('Numer lotu lub znak wywoławczy'))
        self.q_row.add_prefix(Gtk.Image(icon_name="skytrack-plane-symbolic"))
        self.q_row.connect("entry-activated", self._on_track)
        g_q.add(self.q_row)
        self.dest_row = AirportRow(_('Dokąd (opcjonalnie — do czasu przylotu)'), app.airports)
        g_q.add(self.dest_row)
        btn = Gtk.Button(label=_('Śledź'), css_classes=["suggested-action", "pill"], halign=Gtk.Align.CENTER,
                         margin_top=10)
        btn.connect("clicked", self._on_track)
        side.append(g_q)
        side.append(btn)

        # traffic --------------------------------------------------------------------------------
        g_tr = Adw.PreferencesGroup(title=_('Ruch lotniczy'))
        self.traffic_switch = Adw.SwitchRow(
            title=_('Wszystkie samoloty na mapie'),
            subtitle=_('kliknij samolot: skąd, dokąd, wysokość, prędkość'),
            active=bool(app.settings["live_traffic"]))
        self.traffic_switch.connect("notify::active", self._on_traffic_switch)
        g_tr.add(self.traffic_switch)
        self.traffic_row = Adw.ActionRow(title=_('W widoku'), subtitle="—", css_classes=["property"])
        g_tr.add(self.traffic_row)
        side.append(g_tr)

        # my flights ------------------------------------------------------------------------------
        self.g_mine = Adw.PreferencesGroup(title=_('Moje loty'),
                                           description=_('Loty z dziennika na wczoraj, dziś i jutro.'))
        self._mine_rows = []
        side.append(self.g_mine)

        # status ----------------------------------------------------------------------------------
        self.g_status = Adw.PreferencesGroup()
        self.stop_btn = Gtk.Button(icon_name="media-playback-stop-symbolic", tooltip_text=_('Zakończ śledzenie'),
                                   css_classes=["flat"], valign=Gtk.Align.CENTER)
        self.stop_btn.connect("clicked", lambda *_a: self.tracker.stop())
        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_('Odśwież teraz'),
                                      css_classes=["flat"], valign=Gtk.Align.CENTER)
        self.refresh_btn.connect("clicked", lambda *_a: self.tracker.poll_now())
        hs = Gtk.Box(spacing=2)
        hs.append(self.refresh_btn)
        hs.append(self.stop_btn)
        self.g_status.set_header_suffix(hs)
        self.rows = {}
        for key, title, icon in (
                ("status", _('Status'), "skytrack-plane-symbolic"),
                ("alt", _('Wysokość'), "go-up-symbolic"),
                ("speed", _('Prędkość'), "skytrack-route-symbolic"),
                ("track", _('Kurs'), "find-location-symbolic"),
                ("vrate", _('Prędkość pionowa'), "object-flip-vertical-symbolic"),
                ("remaining", _('Do celu'), "skytrack-pin-symbolic"),
                ("eta", _('Przylot (szacunek)'), "alarm-symbolic"),
                ("sched", _('Przylot planowy'), "x-office-calendar-symbolic"),
                ("contact", _('Ostatni sygnał'), "network-wireless-symbolic"),
                ("aircraft", _('Samolot'), "dialog-information-symbolic")):
            row = Adw.ActionRow(title=title, css_classes=["property"])
            row.add_prefix(Gtk.Image(icon_name=icon))
            self.g_status.add(row)
            self.rows[key] = row
        self.follow = Adw.SwitchRow(title=_('Podążaj za samolotem na mapie'), active=True)
        self.g_status.add(self.follow)
        self.msg = Gtk.Label(wrap=True, xalign=0, css_classes=["dim-label", "caption"], margin_top=8, visible=False)
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        status_box.append(self.g_status)
        status_box.append(self.msg)
        self.status_box = status_box
        side.append(status_box)

        # settings --------------------------------------------------------------------------------
        g_set = Adw.PreferencesGroup(title=_('Ustawienia śledzenia'))
        exp = Adw.ExpanderRow(title=_('Źródła danych'),
                              subtitle=_('adsb.lol / airplanes.live / adsb.fi, zapasowo OpenSky'))
        self.exp = exp
        self.auto = Adw.SwitchRow(title=_('Śledź moje loty automatycznie'),
                                  subtitle=_('w dniu wylotu, gdy lot ma numer; powiadomi o starcie, opóźnieniu i lądowaniu'),
                                  active=bool(app.settings["live_auto"]))
        self.auto.connect("notify::active", lambda r, _p: app.settings.__setitem__("live_auto", r.get_active()))
        exp.add_row(self.auto)
        self.interval = Adw.ComboRow(title=_('Odświeżanie'),
                                     model=Gtk.StringList.new([_('co {0} s').format(i) for i in INTERVALS]))
        cur = int(app.settings["live_interval"] or 60)
        self.interval.set_selected(INTERVALS.index(cur) if cur in INTERVALS else 1)
        self.interval.connect("notify::selected", lambda r, _p: app.settings.__setitem__(
            "live_interval", INTERVALS[r.get_selected()]))
        exp.add_row(self.interval)
        cid, secret = live.load_credentials()
        self.cid = Adw.EntryRow(title=_('Konto OpenSky: client id (opcjonalnie)'), text=cid)
        self.secret = Adw.PasswordEntryRow(title=_('client secret'), text=secret)
        exp.add_row(self.cid)
        exp.add_row(self.secret)
        save = Gtk.Button(label=_('Zapisz konto'), valign=Gtk.Align.CENTER)
        save.connect("clicked", self._on_save_account)
        acc = Adw.ActionRow(title=_('Darmowe konto daje 4000 zapytań dziennie'),
                            subtitle=_('opensky-network.org → Account → API client'))
        acc.add_suffix(save)
        exp.add_row(acc)
        self.credits_row = Adw.ActionRow(title=_('Pozostało dziś'), subtitle="—", css_classes=["property"])
        exp.add_row(self.credits_row)
        g_set.add(exp)
        side.append(g_set)
        attr = Gtk.Label(use_markup=True, wrap=True, xalign=0, css_classes=["dim-label", "caption"],
                         label=_('Dane na żywo: <a href="https://adsb.lol">adsb.lol</a>, '
                                 '<a href="https://airplanes.live">airplanes.live</a>, <a href="https://adsb.fi">adsb.fi</a> '
                                 'i <a href="https://opensky-network.org">The OpenSky Network</a>; trasy: '
                                 '<a href="https://www.adsbdb.com">adsbdb</a>. Pozycje z odbiorników ADS-B '
                                 'wolontariuszy — nad oceanami może ich nie być, a trasa bywa nieaktualna.'))
        side.append(attr)

        # map --------------------------------------------------------------------------------------
        self.map = MapView(app.web_dir, layer=app.settings["map_layer"],
                           dark=Adw.StyleManager.get_default().get_dark(), theme=app.settings["theme"])
        self.map.set_mode("live")
        self.map.connect("map-event", self._on_map_event)
        self.traffic.connect("planes", self._on_planes)
        self.traffic.connect("status", self._on_traffic_status)
        Adw.StyleManager.get_default().connect(
            "notify::dark", lambda sm, _p: self.map.set_theme(self.app.settings["theme"], sm.get_dark()))

        paned.set_start_child(side_scroll)
        paned.set_end_child(self.map)
        self.set_child(paned)

        self.tracker.connect("update", lambda *_a: self._update())
        GLib.timeout_add_seconds(5, self._tick)
        self._update()

    # data from the window ------------------------------------------------------------------------
    def set_trips(self, infos):
        self._infos = infos
        for r in self._mine_rows:
            self.g_mine.remove(r)
        self._mine_rows = []
        today = date.today()
        days = {(today - timedelta(days=1)).isoformat(): _('wczoraj'), today.isoformat(): _('dziś'),
                (today + timedelta(days=1)).isoformat(): _('jutro')}
        mine = sorted([i for i in infos if i.trip.dep_date in days],
                      key=lambda i: (i.trip.dep_date, i.trip.dep_time))
        if not mine:
            r = Adw.ActionRow(title=_('Brak lotów w tych dniach'),
                              subtitle=_('W dniu wylotu SkyTrack sam zacznie śledzić loty z numerem lotu.'))
            r.add_css_class("dim-label")
            self.g_mine.add(r)
            self._mine_rows.append(r)
            return
        for i in mine:
            t = i.trip
            when = days[t.dep_date] + (f", {t.dep_time}" if t.dep_time else "")
            r = Adw.ActionRow(title=esc(f"{t.flight_no or '—'} · {t.origin} → {t.dest}"),
                              subtitle=esc(f"{when} · {i.origin.short} → {i.dest.short}"))
            r.add_prefix(Gtk.Image(icon_name="skytrack-plane-symbolic"))
            if t.flight_no:
                b = Gtk.Button(label=_('Śledź'), valign=Gtk.Align.CENTER)
                b.connect("clicked", lambda _b, info=i: self.track_trip(info))
            else:
                b = Gtk.Button(label=_('Dodaj numer lotu'), valign=Gtk.Align.CENTER, css_classes=["flat"])
                b.connect("clicked", lambda _b, tid=t.id: self.emit("show-trip", tid))
            r.add_suffix(b)
            self.g_mine.add(r)
            self._mine_rows.append(r)

    # traffic --------------------------------------------------------------------------------------------
    def set_visible_page(self, visible):
        self._visible = visible
        if visible and not getattr(self, "_centered", False) and self.tracker.s is None:
            home = self._home_airport()
            if home is not None:
                self._centered = True
                self.map.call("SkyMap.setView", home.lat, home.lon, 6)
        self._sync_traffic()

    def _home_airport(self):
        """Where the map starts: the airport you fly from most often."""
        from collections import Counter
        c = Counter(i.trip.origin for i in self._infos or [])
        code = c.most_common(1)[0][0] if c else None
        return self.app.airports.get(code) if code else None

    def _sync_traffic(self):
        on = self._visible and self.traffic_switch.get_active() and bool(self._infos is not None)
        self.traffic.set_active(on)
        if on:
            self.map.call("SkyMap.reportView")
        else:
            self.map.set_traffic([])
            self.traffic_row.set_subtitle("—")

    def _on_traffic_switch(self, row, _p):
        self.app.settings["live_traffic"] = row.get_active()
        self._sync_traffic()

    def _on_planes(self, _feed, planes):
        if not self.traffic.active:
            return
        s = self.tracker.s
        skip = s.icao24 if s and not s.from_map else None      # a plane picked on the map stays a map plane
        self.map.set_traffic(compact(planes, skip))
        n = len(planes)
        src = self.traffic.feed.last_provider
        from .i18n import plural
        word = plural(n, "samolot", "samoloty", "samolotów", "aircraft", "aircraft")
        self.traffic_row.set_subtitle(f"{n} {word} · {src}")

    def _on_traffic_status(self, _feed, status):
        if status == "error":
            self.traffic_row.set_subtitle(_('Brak połączenia z sieciami ADS-B — spróbuję za chwilę'))
        elif status == "wide":
            self.traffic_row.set_subtitle(self.traffic_row.get_subtitle() + " · " +
                                          _('tylko 460 km od środka mapy — przybliż'))

    def _airline_name(self, callsign):
        if self._icao_names is None:
            self._icao_names = {v[0]: v[1] for v in live.airlines().values()}
        cs = callsign or ""
        return self._icao_names.get(cs[:3], "") if len(cs) > 3 and cs[:3].isalpha() else ""

    def _plane_lines(self, p):
        lines = []
        if p.on_ground:
            lines.append(_('Na ziemi') + (f" · {geo.fmt_int((p.speed_ms or 0) * 3.6)} km/h" if p.speed_ms else ""))
        else:
            alt = f"{geo.fmt_int(p.alt_m)} m" if p.alt_m is not None else "—"
            spd = f"{geo.fmt_int((p.speed_ms or 0) * 3.6)} km/h" if p.speed_ms is not None else "—"
            lines.append(_('Wysokość {0} · {1} · kurs {2}°').format(alt, spd, round(p.track or 0)))
        ac = " · ".join(x for x in (p.desc or p.type, p.reg) if x)
        if ac:
            lines.append(ac)
        return lines

    def _on_map_event(self, _map, kind, payload):
        msg = json.loads(payload)
        if kind == "view":
            try:
                self.traffic.set_view(float(msg["lat"]), float(msg["lon"]), float(msg["nm"]))
            except (KeyError, TypeError, ValueError):
                pass
        elif kind == "map-click":
            self._end_map_tracking()
        elif kind == "plane":
            hexcode = str(msg.get("hex", ""))
            s = self.tracker.s
            if s is not None and s.icao24 != hexcode:
                self._end_map_tracking()
            p = self.traffic.planes.get(hexcode)
            if p is None:
                return
            info = {"hex": hexcode, "title": p.callsign or hexcode.upper(),
                    "subtitle": self._airline_name(p.callsign),
                    "lines": [(_('Trasa: szukam…') if p.callsign else _('Trasa nieznana'))] + self._plane_lines(p),
                    **self._track_action(hexcode)}
            self.map.plane_info(info)
            if p.callsign:
                adsb.route_async(p.callsign, lambda r, hx=hexcode: self._show_route(hx, r), p.lat, p.lon)
        elif kind == "track":
            hexcode = str(msg.get("hex", ""))
            p = self.traffic.planes.get(hexcode)
            cs = p.callsign if p else ""
            self._fit_next = True
            a = b = None
            src = ""
            cached = getattr(self, "_routes", {}).get(hexcode)
            if cached:
                a, b, src = cached
            self.q_row.set_text(cs or hexcode.upper())
            self.dest_row.set_airport(b)
            self.tracker.start_hex(hexcode, cs, a, b, src)

    def _show_route(self, hexcode, route):
        p = self.traffic.planes.get(hexcode)
        if p is None:
            return
        a, b = adsb.resolve_route(route, self.app.airports, (p.lat, p.lon))
        if not hasattr(self, "_routes"):
            self._routes = {}
        self._routes[hexcode] = (a, b, route.get("source", ""))
        if a and b:
            from .wrapped import city
            line = f"{a.iata} {city(a)} → {b.iata} {city(b)}"
            if not route.get("plausible", True):
                line += " " + _('(niepewna)')
            r = {"from": a.to_js(), "to": b.to_js()}
        else:
            line, r = _('Trasa nieznana'), None
        subtitle = route.get("airline") or self._airline_name(p.callsign)
        self.map.plane_info({"hex": hexcode, "title": p.callsign or hexcode.upper(), "subtitle": subtitle,
                             "lines": [line] + self._plane_lines(p), "route": r, **self._track_action(hexcode)})

    def _track_action(self, hexcode):
        s = self.tracker.s
        if s is not None and s.icao24 == hexcode and s.status not in ("stopped", "landed"):
            return {"tracking": _('Śledzę ten lot')}
        return {"track": _('Śledź ten lot'), "trackingLabel": _('Śledzę ten lot')}

    def _end_map_tracking(self):
        """A click on the map (or on another plane) ends tracking — except for your own flight
        from the log, which stays until you press ■."""
        s = self.tracker.s
        if s is None or s.trip_id is not None:
            return
        self.tracker.clear()
        self.q_row.set_text("")
        self.dest_row.set_airport(None)
        self._fit_next = True

    def set_theme(self, name):
        self.map.set_theme(name, Adw.StyleManager.get_default().get_dark())

    # actions -----------------------------------------------------------------------------------------
    def track_trip(self, info):
        self.q_row.set_text(info.trip.flight_no)
        self.dest_row.set_airport(info.dest)
        self._fit_next = True
        self.tracker.start(info.trip.flight_no, trip_info=info)

    def _on_track(self, *_a):
        text = self.q_row.get_text().strip()
        if not text:
            self.q_row.grab_focus()
            return
        # a flight from the log with this number today/yesterday/tomorrow gives the route and times
        cs, _airline, _label = live.parse_query(text)
        today = date.today()
        near = {(today + timedelta(days=d)).isoformat() for d in (-1, 0, 1)}
        for i in self._infos:
            if i.trip.dep_date in near and i.trip.flight_no and live.parse_query(i.trip.flight_no)[0] & cs:
                self.track_trip(i)
                return
        self._fit_next = True
        if not self.tracker.start(text, dest=self.dest_row.airport):
            self._toast(_('Nie rozpoznaję „{0}”. Wpisz np. W6 1729 albo znak wywoławczy RYR5TG.').format(text))

    def _on_save_account(self, *_a):
        live.save_credentials(self.cid.get_text().strip(), self.secret.get_text().strip())
        self.tracker.api.reload_credentials()
        self._toast(_('Zapisano konto OpenSky') if self.cid.get_text().strip() else _('Usunięto konto OpenSky'))

    def _toast(self, text):
        root = self.get_root()
        if hasattr(root, "toasts"):
            root.toasts.add_toast(Adw.Toast(title=text, timeout=5))

    # view ---------------------------------------------------------------------------------------------
    def _tick(self):
        s = self.tracker.s
        if s and s.state:
            self.rows["contact"].set_subtitle(_ago(s.state.last_contact))
        return True

    def _update(self):
        tr = self.tracker
        s = tr.s
        rem = tr.api.remaining
        self.credits_row.set_subtitle(str(rem) if rem is not None else "—")
        if s is None:
            self.status_box.set_visible(False)
            self.map.set_live(None)
            return
        self.status_box.set_visible(True)
        title = s.label + (f" · {s.airline}" if s.airline else "")
        self.g_status.set_title(esc(title))
        route = (f"{s.origin.iata} → {s.dest.iata} · {s.origin.short} → {s.dest.short}" if s.origin and s.dest
                 else (f"→ {s.dest.iata} · {s.dest.short}" if s.dest else _('trasa nieznana — podaj „Dokąd”, żeby zobaczyć czas przylotu')))
        if s.origin and s.dest and s.route_source not in ("", "log", "user"):
            route += " · " + _('trasa wg {0}').format(s.route_source)
        if s.source:
            route += " · " + _('dane: {0}').format(s.source)
        self.g_status.set_description(esc(route))
        icon, label = STATUS.get(s.status, ("", s.status))
        self.rows["status"].set_subtitle(_(label) if label else "—")
        st = s.state
        if st:
            alt = st.alt_m or 0
            self.rows["alt"].set_subtitle("—" if st.on_ground else f"{geo.fmt_int(alt)} m · {geo.fmt_int(alt * 3.28084)} ft")
            kmh = (st.speed_ms or 0) * 3.6
            self.rows["speed"].set_subtitle(f"{geo.fmt_int(kmh)} km/h · {geo.fmt_int((st.speed_ms or 0) * 1.94384)} kt")
            self.rows["track"].set_subtitle(f"{round(st.track or 0)}°")
            vr = st.vrate or 0
            arrow = "↑" if vr > 0.5 else "↓" if vr < -0.5 else "→"
            self.rows["vrate"].set_subtitle(f"{arrow} {geo.fmt_dec(abs(vr))} m/s")
            self.rows["contact"].set_subtitle(_ago(st.last_contact))
            parts = [st.callsign, st.desc or st.type, st.reg, f"ICAO {st.icao24.upper()}", st.country]
            self.rows["aircraft"].set_subtitle(esc(" · ".join(x for x in parts if x)))
        else:
            for k in ("alt", "speed", "track", "vrate", "contact", "aircraft"):
                self.rows[k].set_subtitle("—")
        r = tr.remaining_km()
        self.rows["remaining"].set_subtitle(geo.fmt_km(r) if r is not None else "—")
        eta = tr.eta()
        if s.status == "landed":
            self.rows["eta"].set_subtitle(_('wylądował'))
        elif eta:
            txt = _('{0} czasu lokalnego').format(tr.local_time(eta, s.dest))
            if s.sched_arr:
                diff = int((eta - s.sched_arr).total_seconds() // 60)
                if diff > 5:
                    txt += " · " + _('+{0} min').format(diff)
                elif diff < -5:
                    txt += " · " + _('{0} min wcześniej').format(-diff)
                else:
                    txt += " · " + _('o czasie')
            self.rows["eta"].set_subtitle(txt)
        else:
            self.rows["eta"].set_subtitle("—")
        self.rows["sched"].set_subtitle(tr.local_time(s.sched_arr, s.dest) if s.sched_arr else "—")
        self.rows["sched"].set_visible(s.sched_arr is not None)
        self.rows["remaining"].set_visible(s.dest is not None)
        self.stop_btn.set_sensitive(s.status not in ("stopped", "landed"))
        self.refresh_btn.set_sensitive(s.status not in ("stopped", "landed"))
        self.msg.set_label(s.message)
        self.msg.set_visible(bool(s.message))
        # The map never zooms by itself: the dashed route is drawn, and you zoom out if you want
        # to see where the plane is going. A plane picked on the traffic map keeps its map marker
        # (and popup) and the view stays put; a flight typed in the panel is centred once when
        # found, then followed if "Podążaj" is on.
        if s.from_map and self.traffic.active:
            data = tr.map_data(follow=False)
            data.pop("pos", None)
            center = False
        else:
            data = tr.map_data(follow=self.follow.get_active())
            center = self._fit_next and s.state is not None
        data["center"] = center
        self.map.set_live(data, True)
        if s.state is not None:
            self._fit_next = False
