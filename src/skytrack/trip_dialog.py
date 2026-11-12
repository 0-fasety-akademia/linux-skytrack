"""Add / edit trip dialog."""
import re
import uuid
from datetime import date, timedelta

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, GObject, Gtk

from . import geo
from .db import Trip
from .stats import nice_date
from .i18n import _, plural

TIME_RE = re.compile(r"^([01]?\d|2[0-3])[:.]?([0-5]\d)$")


def parse_time(text):
    """'7:05', '0705', '07.05' -> '07:05'; '' -> ''; invalid -> None."""
    text = text.strip()
    if not text:
        return ""
    m = TIME_RE.match(text)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


class AirportRow(Adw.EntryRow):
    """Entry row with a live airport suggestion popover."""

    __gsignals__ = {"airport-changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, title, airports):
        super().__init__(title=title)
        self.airports = airports
        self.airport = None
        self._setting = False

        self.icon = Gtk.Image.new_from_icon_name("mark-location-symbolic")
        self.add_prefix(self.icon)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("navigation-sidebar")
        self.listbox.connect("row-activated", self._on_pick)
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                propagate_natural_height=True, max_content_height=320)
        sc.set_child(self.listbox)
        self.popover = Gtk.Popover(autohide=False, has_arrow=False, can_focus=False,
                                   position=Gtk.PositionType.BOTTOM)
        self.popover.set_child(sc)
        self.popover.set_parent(self)
        self.popover.set_size_request(440, -1)
        self._results = []

        self.connect("changed", self._on_changed)
        self.connect("entry-activated", self._on_enter)
        self.connect("destroy", lambda *_: self.popover.unparent())
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: GLib.timeout_add(150, self._hide_later))
        self.add_controller(focus)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

    def _hide_later(self):
        self.popover.popdown()
        return False

    def set_airport(self, ap):
        self._setting = True
        self.airport = ap
        self.set_text(ap.label if ap else "")
        self._setting = False
        self.popover.popdown()
        self.remove_css_class("error")
        self.emit("airport-changed")

    def _on_changed(self, *_a):
        if self._setting:
            return
        if self.airport is not None:
            self.airport = None
            self.emit("airport-changed")
        self._results = self.airports.search(self.get_text(), limit=8)
        self.listbox.remove_all()
        for ap in self._results:
            row = Adw.ActionRow(title=GLib.markup_escape_text(f"{ap.iata} · {ap.short}"),
                                subtitle=GLib.markup_escape_text(f"{ap.name} · {ap.country}"),
                                activatable=True)
            row.ap = ap
            self.listbox.append(row)
        if self._results:
            self.popover.popup()
        else:
            self.popover.popdown()

    def _on_pick(self, _lb, row):
        self.set_airport(row.ap)

    def _on_enter(self, *_a):
        if self.airport is None and self._results:
            self.set_airport(self._results[0])

    def _on_key(self, _ctl, keyval, _code, _state):
        from gi.repository import Gdk
        if keyval == Gdk.KEY_Escape and self.popover.get_visible():
            self.popover.popdown()
            return True
        if keyval in (Gdk.KEY_Down,) and self._results and self.popover.get_visible():
            first = self.listbox.get_row_at_index(0)
            if first:
                first.grab_focus()
            return True
        return False


