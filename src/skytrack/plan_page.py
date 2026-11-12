"""Plans page: flight calculator (distance, time, local arrival) and upcoming trips."""
from datetime import date, timedelta

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

from . import geo, photos, stats
from .db import Trip
from .trip_dialog import AirportRow, DateRow, parse_time
from .widgets import PassCard
from .i18n import IS_PL, _, plural


class PlanPage(Gtk.ScrolledWindow):
    __gsignals__ = {
        "plan-trip": (GObject.SignalFlags.RUN_FIRST, None, (object, object, str)),  # Trip, return|None, album
        "edit": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "return-flight": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "show-trip": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "calendar": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, airports):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.airports = airports
        clamp = Adw.Clamp(maximum_size=860, tightening_threshold=600)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                      margin_top=24, margin_bottom=32, margin_start=16, margin_end=16)
        clamp.set_child(box)
        self.set_child(clamp)

        title = Gtk.Label(label=_('Planowanie'), xalign=0)
        title.add_css_class("title-1")
        box.append(title)

        # Calculator ---------------------------------------------------------------------
        kind = Gtk.Box(halign=Gtk.Align.CENTER)
        kind.add_css_class("linked")
        self.btn_round = Gtk.ToggleButton(label=_('Tam i z powrotem'), active=True)
        self.btn_oneway = Gtk.ToggleButton(label=_('Jeden lot'), group=self.btn_round)
        kind.append(self.btn_round)
        kind.append(self.btn_oneway)
        self.btn_round.connect("toggled", self._recalc)
        box.append(kind)

        calc = Adw.PreferencesGroup(
            title=_('Kalkulator podróży'),
            description=_('Ile kilometrów i ile w powietrzu, o której będziesz na miejscu i w domu w czasie lokalnym. Strefy czasowe i czas letni są uwzględnione.'))
        self.c_from = AirportRow(_('Skąd (wylatujesz)'), airports)
        self.c_to = AirportRow(_('Dokąd (cel podróży)'), airports)
        for r in (self.c_from, self.c_to):
            calc.add(r)
        box.append(calc)

        g_out = Adw.PreferencesGroup(title=_('Wylot'))
        self.c_date = DateRow(_('Data wylotu'), (date.today() + timedelta(days=14)).isoformat())
        self.c_time = Adw.EntryRow(title=_('Godzina startu (HH:MM, czas lokalny) — opcjonalnie'))
        self.c_time.add_prefix(Gtk.Image.new_from_icon_name("alarm-symbolic"))
        g_out.add(self.c_date)
        g_out.add(self.c_time)
        box.append(g_out)

        self.g_back = Adw.PreferencesGroup(title=_('Powrót'))
        self.r_date = DateRow(_('Data powrotu'), (date.today() + timedelta(days=21)).isoformat())
        self.r_time = Adw.EntryRow(title=_('Godzina startu powrotu (HH:MM, czas lokalny) — opcjonalnie'))
        self.r_time.add_prefix(Gtk.Image.new_from_icon_name("alarm-symbolic"))
        self.g_back.add(self.r_date)
        self.g_back.add(self.r_time)
        box.append(self.g_back)
        self._ret_touched = False

        res = Adw.PreferencesGroup()
        self.r_km = self._res_row(_('Dystans'), "mark-location-symbolic")
        self.r_dur = self._res_row(_('Czas lotu (szacunek)'), "alarm-symbolic")
        self.r_arr = self._res_row(_('Lądowanie u celu (czas lokalny)'), "skytrack-pin-symbolic")
        self.r_home = self._res_row(_('Lądowanie po powrocie (czas lokalny)'), "go-home-symbolic")
        self.r_stay = self._res_row(_('Na miejscu'), "x-office-calendar-symbolic")
        self.r_tz = self._res_row(_('Różnica stref'), "preferences-system-time-symbolic")
        self.r_when = self._res_row(_('Do wylotu'), "x-office-calendar-symbolic")
        self._rows = (self.r_km, self.r_dur, self.r_arr, self.r_home, self.r_stay, self.r_tz, self.r_when)
        for r in self._rows:
            res.add(r)
        # iCloud album (only when linux-icloud-photos is installed) ------------------------
        self.g_album = Adw.PreferencesGroup(
            title=_('Album w iCloud'),
            description=_('Linux iCloud Photos utworzy pusty album na zdjęcia z tej podróży i połączy go z nią. Po powrocie uzupełnisz go jednym kliknięciem („Album…” na karcie lotu).'))
        self.album_switch = Adw.SwitchRow(title=_('Utworzyć album w Linux iCloud Photos?'), active=True)
        self.album_switch.add_prefix(Gtk.Image.new_from_icon_name("folder-pictures-symbolic"))
        self.album_title = Adw.EntryRow(title=_('Tytuł albumu'))
        self.album_switch.bind_property("active", self.album_title, "sensitive",
                                        GObject.BindingFlags.SYNC_CREATE)
        self.g_album.add(self.album_switch)
        self.g_album.add(self.album_title)
        self.g_album.set_visible(photos.available())
        self._title_touched = False
        self._title_auto = ""
        self.album_title.connect("changed", self._on_title_changed)
        album_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=24)
        album_box.append(self.g_album)

        self.save_btn = Gtk.Button(label=_('Zapisz jako planowaną podróż'), halign=Gtk.Align.CENTER,
                                   margin_top=12, sensitive=False)
        self.save_btn.add_css_class("pill")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._on_plan)
        res_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        res_box.append(res)
        res_box.append(album_box)
        res_box.append(self.save_btn)
        box.append(res_box)

        for w in (self.c_from, self.c_to):
            w.connect("airport-changed", self._recalc)
        self.c_date.connect("date-changed", self._follow_return)
        self.c_date.connect("date-changed", self._recalc)
        self.c_time.connect("changed", self._recalc)
        self.r_date.connect("date-changed", self._on_ret_date)
        self.r_date.connect("date-changed", self._recalc)
        self.r_time.connect("changed", self._recalc)

        # Upcoming -------------------------------------------------------------------------
        up_title = Gtk.Label(label=_('NADCHODZĄCE PODRÓŻE'), xalign=0, margin_top=8)
        up_title.add_css_class("section-title")
        box.append(up_title)
        self.upcoming = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.append(self.upcoming)
        self._recalc()

    @staticmethod
    def _res_row(title, icon):
        r = Adw.ActionRow(title=title, subtitle="—")
        r.add_css_class("property")
        r.add_prefix(Gtk.Image.new_from_icon_name(icon))
        return r

    def set_home(self, ap):
        if ap and not self.c_from.airport:
            self.c_from.set_airport(ap)

    def _on_title_changed(self, row):
        if not getattr(self, "_setting_title", False) and row.get_text() != self._title_auto:
            self._title_touched = True

    def _suggest_title(self):
        """Default album title, e.g. '✈ Korfu · cze 2027' — until the user types their own."""
        a, b, d = self.c_from.airport, self.c_to.airport, self.c_date.get_value()
        if self._title_touched or not b or not d:
            return
        from .airports import CITY_PL
        mon = stats.MONTHS_GEN[int(d[5:7]) - 1]
        city = CITY_PL.get(b.city, b.short) if IS_PL else b.short
        if "(" in city and ")" in city:          # 'Kerkyra (Corfu)' -> 'Corfu'
            city = city[city.index("(") + 1:city.index(")")]
        self._title_auto = f"✈ {city} · {mon} {d[:4]}"
        if self.album_title.get_text() != self._title_auto:
            self._setting_title = True
            self.album_title.set_text(self._title_auto)
            self._setting_title = False

    def _on_ret_date(self, *_a):
        self._ret_touched = True

    def _follow_return(self, *_a):
        """Until the return date is typed in, it stays one week after the departure."""
        d = self.c_date.get_value()
        if d and not self._ret_touched:
            self.r_date.set_value((date.fromisoformat(d) + timedelta(days=7)).isoformat())

    @staticmethod
    def _time_of(row):
        t = parse_time(row.get_text())
        if t is None:
            row.add_css_class("error")
            return ""
        row.remove_css_class("error")
        return t

    def _recalc(self, *_a):
        round_trip = self.btn_round.get_active()
        self.g_back.set_visible(round_trip)
        self.r_home.set_visible(round_trip)
        self.r_stay.set_visible(round_trip)
        self.save_btn.set_label(_('Zapisz jako planowaną podróż') if round_trip else _('Zapisz jako planowany lot'))
        a, b, d = self.c_from.airport, self.c_to.airport, self.c_date.get_value()
        self._suggest_title()
        t = self._time_of(self.c_time)
        rd = self.r_date.get_value()
        rt = self._time_of(self.r_time)
        ok = bool(a and b and d and a.iata != b.iata and (not round_trip or (rd and rd >= d)))
        self.save_btn.set_sensitive(ok)
        if not (a and b and d and a.iata != b.iata):
            for r in self._rows:
                r.set_subtitle("—")
            return
        km = geo.distance_km(a.lat, a.lon, b.lat, b.lon)
        mins = geo.estimate_minutes(km)
        if round_trip:
            self.r_km.set_subtitle(_('{0} w każdą stronę · razem {1}').format(geo.fmt_km(km), geo.fmt_km(2 * round(km))))
            self.r_dur.set_subtitle(_('≈ {0} w każdą stronę  (≈ {1:.0f} km/h + 30 min)').format(geo.fmt_duration(mins), geo.CRUISE_KMH))
        else:
            self.r_km.set_subtitle(f"{geo.fmt_km(km)}  ·  {a.iata} → {b.iata}")
            self.r_dur.set_subtitle(_('{0}  (≈ {1:.0f} km/h + 30 min)').format(geo.fmt_duration(mins, True), geo.CRUISE_KMH))
        if t:
            ad, at = geo.arrival_estimate(d, t, a.tz, mins, b.tz)
            self.r_arr.set_subtitle(
                _('≈ {0}, {1} {2}   (start {3} {4})').format(stats.nice_date(ad, True), at, geo.utc_offset_label(b.tz, ad, at), t, geo.utc_offset_label(a.tz, d, t)))
        else:
            self.r_arr.set_subtitle(_('podaj godzinę startu wylotu'))
        if round_trip:
            if not rd or rd < d:
                self.r_home.set_subtitle("—")
                self.r_stay.set_subtitle(_('data powrotu przed wylotem'))
            else:
                if rt:
                    hd, ht = geo.arrival_estimate(rd, rt, b.tz, mins, a.tz)
                    self.r_home.set_subtitle(
                        _('≈ {0}, {1} {2}   (start {3} {4})').format(stats.nice_date(hd, True), ht, geo.utc_offset_label(a.tz, hd, ht), rt, geo.utc_offset_label(b.tz, rd, rt)))
                else:
                    self.r_home.set_subtitle(_('podaj godzinę startu powrotu'))
                days = (date.fromisoformat(rd) - date.fromisoformat(d)).days
                self.r_stay.set_subtitle(f"{stats.nice_date(d)} – {stats.nice_date(rd)} · "
                                         f"{days} {plural(days, 'dzień', 'dni', 'dni', 'day', 'days')}")
        self.r_tz.set_subtitle(f"{geo.tz_difference_label(a.tz, b.tz, d)}   ·   {a.tz} → {b.tz}")
        if geo.is_future(d, t, a.tz):
            self.r_when.set_subtitle(geo.countdown_label(d, t, a.tz))
        else:
            self.r_when.set_subtitle(_('data minęła: zapisze się jako odbyta podróż'))

    def _on_plan(self, *_a):
        a, b = self.c_from.airport, self.c_to.airport
        out = Trip(origin=a.iata, dest=b.iata, dep_date=self.c_date.get_value(),
                   dep_time=parse_time(self.c_time.get_text()) or "")
        back = None
        if self.btn_round.get_active():
            back = Trip(origin=b.iata, dest=a.iata, dep_date=self.r_date.get_value(),
                        dep_time=parse_time(self.r_time.get_text()) or "")
        album = ""
        if self.g_album.get_visible() and self.album_switch.get_active():
            album = self.album_title.get_text().strip()
        self.emit("plan-trip", out, back, album)

    def _on_card_click(self, _g, _n, x, y, card, trip_id):
        w = card.pick(x, y, Gtk.PickFlags.DEFAULT)
        while w is not None and w is not card:
            if isinstance(w, Gtk.Button):
                return                      # the card's own buttons handle this
            w = w.get_parent()
        self.emit("show-trip", trip_id)

    def refresh(self, all_infos):
        child = self.upcoming.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.upcoming.remove(child)
            child = nxt
        plans = stats.planned(all_infos)
        if not plans:
            empty = Adw.StatusPage(icon_name="x-office-calendar-symbolic",
                                   title=_('Brak zaplanowanych podróży'),
                                   description=_('Policz lot w kalkulatorze i zapisz go albo dodaj podróż z przyszłą datą. Gdy data minie, trafi do odbytych sama.'))
            empty.add_css_class("compact")
            self.upcoming.append(empty)
            return
        total = sum(i.km for i in plans)
        # one card per trip: the return flight of a there-and-back trip goes onto its outbound card
        by_group = {}
        for i in all_infos:
            if i.trip.trip_group:
                by_group.setdefault(i.trip.trip_group, []).append(i)
        cards, skip = [], set()
        for i in plans:
            if i.trip.id in skip:
                continue
            legs = sorted(by_group.get(i.trip.trip_group, []), key=lambda x: (x.trip.dep_date, x.trip.dep_time))
            caption = None
            if len(legs) == 2 and legs[0].trip.id == i.trip.id:
                caption = _('Tam i z powrotem · powrót {0}').format(stats.nice_date(legs[1].trip.dep_date))
                skip.add(legs[1].trip.id)
            elif len(legs) == 2:
                caption = _('Powrót · wylot {0}').format(stats.nice_date(legs[0].trip.dep_date))
            cards.append((i, caption))
        n = len(cards)
        word = plural(n, "podróż", "podróże", "podróży", "trip", "trips")
        m = len(plans)
        lw = plural(m, "lot", "loty", "lotów", "flight", "flights")
        info = Gtk.Label(xalign=0, label=_('{0} {1} ({2} {3}) · {4} · ok. {5} w powietrzu').format(n, word, m, lw, geo.fmt_km(total), geo.fmt_duration(sum((i.minutes for i in plans)))))
        info.add_css_class("dim-label")
        self.upcoming.append(info)
        for i, caption in cards:
            card = PassCard(i, caption=caption)
            if caption and caption.startswith(_('Tam i z powrotem')):
                card.ret_btn.set_visible(False)
            card.connect("edit", lambda _c, tr: self.emit("edit", tr))
            card.connect("return-flight", lambda _c, tr: self.emit("return-flight", tr))
            card.connect("calendar", lambda _c, info: self.emit("calendar", info))
            click = Gtk.GestureClick()
            click.connect("released", self._on_card_click, card, i.trip.id)
            card.add_controller(click)
            self.upcoming.append(card)