class DateRow(Adw.EntryRow):
    """Date typed as DD.MM.RRRR (fast for historical trips) or picked from a calendar."""

    __gsignals__ = {"date-changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, title, value=None):
        super().__init__(title=_('{0} (DD.MM.RRRR)').format(title))
        self.add_prefix(Gtk.Image.new_from_icon_name("x-office-calendar-symbolic"))
        self.weekday = Gtk.Label(valign=Gtk.Align.CENTER)
        self.weekday.add_css_class("dim-label")
        self.weekday.add_css_class("caption")
        self.add_suffix(self.weekday)
        self.calendar = Gtk.Calendar()
        self.button = Gtk.MenuButton(icon_name="x-office-calendar-symbolic", valign=Gtk.Align.CENTER,
                                     tooltip_text=_('Wybierz z kalendarza'))
        self.button.add_css_class("flat")
        pop = Gtk.Popover()
        pop.set_child(self.calendar)
        self.button.set_popover(pop)
        self.add_suffix(self.button)
        self._value = None
        self._setting = False
        self.calendar.connect("day-selected", self._on_day)
        self.connect("changed", self._on_text)
        self.set_value(value or date.today().isoformat())

    def set_value(self, iso):
        self._setting = True
        self._value = iso
        self.set_text(geo.fmt_date_pl(iso))
        d = date.fromisoformat(iso)
        self.calendar.select_day(GLib.DateTime.new_local(d.year, d.month, d.day, 12, 0, 0))
        self._setting = False
        self._update_hint()

    def get_value(self):
        return self._value

    def _update_hint(self):
        if self._value:
            self.weekday.set_label(nice_date(self._value, with_weekday=True).split(",")[0])
            self.remove_css_class("error")
        else:
            self.weekday.set_label("")
            if self.get_text().strip():
                self.add_css_class("error")

    def _on_text(self, *_a):
        if self._setting:
            return
        self._value = geo.parse_date(self.get_text())
        if self._value:
            d = date.fromisoformat(self._value)
            self._setting = True
            self.calendar.select_day(GLib.DateTime.new_local(d.year, d.month, d.day, 12, 0, 0))
            self._setting = False
        self._update_hint()
        self.emit("date-changed")

    def _on_day(self, cal):
        if self._setting:
            return
        dt = cal.get_date()
        self.set_value(f"{dt.get_year():04d}-{dt.get_month():02d}-{dt.get_day_of_month():02d}")
        self.button.get_popover().popdown()
        self.emit("date-changed")


class LegEditor:
    """Date, take-off time, optional landing and flight number of one flight (one leg)."""

    def __init__(self, title, date_title, iso_date):
        self.group = Adw.PreferencesGroup(title=title)
        self.date = DateRow(date_title, iso_date)
        self.dep_time = Adw.EntryRow(title=_('Godzina startu (HH:MM, czas lokalny) — opcjonalnie'))
        self.dep_time.add_prefix(Gtk.Image.new_from_icon_name("alarm-symbolic"))
        self.land = Adw.ExpanderRow(title=_('Godzina lądowania'), subtitle=_('opcjonalnie — dokładny czas lotu'),
                                    show_enable_switch=True, enable_expansion=False)
        self.arr_date = DateRow(_('Data lądowania'), iso_date)
        self.arr_time = Adw.EntryRow(title=_('Godzina lądowania (HH:MM, czas lokalny)'))
        self.arr_time.add_prefix(Gtk.Image.new_from_icon_name("alarm-symbolic"))
        self.land.add_row(self.arr_date)
        self.land.add_row(self.arr_time)
        self.flight_no = Adw.EntryRow(title=_('Numer lotu (np. LO 3803) — opcjonalnie'))
        self.seat = Adw.EntryRow(title=_('Miejsce — opcjonalnie'))
        for r in (self.date, self.dep_time, self.land, self.flight_no, self.seat):
            self.group.add(r)
        self.date.connect("date-changed", self._sync_arr_date)

    def _sync_arr_date(self, *_a):
        if not self.land.get_enable_expansion() and self.date.get_value():
            self.arr_date.set_value(self.date.get_value())

    def fill(self, t):
        self.date.set_value(t.dep_date)
        self.dep_time.set_text(t.dep_time)
        self.arr_date.set_value(t.arr_date or t.dep_date)
        if t.arr_time:
            self.land.set_enable_expansion(True)
            self.land.set_expanded(True)
            self.arr_time.set_text(t.arr_time)
        self.flight_no.set_text(t.flight_no)
        self.seat.set_text(t.seat)

    def connect_changed(self, cb):
        self.date.connect("date-changed", cb)
        self.arr_date.connect("date-changed", cb)
        self.dep_time.connect("changed", cb)
        self.arr_time.connect("changed", cb)
        self.land.connect("notify::enable-expansion", cb)

    def mark_times(self):
        for row in (self.dep_time, self.arr_time):
            if parse_time(row.get_text()) is None:
                row.add_css_class("error")
            else:
                row.remove_css_class("error")

    def values(self, a, b, what):
        """(dict, None) or (None, error message). a/b = origin/destination airports of this leg."""
        d = self.date.get_value()
        if not d:
            self.date.add_css_class("error")
            return None, _('Data {0} w formacie DD.MM.RRRR, np. 31.08.2025').format(what)
        dep_t = parse_time(self.dep_time.get_text())
        if dep_t is None:
            return None, _('Godzina startu ({0}) w formacie HH:MM, np. 20:25').format(what)
        arr_d, arr_t = "", ""
        if self.land.get_enable_expansion():
            arr_t = parse_time(self.arr_time.get_text())
            if not arr_t:
                return None, _('Podaj godzinę lądowania ({0}) albo wyłącz lądowanie').format(what)
            arr_d = self.arr_date.get_value()
            if not arr_d:
                return None, _('Data lądowania ({0}) w formacie DD.MM.RRRR').format(what)
            if dep_t and geo.real_minutes(d, dep_t, a.tz, arr_d, arr_t, b.tz) is None:
                return None, _('Lądowanie musi być po starcie ({0}) — sprawdź daty i strefy czasowe').format(what)
        return {"dep_date": d, "dep_time": dep_t, "arr_date": arr_d, "arr_time": arr_t,
                "flight_no": re.sub(r"\s+", " ", self.flight_no.get_text().strip().upper()),
                "seat": self.seat.get_text().strip().upper()}, None

    def minutes(self, a, b):
        """(minutes, estimated?) for this leg."""
        d = self.date.get_value()
        dep_t = parse_time(self.dep_time.get_text()) or ""
        arr_t = parse_time(self.arr_time.get_text()) or ""
        if d and self.land.get_enable_expansion() and dep_t and arr_t:
            real = geo.real_minutes(d, dep_t, a.tz, self.arr_date.get_value(), arr_t, b.tz)
            if real is not None:
                return real, False
        return geo.estimate_minutes(geo.distance_km(a.lat, a.lon, b.lat, b.lon)), True

    def landing(self, a, b):
        """'pon, 1 wrz 2025, 00:34 (UTC+3)' or a hint; estimated landings are marked with ≈."""
        d = self.date.get_value()
        dep_t = parse_time(self.dep_time.get_text()) or ""
        arr_t = parse_time(self.arr_time.get_text()) or ""
        if not d:
            return "—"
        if self.land.get_enable_expansion() and arr_t and self.arr_date.get_value():
            ad = self.arr_date.get_value()
            return f"{nice_date(ad, True)}, {arr_t} ({geo.utc_offset_label(b.tz, ad, arr_t)})"
        mins, _est = self.minutes(a, b)
        ad, at = geo.arrival_estimate(d, dep_t, a.tz, mins, b.tz)
        if not ad:
            return _('podaj godzinę startu, żeby policzyć')
        return f"≈ {nice_date(ad, True)}, {at} ({geo.utc_offset_label(b.tz, ad, at)})"


class TripDialog(Adw.Dialog):
    """Add / edit a trip: there-and-back (two flights with one group id) or a single flight."""

    __gsignals__ = {
        "saved": (GObject.SignalFlags.RUN_FIRST, None, (object, bool)),    # [Trip, ...], next_leg
        "deleted": (GObject.SignalFlags.RUN_FIRST, None, (object,)),        # [id, ...]
    }

    def __init__(self, airports, trip=None, return_trip=None, home_airport=None, title=None,
                 album_picker=None, round_trip=None):
        editing = trip is not None and trip.id is not None
        if round_trip is None:
            round_trip = return_trip is not None or (not editing and trip is None)
        super().__init__(title=title or (_('Edytuj podróż') if editing else _('Nowa podróż')),
                         content_width=600, content_height=820)
        self.airports = airports
        self.editing = editing
        self.trip = trip or Trip(origin="", dest="", dep_date=date.today().isoformat())
        self.ret_trip = return_trip
        self.round = round_trip

        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label=_('Anuluj'))
        cancel.connect("clicked", lambda *_: self.close())
        self.save_btn = Gtk.Button(label=_('Zapisz'))
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", lambda *_: self._on_save())
        hb.pack_start(cancel)
        hb.pack_end(self.save_btn)
        tv.add_top_bar(hb)

        self.toasts = Adw.ToastOverlay()
        page = Adw.PreferencesPage()
        self.toasts.set_child(page)
        tv.set_content(self.toasts)
        self.set_child(tv)

        # Kind of trip ---------------------------------------------------------------------
        g_kind = Adw.PreferencesGroup()
        kind = Gtk.Box(halign=Gtk.Align.CENTER)
        kind.add_css_class("linked")
        self.btn_round = Gtk.ToggleButton(label=_('Tam i z powrotem'))
        self.btn_oneway = Gtk.ToggleButton(label=_('Jeden lot'), group=self.btn_round)
        kind.append(self.btn_round)
        kind.append(self.btn_oneway)
        (self.btn_round if round_trip else self.btn_oneway).set_active(True)
        self.btn_round.connect("toggled", self._on_kind)
        # an existing flight keeps its kind (a pair stays a pair, a single flight stays single)
        kind.set_sensitive(not editing)
        g_kind.add(kind)
        page.add(g_kind)

        # Route --------------------------------------------------------------------
        g_route = Adw.PreferencesGroup(title=_('Trasa'),
                                       description=_('Wpisz kod IATA, miasto lub nazwę lotniska'))
        self.from_row = AirportRow(_('Skąd (wylatujesz)'), airports)
        self.to_row = AirportRow(_('Dokąd (cel podróży)'), airports)
        swap = Gtk.Button(icon_name="object-flip-vertical-symbolic", valign=Gtk.Align.CENTER,
                          tooltip_text=_('Zamień kierunek'))
        swap.add_css_class("flat")
        swap.connect("clicked", self._on_swap)
        self.to_row.add_suffix(swap)
        g_route.add(self.from_row)
        g_route.add(self.to_row)
        page.add(g_route)

        # Legs ---------------------------------------------------------------------------
        self.out = LegEditor(_('Wylot'), _('Data wylotu'), self.trip.dep_date)
        page.add(self.out.group)
        ret_date = (return_trip.dep_date if return_trip else
                    (date.fromisoformat(self.trip.dep_date) + timedelta(days=7)).isoformat())
        self.back = LegEditor(_('Powrót'), _('Data powrotu'), ret_date)
        page.add(self.back.group)

        # Summary ---------------------------------------------------------------------
        g_sum = Adw.PreferencesGroup(title=_('Podsumowanie'))
        self.sum_status = self._sum_row("Status", "skytrack-plane-symbolic")
        self.sum_km = self._sum_row(_('Odległość'), "mark-location-symbolic")
        self.sum_time = self._sum_row(_('Czas lotu'), "alarm-symbolic")
        self.sum_land = self._sum_row(_('Lądowanie u celu (czas lokalny)'), "skytrack-pin-symbolic")
        self.sum_home = self._sum_row(_('Lądowanie po powrocie (czas lokalny)'), "go-home-symbolic")
        self.sum_stay = self._sum_row(_('Na miejscu'), "x-office-calendar-symbolic")
        self.sum_tz = self._sum_row(_('Strefy czasowe'), "preferences-system-time-symbolic")
        for r in (self.sum_status, self.sum_km, self.sum_time, self.sum_land, self.sum_home,
                  self.sum_stay, self.sum_tz):
            g_sum.add(r)
        page.add(g_sum)

        # Details -----------------------------------------------------------------------
        g_det = Adw.PreferencesGroup(title=_('Szczegóły'), description=_('Wszystko opcjonalne'))
        self.airline = Adw.EntryRow(title=_('Linia lotnicza'))
        self.aircraft = Adw.EntryRow(title=_('Samolot (np. Boeing 737-8)'))
        self.notes = Adw.EntryRow(title=_('Notatka'))
        for r in (self.airline, self.aircraft, self.notes):
            g_det.add(r)
        page.add(g_det)

        # iCloud album (linux-icloud-photos) --------------------------------------------------------
        self._album = self.trip.album or ""
        self.album_picker = album_picker
        if album_picker is not None or self._album:
            g_alb = Adw.PreferencesGroup(title=_('Zdjęcia'))
            self.album_row = Adw.ActionRow(title=_('Album iCloud'))
            self.album_row.add_prefix(Gtk.Image.new_from_icon_name("folder-pictures-symbolic"))
            self.album_clear = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER,
                                          tooltip_text=_('Odłącz album'))
            self.album_clear.add_css_class("flat")
            self.album_clear.connect("clicked", lambda *_: self._set_album(""))
            self.album_row.add_suffix(self.album_clear)
            if album_picker is not None:
                pick = Gtk.Button(label=_('Wybierz…'), valign=Gtk.Align.CENTER)
                pick.connect("clicked", self._on_pick_album)
                self.album_row.add_suffix(pick)
            g_alb.add(self.album_row)
            page.add(g_alb)
            self._set_album(self._album)

        self.g_next = None
        if not editing:
            self.g_next = Adw.PreferencesGroup(
                description=_('Podróż z przesiadką albo kilka miast? „Zapisz i dodaj kolejny” zapisze ten lot i od razu otworzy następny: z lotniska docelowego, z tą samą datą.'))
            nxt = Gtk.Button(label=_('Zapisz i dodaj kolejny lot'), halign=Gtk.Align.CENTER)
            nxt.add_css_class("pill")
            nxt.connect("clicked", lambda *_: self._on_save(next_leg=True))
            self.g_next.add(nxt)
            page.add(self.g_next)

        if editing:
            g_del = Adw.PreferencesGroup()
            delete = Gtk.Button(label=_('Usuń podróż (oba loty)') if return_trip else _('Usuń lot'),
                                halign=Gtk.Align.CENTER)
            delete.add_css_class("destructive-action")
            delete.add_css_class("pill")
            delete.connect("clicked", self._on_delete)
            g_del.add(delete)
            page.add(g_del)

        # Fill ------------------------------------------------------------------------------
        t = self.trip
        self.from_row.set_airport(airports.get(t.origin) or (home_airport if not editing else None))
        self.to_row.set_airport(airports.get(t.dest))
        self.out.fill(t) if editing or t.dep_time or t.flight_no else None
        if return_trip:
            self.back.fill(return_trip)
        for w, v in ((self.airline, t.airline), (self.aircraft, t.aircraft), (self.notes, t.notes)):
            w.set_text(v)

        for w in (self.from_row, self.to_row):
            w.connect("airport-changed", self._update_summary)
        self.out.connect_changed(self._update_summary)
        self.back.connect_changed(self._update_summary)
        self._ret_touched = return_trip is not None
        self.back.date.connect("date-changed", self._on_ret_date)
        self.out.date.connect("date-changed", self._keep_return_after)
        self._apply_kind()
        target = self.to_row if self.from_row.airport and not self.to_row.airport else \
            (self.from_row if not self.from_row.airport else None)
        if target:
            self.set_focus(target)

    @staticmethod
    def _sum_row(title, icon):
        r = Adw.ActionRow(title=title, subtitle="—")
        r.add_prefix(Gtk.Image.new_from_icon_name(icon))
        r.add_css_class("property")
        return r

    # ---------------------------------------------------------------------------------------
    def _on_kind(self, *_a):
        self.round = self.btn_round.get_active()
        self._apply_kind()

    def _apply_kind(self):
        self.back.group.set_visible(self.round)
        if self.g_next is not None:
            self.g_next.set_visible(not self.round)
        self.sum_home.set_visible(self.round)
        self.sum_stay.set_visible(self.round)
        if self.round:
            self.out.group.set_title(_('Wylot'))
            self.sum_land.set_title(_('Lądowanie u celu (czas lokalny)'))
        else:
            self.out.group.set_title(_('Lot'))
            self.sum_land.set_title(_('Lądowanie (czas lokalny)'))
        self._update_summary()

    def _on_ret_date(self, *_a):
        self._ret_touched = True

    def _keep_return_after(self, *_a):
        """Until the return date is typed in, it follows the departure (+7 days)."""
        d, r = self.out.date.get_value(), self.back.date.get_value()
        if not d:
            return
        if not self._ret_touched:
            self.back.date.set_value((date.fromisoformat(d) + timedelta(days=7)).isoformat())
            self.back._sync_arr_date()
        elif r and r < d:
            self.back.date.set_value(d)

    def _set_album(self, name):
        self._album = name or ""
        self.album_row.set_subtitle(GLib.markup_escape_text(self._album) if self._album else
                                    _('brak — wybierz album albo utwórz go z dni podróży'))
        self.album_clear.set_visible(bool(self._album))

    def _on_pick_album(self, *_a):
        a, b, d = self.from_row.airport, self.to_row.airport, self.out.date.get_value()
        if not a or not b or not d:
            return self._toast(_('Najpierw wybierz trasę i datę'))
        tmp = Trip(origin=a.iata, dest=b.iata, dep_date=d,
                   dep_time=parse_time(self.out.dep_time.get_text()) or "", album=self._album,
                   id=self.trip.id)
        self.album_picker(tmp, self._set_album)

    def _on_swap(self, *_a):
        a, b = self.from_row.airport, self.to_row.airport
        self.from_row.set_airport(b)
        self.to_row.set_airport(a)

    def _update_summary(self, *_a):
        a, b = self.from_row.airport, self.to_row.airport
        self.out.mark_times()
        self.back.mark_times()
        self.out.group.set_description(f"{a.iata} → {b.iata}" if a and b else None)
        self.back.group.set_description(_('{0} → {1} (powrót do domu)').format(b.iata, a.iata) if a and b else None)
        d = self.out.date.get_value()
        rows = (self.sum_km, self.sum_time, self.sum_land, self.sum_home, self.sum_stay, self.sum_tz,
                self.sum_status)
        if not a or not b or not d:
            for r in rows:
                r.set_subtitle("—")
            return
        km = geo.distance_km(a.lat, a.lon, b.lat, b.lon)
        m1, e1 = self.out.minutes(a, b)
        if self.round:
            m2, e2 = self.back.minutes(b, a)
            self.sum_km.set_subtitle(_('{0} w każdą stronę · razem {1}').format(geo.fmt_km(km), geo.fmt_km(2 * round(km))))
            self.sum_time.set_subtitle(_('tam {0} · z powrotem {1}').format(geo.fmt_duration(m1, e1), geo.fmt_duration(m2, e2)))
            self.sum_home.set_subtitle(self.back.landing(b, a))
            r = self.back.date.get_value()
            if r:
                days = (date.fromisoformat(r) - date.fromisoformat(d)).days
                self.sum_stay.set_subtitle(
                    f"{nice_date(d)} – {nice_date(r)} · {days} {plural(days, 'dzień', 'dni', 'dni', 'day', 'days')}"
                    if days >= 0 else _('powrót przed wylotem?'))
        else:
            self.sum_km.set_subtitle(_('{0}  ·  {1} → {2} po ortodromie').format(geo.fmt_km(km), a.iata, b.iata))
            self.sum_time.set_subtitle(geo.fmt_duration(m1, e1) + (_(' (szacunek)') if e1 else ""))
        self.sum_land.set_subtitle(self.out.landing(a, b))
        dep_t = parse_time(self.out.dep_time.get_text()) or ""
        last_d = self.back.date.get_value() if self.round else d
        last_t = (parse_time(self.back.dep_time.get_text()) or "") if self.round else dep_t
        if geo.is_future(d, dep_t, a.tz):
            self.sum_status.set_subtitle(_('Zaplanowana · {0}').format(geo.countdown_label(d, dep_t, a.tz)))
        elif self.round and last_d and geo.is_future(last_d, last_t, b.tz):
            self.sum_status.set_subtitle(_('W trakcie · wylot odbyty, powrót zaplanowany'))
        else:
            self.sum_status.set_subtitle(_('Odbyta · wlicza się do statystyk'))
        diff = geo.tz_difference_label(a.tz, b.tz, d)
        self.sum_tz.set_subtitle(f"{a.iata} {geo.utc_offset_label(a.tz, d)}  ·  "
                                 f"{b.iata} {geo.utc_offset_label(b.tz, d)}  ·  {diff}")

    def _toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=3))

    def _on_save(self, next_leg=False):
        a, b = self.from_row.airport, self.to_row.airport
        if not a:
            self.from_row.add_css_class("error")
            return self._toast(_('Wybierz lotnisko wylotu z listy'))
        if not b:
            self.to_row.add_css_class("error")
            return self._toast(_('Wybierz lotnisko docelowe z listy'))
        if a.iata == b.iata:
            return self._toast(_('Lotnisko wylotu i docelowe są takie same'))
        v1, err = self.out.values(a, b, _("wylotu") if self.round else _("lotu"))
        if err:
            return self._toast(err)
        common = {"airline": self.airline.get_text().strip(),
                  "aircraft": self.aircraft.get_text().strip(),
                  "notes": self.notes.get_text().strip(), "album": self._album}
        t = self.trip
        t.origin, t.dest = a.iata, b.iata
        for k, v in list(v1.items()) + list(common.items()):
            setattr(t, k, v)
        trips = [t]
        if self.round:
            v2, err = self.back.values(b, a, _("powrotu"))
            if err:
                return self._toast(err)
            out_start = (v1["dep_date"], v1["dep_time"] or "00:00")
            back_start = (v2["dep_date"], v2["dep_time"] or "23:59")
            if back_start < out_start:
                return self._toast(_('Powrót nie może być przed wylotem'))
            if not t.trip_group:
                t.trip_group = uuid.uuid4().hex[:12]
            r = self.ret_trip or Trip(origin="", dest="", dep_date=v2["dep_date"])
            r.origin, r.dest = b.iata, a.iata
            for k, v in list(v2.items()) + list(common.items()):
                setattr(r, k, v)
            r.trip_group = t.trip_group
            trips.append(r)
        self.emit("saved", trips, next_leg)
        self.close()

    def _on_delete(self, *_a):
        t, r = self.trip, self.ret_trip
        what = (_('{0} ⇄ {1}, {2} – {3} (oba loty)').format(t.origin, t.dest, nice_date(t.dep_date), nice_date(r.dep_date))
                if r else f"{t.origin} → {t.dest}, {nice_date(t.dep_date)}")
        dlg = Adw.AlertDialog(heading=_('Usunąć podróż?') if r else _('Usunąć lot?'),
                              body=_('{0}. Tego nie da się cofnąć.').format(what))
        dlg.add_response("cancel", _('Anuluj'))
        dlg.add_response("delete", _('Usuń'))
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_close_response("cancel")

        def on_resp(_d, resp):
            if resp == "delete":
                self.emit("deleted", [x.id for x in (t, r) if x is not None and x.id is not None])
                self.close()
        dlg.connect("response", on_resp)
        dlg.present(self)
