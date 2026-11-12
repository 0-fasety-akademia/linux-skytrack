"""Main window: trips (list + boarding pass + map), plans and statistics."""
from collections import Counter
from datetime import date
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import badges, calexport, geo, importer, photos, stats
from .db import Trip
from . import backup, cloud
from .atc_ui import AtcControl
from .backup_ui import BackupDialog
from .lock import ChangePasswordDialog, LockPage
from .mapview import MapView
from .photos_ui import AlbumDialog, PhotoSection
from .plan_page import PlanPage
from .live_page import LivePage
from .stats_page import StatsPage
from .summary_page import SummaryPage
from .trip_dialog import TripDialog
from .widgets import CounterAnimator, PassCard, add_card_button
from .version import APP_NAME
from .i18n import IS_PL, _, plural


def esc(s):
    return GLib.markup_escape_text(str(s))


TEMPLATE_BASE = "skytrack-import" if IS_PL else "skytrack-import-en"


def plural_loty(n):
    return plural(n, "lot", "loty", "lotów", "flight", "flights")


class TripRow(Gtk.ListBoxRow):
    def __init__(self, info, on_edit, leg_label=""):
        super().__init__()
        self.info = info
        t = info.trip
        box = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=6, margin_end=4)
        icon = Gtk.Image.new_from_icon_name("skytrack-plane-symbolic")
        icon.add_css_class("trip-icon")
        if info.planned:
            icon.add_css_class("planned")
        icon.set_valign(Gtk.Align.CENTER)
        box.append(icon)

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        title = Gtk.Label(xalign=0, ellipsize=3)
        title.set_markup(f"{esc(t.origin)} → {esc(t.dest)}")
        title.add_css_class("code")
        sub = Gtk.Label(label=f"{info.origin.short} → {info.dest.short}", xalign=0, ellipsize=3)
        sub.add_css_class("caption")
        meta = ([leg_label] if leg_label else []) + [stats.nice_date(t.dep_date)]
        if t.dep_time:
            meta.append(t.dep_time)
        if t.flight_no:
            meta.append(t.flight_no)
        cap = Gtk.Label(label=" · ".join(meta), xalign=0, ellipsize=3)
        cap.add_css_class("caption")
        cap.add_css_class("dim-label")
        if t.album:
            line = Gtk.Box(spacing=4)
            ic = Gtk.Image.new_from_icon_name("folder-pictures-symbolic")
            ic.add_css_class("album-icon")
            ic.set_tooltip_text(_('Album iCloud: {0}').format(t.album))
            ic.set_pixel_size(12)
            line.append(cap)
            line.append(ic)
            cap = line
        for w in (title, sub, cap):
            texts.append(w)
        box.append(texts)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, spacing=2)
        km = Gtk.Label(label=geo.fmt_km(info.km), xalign=1)
        km.add_css_class("numeric")
        km.add_css_class("heading")
        right.append(km)
        if info.planned:
            badge = Gtk.Label(label=info.countdown, halign=Gtk.Align.END)
            badge.add_css_class("badge")
            badge.add_css_class("planned")
            right.append(badge)
        else:
            dur = Gtk.Label(label=geo.fmt_duration(info.minutes, info.approx), xalign=1)
            dur.add_css_class("caption")
            dur.add_css_class("dim-label")
            right.append(dur)
        box.append(right)

        edit = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER,
                          tooltip_text=_('Edytuj podróż'))
        edit.add_css_class("flat")
        edit.add_css_class("circular")
        edit.connect("clicked", lambda *_: on_edit(info.trip))
        box.append(edit)
        self.set_child(box)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME,
                         default_width=app.settings["width"], default_height=app.settings["height"])
        self.app = app
        self.set_size_request(360, 560)
        self.year = None
        self.infos = []
        self.all_infos = []
        self._years = None
        self._selected_id = None
        self._updating_years = False

        # Header ----------------------------------------------------------------------
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header = Adw.HeaderBar(title_widget=switcher)

        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text=_('Dodaj podróż (Ctrl+N)'))
        add.set_action_name("app.add-trip")
        header.pack_start(add)

        self.year_model = Gtk.StringList()
        self.year_dd = Gtk.DropDown(model=self.year_model, tooltip_text=_('Okres'))
        self.year_dd.connect("notify::selected", self._on_year)
        header.pack_start(self.year_dd)

        menu = Gio.Menu()
        looks = Gio.Menu()
        looks.append(_('Systemowy (jasny / ciemny)'), "app.theme::system")
        looks.append("Flighty", "app.theme::flighty")
        looks.append("Matrix", "app.theme::matrix")
        menu.append_submenu(_('Wygląd'), looks)
        data = Gio.Menu()
        data.append(_('Importuj podróże (arkusz / CSV)…'), "app.import")
        data.append(_('Zapisz szablon importu…'), "app.save-template")
        data.append(_('Eksportuj podróże do CSV…'), "app.export")
        data.append(_('Kopia zapasowa…'), "app.backup")
        data.append(_('Sprawdź nowe wieże (LIVE)…'), "win.check-towers")
        data.append(_('Otwórz folder z danymi'), "app.open-data")
        menu.append_section(None, data)
        acct = Gio.Menu()
        acct.append(_('Zablokuj'), "app.lock")
        acct.append(_('Zmień login i hasło…'), "app.change-password")
        menu.append_section(None, acct)
        sec2 = Gio.Menu()
        sec2.append(_('O aplikacji SkyTrack'), "app.about")
        sec2.append(_('Zakończ'), "app.quit")
        menu.append_section(None, sec2)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                       primary=True, tooltip_text="Menu"))
        self.atc = AtcControl(app.settings, app.airports)
        act = Gio.SimpleAction.new("check-towers", None)
        act.connect("activate", lambda *_a: self.atc.check_new())
        self.add_action(act)
        self.atc.connect("message", lambda _c, m: self.toasts.add_toast(Adw.Toast(title=m, timeout=5)))
        header.pack_end(self.atc)

        # Trips page --------------------------------------------------------------------
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL,
                               position=max(380, app.settings["sidebar"]),
                               shrink_start_child=False, resize_start_child=False)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.add_css_class("trip-sidebar")
        side.set_size_request(340, -1)

        summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0,
                          margin_top=14, margin_bottom=10, margin_start=16, margin_end=16)
        self.sum_period = Gtk.Label(xalign=0)
        self.sum_period.add_css_class("period")
        self.sum_km = Gtk.Label(xalign=0, label="0 km")
        self.sum_km.add_css_class("km-counter")
        self.counter = CounterAnimator(self.sum_km)
        self.sum_sub = Gtk.Label(xalign=0, wrap=True)
        self.sum_sub.add_css_class("dim-label")
        self.sum_sub.add_css_class("caption")
        for w in (self.sum_period, self.sum_km, self.sum_sub):
            summary.append(w)

        self.pass_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                   margin_start=12, margin_end=12, margin_bottom=10)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listbox.add_css_class("navigation-sidebar")
        self.listbox.set_header_func(self._row_header)
        self.listbox.connect("row-selected", self._on_row_selected)
        self.listbox.connect("row-activated", lambda _lb, row: self.map.focus(row.info.trip.id))
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_box.append(summary)
        list_box.append(self.pass_holder)
        list_box.append(self.listbox)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_child(list_box)

        self.empty = Adw.StatusPage(icon_name="skytrack-plane-symbolic", title=_('Brak podróży'),
                                    description=_('Dodaj lot: skąd, dokąd i kiedy, także sprzed lat. Masz historię z myFlightradar24 albo Flighty? Zaimportuj CSV.'))
        self.empty.add_css_class("compact")
        eb = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        btn = Gtk.Button(label=_('Dodaj podróż'))
        btn.add_css_class("pill")
        btn.add_css_class("suggested-action")
        btn.set_action_name("app.add-trip")
        imp = Gtk.Button(label=_('Importuj CSV'))
        imp.add_css_class("pill")
        imp.set_action_name("app.import")
        eb.append(btn)
        eb.append(imp)
        self.empty.set_child(eb)

        self.side_stack = Gtk.Stack(vexpand=True)
        self.side_stack.add_named(sc, "list")
        self.side_stack.add_named(self.empty, "empty")
        side.append(self.side_stack)

        self.map = MapView(app.web_dir, layer=app.settings["map_layer"],
                           dark=Adw.StyleManager.get_default().get_dark(), theme=app.settings["theme"])
        self.map.connect("trip-selected", self._on_map_select)
        self.map.connect("layer-changed", lambda _m, layer: app.settings.__setitem__("map_layer", layer))
        Adw.StyleManager.get_default().connect(
            "notify::dark", lambda sm, _p: self.map.set_theme(self.app.settings["theme"], sm.get_dark()))

        self.paned.set_start_child(side)
        self.paned.set_end_child(self.map)
        self.stack.add_titled_with_icon(self.paned, "trips", _('Podróże'), "skytrack-route-symbolic")

        # Plans page ------------------------------------------------------------------------
        self.plan_page = PlanPage(app.airports)
        self.plan_page.connect("plan-trip", lambda _p, t, back, album: self.plan_trip(t, back, album))
        self.plan_page.connect("edit", lambda _p, t: self.edit_trip(t))
        self.plan_page.connect("return-flight", lambda _p, t: self.return_flight(t))
        self.plan_page.connect("show-trip", lambda _p, tid: self.show_trip(tid))
        self.plan_page.connect("calendar", lambda _p, info: self.add_to_calendar(info))
        self.stack.add_titled_with_icon(self.plan_page, "plans", _('Plany'), "x-office-calendar-symbolic")

        # Stats page ------------------------------------------------------------------------
        self.stats_page = StatsPage(app.airports)
        self.stats_page.connect("home-changed", self._on_home_changed)
        self.stats_page.connect("show-trip", lambda _p, tid: self.show_trip(tid))
        self.stack.add_titled_with_icon(self.stats_page, "stats", _('Statystyki'),
                                        "skytrack-chart-symbolic")

        # Live tracking page ------------------------------------------------------------------
        self.live_page = LivePage(app)
        self.live_page.connect("show-trip", lambda _p, tid: self.show_trip(tid))
        self.stack.add_titled_with_icon(self.live_page, "live", _('Na żywo'), "find-location-symbolic")
        self.stack.connect("notify::visible-child-name", lambda *_a: self._sync_live_visible())

        # Summary ("wrapped") page ---------------------------------------------------------------
        self.summary_page = SummaryPage(app.airports, app.web_dir)
        self.summary_page.connect("year-chosen", self._on_summary_year)
        self.stack.add_titled_with_icon(self.summary_page, "summary", _('Podsumowanie'), "starred-symbolic")

        self.toasts = Adw.ToastOverlay()
        content = Gtk.Overlay(child=self.stack)
        content.add_overlay(self.atc.mini)   # LIVE mini window: same on every tab
        self.toasts.set_child(content)
        tv = Adw.ToolbarView(content=self.toasts)
        tv.add_top_bar(header)
        bottom = Adw.ViewSwitcherBar(stack=self.stack)
        tv.add_bottom_bar(bottom)
        self.lock_page = LockPage()
        self.lock_page.connect("unlocked", lambda *_: self.unlock())
        self.root = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.root.add_named(self.lock_page, "lock")
        self.root.add_named(tv, "main")
        self.set_content(self.root)
        self.locked = True
        self._after_unlock = []

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 760sp"))
        bp.add_setter(switcher, "visible", False)
        bp.add_setter(bottom, "reveal", True)
        bp.connect("apply", lambda *_a: self.summary_page.set_narrow(True))
        bp.connect("unapply", lambda *_a: self.summary_page.set_narrow(False))
        self.add_breakpoint(bp)

        self.connect("close-request", self._on_close)
        self.connect("realize", self._watch_minimize)
        self.apply_theme(app.settings["theme"])
        self.lock()

    # Login / lock ---------------------------------------------------------------------------
    def lock(self):
        """Hide everything behind the login screen and forget the data shown."""
        while True:
            d = self.get_visible_dialog()
            if d is None:
                break
            d.force_close()
        self.locked = True
        self.lock_page.reset()
        self.root.set_visible_child_name("lock")
        self.all_infos, self.infos = [], []
        self.listbox.remove_all()
        self.map.set_trips([])
        self.summary_page.refresh([], None, None)
        self.app.tracker.clear()
        self.atc.turn_off()
        self.live_page.set_trips([])
        self.live_page.set_visible_page(False)
        self.lock_page.focus_first()

    def unlock(self):
        self.locked = False
        self.root.set_visible_child_name("main")
        self.reload()
        GLib.timeout_add(400, lambda: (self.map.call("SkyMap.refit"), False)[1])
        pending, self._after_unlock = self._after_unlock, []
        for fn in pending:
            fn()
        GLib.timeout_add_seconds(3, self._auto_backup)
        self._sync_live_visible()

    def _auto_backup(self):
        if self.locked:
            return False
        try:
            backup.auto_backup_if_due(self.app.store, self.app.settings)
        except Exception as e:  # never block the app because of a backup
            print("auto backup failed:", e)
        try:
            cloud.auto_if_due(self.app.store, self.app.settings, self._on_cloud_auto)
        except Exception as e:
            print("cloud backup failed:", e)
        return False

    def _on_cloud_auto(self, results):
        bad = [k for k, r in (results or {}).items() if r is not None and not r.get("ok")]
        if bad or (results or {}).get("error"):
            names = {"gdrive": _('Dysk Google'), "icloud": "iCloud Drive"}
            self.toasts.add_toast(Adw.Toast(
                title=_('Kopia w chmurze nie powiodła się: {0}').format(", ".join(names.get(k, k) for k in bad) or "?"),
                button_label=_('Szczegóły'), action_name="app.backup", timeout=8))

    def show_backup(self):
        dlg = BackupDialog(self.app.store, self.app.settings)

        def restored(_d, with_auth):
            self.year_dd.set_selected(0)
            self.reload()
            if with_auth:
                self.lock()
            self.toasts.add_toast(Adw.Toast(title=_('Przywrócono kopię zapasową'), timeout=4))
        dlg.connect("restored", restored)
        dlg.present(self)

    def _sync_live_visible(self):
        self.live_page.set_visible_page(not self.locked and self.stack.get_visible_child_name() == "live")

    def when_unlocked(self, fn):
        if self.locked:
            self._after_unlock.append(fn)
        else:
            fn()

    def change_password(self):
        if self.locked:
            return
        dlg = ChangePasswordDialog()
        dlg.connect("closed", lambda d: d.saved and self.toasts.add_toast(
            Adw.Toast(title=_('Zapisano nowy login i hasło'), timeout=3)))
        dlg.present(self)

    # Theme -----------------------------------------------------------------------------------
    def apply_theme(self, name):
        self.counter.matrix = name == "matrix"
        self.map.set_theme(name, Adw.StyleManager.get_default().get_dark())
        self.summary_page.theme = name
        self.live_page.set_theme(name)
        if not self.locked:
            self.summary_page.set_theme(name)

    # Data ------------------------------------------------------------------------------------
    def reload(self, select_id=None):
        self.all_infos = stats.enrich(self.app.store.all(), self.app.airports)
        years = sorted({i.year for i in self.all_infos}, reverse=True)
        if years != self._years:
            self._years = years
            keep = self.year
            self._updating_years = True
            self.year_model.splice(0, self.year_model.get_n_items(),
                                   [_('Wszystkie lata')] + [str(y) for y in years])
            idx = years.index(keep) + 1 if keep in years else 0
            self.year = years[idx - 1] if idx else None
            self.year_dd.set_selected(idx)
            self._updating_years = False
        home = self._home_airport()
        self.plan_page.set_home(home)
        self.plan_page.refresh(self.all_infos)
        self._apply(select_id)

    def _on_summary_year(self, _page, year):
        idx = self._years.index(year) + 1 if year and self._years and year in self._years else 0
        self.year_dd.set_selected(idx)

    def _on_year(self, dd, _p):
        if self._updating_years:
            return
        i = dd.get_selected()
        self.year = self._years[i - 1] if self._years and 0 < i <= len(self._years) else None
        self._apply()

    def add_to_calendar(self, info):
        """Planned trip → calendar: the flight and, for a there-and-back trip, its return flight."""
        legs = [info]
        partner = self._partner(info)
        if partner is not None and partner.planned:
            legs.append(partner)
        legs.sort(key=lambda i: (i.trip.dep_date, i.trip.dep_time))
        try:
            how = calexport.export(legs, self)
        except OSError as e:
            self.toasts.add_toast(Adw.Toast(title=_('Nie udało się zapisać pliku kalendarza: {0}').format(e)))
            return
        n = len(legs)
        if how == "calendar":
            msg = _('Otwieram Linux iCloud Calendar: {0}').format(
                _('2 wydarzenia (wylot i powrót)') if n == 2 else _('1 wydarzenie'))
        else:
            msg = _('Otwieram plik kalendarza w domyślnej aplikacji')
        self.toasts.add_toast(Adw.Toast(title=msg, timeout=4))

    def _update_badges(self, all_flown, home):
        """Badges for the whole log; a toast when a new one was earned (not on the first load)."""
        items = badges.compute(all_flown, home)
        self.stats_page.set_badges(items)
        keys = {b.key for b in items if b.earned}
        prev = getattr(self, "_badge_keys", None)
        if prev is not None:
            new = [b for b in items if b.earned and b.key not in prev]
            if new:
                title = _('🏅 Nowa odznaka: {0}').format(new[0].name)
                if len(new) > 1:
                    title += _(' (+{0} kolejne)').format(len(new) - 1)
                t = Adw.Toast(title=title, timeout=6, button_label=_('Pokaż'))
                t.connect("button-clicked", lambda *_a: self._show_badges())
                self.toasts.add_toast(t)
        self._badge_keys = keys

    def _show_badges(self):
        self.stack.set_visible_child_name("stats")
        GLib.idle_add(self.stats_page.scroll_to_badges)

    def _apply(self, select_id=None):
        self.infos = stats.filter_year(self.all_infos, self.year)
        flown = stats.flown(self.infos)
        plans = stats.planned(self.infos)
        all_flown = stats.flown(self.all_infos)
        home = stats.home_country(all_flown, self.app.settings["home_country"])
        home_name = self.app.airports.country_name(home) if home else ""
        t = stats.totals(flown, home)
        self.sum_period.set_label(_('ODBYTE LOTY · {0}').format(self.year) if self.year else _('ODBYTE LOTY · WSZYSTKIE LATA'))
        self.counter.set(t["km"])
        n = t["flights"]
        nc = t["countries"]
        cw = plural(nc, "kraj", "kraje", "krajów", "country", "countries")
        sub = _('{0} {1} · {2} lotnisk · {3} {4} za granicą').format(n, plural_loty(n), t['airports'], nc, cw)
        if plans:
            sub += _('\n+ {0} zaplanowanych · {1}').format(len(plans), geo.fmt_km(sum((i.km for i in plans))))
        self.sum_sub.set_label(sub)

        self.listbox.remove_all()
        legs = self._leg_labels()
        for info in plans + sorted(flown, key=lambda i: (i.trip.dep_date, i.trip.dep_time), reverse=True):
            self.listbox.append(TripRow(info, self.edit_trip, legs.get(info.trip.id, "")))
        self.side_stack.set_visible_child_name("list" if self.infos else "empty")
        if self.all_infos and not self.infos:
            self.empty.set_title(_('Brak lotów w {0}').format(self.year))
            self.side_stack.set_visible_child_name("empty")
        else:
            self.empty.set_title(_('Brak podróży'))

        self.map.set_trips(self.infos, home)
        self.stats_page.refresh(flown, self.year, plans, home, home_name)
        self._update_badges(all_flown, home)
        self.summary_page.refresh(all_flown, self.year, home)
        self.live_page.set_trips(self.all_infos)
        sel = select_id if select_id is not None else self._selected_id
        if sel is not None and any(i.trip.id == sel for i in self.infos):
            GLib.idle_add(self._select_row, sel)
        else:
            self._selected_id = None
            GLib.idle_add(self._clear_selection)
        self._show_pass()

    def _on_home_changed(self, _page, cc):
        self.app.settings["home_country"] = cc
        self._apply()

    def _leg_labels(self):
        """{trip id: 'wylot' | 'powrót'} for flights saved as a there-and-back trip."""
        groups = {}
        for i in self.all_infos:
            if i.trip.trip_group:
                groups.setdefault(i.trip.trip_group, []).append(i)
        out = {}
        for legs in groups.values():
            if len(legs) == 2:
                legs.sort(key=lambda i: (i.trip.dep_date, i.trip.dep_time))
                out[legs[0].trip.id], out[legs[1].trip.id] = _('wylot'), _('powrót')
        return out

    def _partner(self, info):
        if not info.trip.trip_group:
            return None
        return next((i for i in self.all_infos if i.trip.trip_group == info.trip.trip_group
                     and i.trip.id != info.trip.id), None)

    def _pair_candidate(self, info):
        """A separate flight in the opposite direction right before/after this one (no flights in
        between, within 60 days) — e.g. GDN → KGS and KGS → GDN entered as two single flights."""
        from datetime import date as _date
        seq = sorted(self.all_infos, key=lambda i: (i.trip.dep_date, i.trip.dep_time))
        idx = next((k for k, i in enumerate(seq) if i.trip.id == info.trip.id), None)
        if idx is None:
            return None
        for k in (idx + 1, idx - 1):
            if 0 <= k < len(seq):
                m = seq[k]
                if (not m.trip.trip_group and m.trip.origin == info.trip.dest
                        and m.trip.dest == info.trip.origin
                        and abs((_date.fromisoformat(m.trip.dep_date) -
                                 _date.fromisoformat(info.trip.dep_date)).days) <= 60):
                    return m
        return None

    def _link_pair(self, a, b):
        import uuid
        group = uuid.uuid4().hex[:12]
        for t in (a, b):
            t.trip_group = group
            self.app.store.save(t)
        self.reload(select_id=a.id)
        self.toasts.add_toast(Adw.Toast(title=_('Połączono: {0} ⇄ {1} jako jedna podróż').format(a.origin, a.dest),
                                        timeout=3))

    def _show_pass(self):
        """Boarding pass: selected trip, else the next planned one, else the latest flight."""
        child = self.pass_holder.get_first_child()
        if child:
            self.pass_holder.remove(child)
        info = next((i for i in self.infos if i.trip.id == self._selected_id), None)
        caption = None
        if info is None:
            plans = stats.planned(self.infos)
            if plans:
                info, caption = plans[0], _('Następny lot')
            else:
                flown = stats.flown(self.infos)
                if flown:
                    info = max(flown, key=lambda i: (i.trip.dep_date, i.trip.dep_time))
                    caption = _('Ostatni lot')
        if info is None:
            return
        partner = self._partner(info)
        if partner is not None:
            is_out = (info.trip.dep_date, info.trip.dep_time) <= (partner.trip.dep_date, partner.trip.dep_time)
            leg = (_('Wylot · powrót {0}').format(stats.nice_date(partner.trip.dep_date)) if is_out
                   else _('Powrót · wylot {0}').format(stats.nice_date(partner.trip.dep_date)))
            caption = f"{caption} · {leg}" if caption else leg
        card = PassCard(info, caption=caption)
        card.connect("edit", lambda _c, tr: self.edit_trip(tr))
        card.connect("return-flight", lambda _c, tr: self.return_flight(tr))
        card.connect("calendar", lambda _c, i: self.add_to_calendar(i))
        if partner is not None:
            card.ret_btn.set_visible(False)       # the return flight already exists
        else:
            mate = self._pair_candidate(info)
            if mate is not None:
                card.ret_btn.set_visible(False)
                later = (mate.trip.dep_date, mate.trip.dep_time) > (info.trip.dep_date, info.trip.dep_time)
                add_card_button(card, _('Połącz w podróż'),
                                _('To {0} {1} → {2} z {3} — zapisz oba loty jako jedną podróż tam i z powrotem').format(_('powrót') if later else _('wylot'), mate.trip.origin, mate.trip.dest, stats.nice_date(mate.trip.dep_date)),
                                lambda: self._link_pair(info.trip, mate.trip))
        if photos.available():
            section = PhotoSection(info, self.all_infos)
            section.connect("manage-album", lambda _s, i: self.manage_album(i))
            card.append(section)
        self.pass_holder.append(card)

    def _clear_selection(self):
        self.listbox.unselect_all()
        self.set_focus(None)
        return False

    def _select_row(self, trip_id):
        row = self.listbox.get_first_child()
        while row:
            if isinstance(row, TripRow) and row.info.trip.id == trip_id:
                self.listbox.select_row(row)
                row.grab_focus()
                break
            row = row.get_next_sibling()
        return False

    def _row_header(self, row, before):
        if row.info.planned:
            key, text = "planned", _('NADCHODZĄCE')
        else:
            key = row.info.trip.dep_date[:7]
            y, m = int(key[:4]), int(key[5:7])
            text = f"{stats.MONTHS[m - 1].upper()} {y}"
        if before is not None:
            bkey = "planned" if before.info.planned else before.info.trip.dep_date[:7]
            if bkey == key:
                row.set_header(None)
                return
        lab = Gtk.Label(label=text, xalign=0, margin_top=14 if before else 4,
                        margin_bottom=4, margin_start=12)
        lab.add_css_class("section-title")
        row.set_header(lab)

    def _on_row_selected(self, _lb, row):
        if row is None:
            if self._selected_id is not None:
                self._selected_id = None
                self.map.clear_focus()
                self._show_pass()
            return
        if self._selected_id != row.info.trip.id:
            self._selected_id = row.info.trip.id
            self._show_pass()
        self.map.focus(row.info.trip.id)

    def _on_map_select(self, _map, trip_id):
        self._select_row(trip_id)

    def show_trip(self, trip_id):
        info = next((i for i in self.all_infos if i.trip.id == trip_id), None)
        if info and self.year is not None and info.year != self.year:
            self.year_dd.set_selected(0)
        self.stack.set_visible_child_name("trips")
        self._select_row(trip_id)
        self.map.focus(trip_id)

    # Dialogs ------------------------------------------------------------------------------------
    def _home_airport(self):
        c = Counter(i.trip.origin for i in self.all_infos)
        return self.app.airports.get(c.most_common(1)[0][0]) if c else None

    # iCloud album ----------------------------------------------------------------------------
    def manage_album(self, info, on_chosen=None):
        if not photos.available():
            self.toasts.add_toast(Adw.Toast(title=_('Zainstaluj Linux iCloud Photos 0.15.0+, żeby łączyć albumy')))
            return
        if not photos.bridge_supported():
            self.toasts.add_toast(Adw.Toast(title=_('Zaktualizuj Linux iCloud Photos do 0.15.0 lub nowszej')))
            return
        dlg = AlbumDialog(info, self.all_infos)
        dlg.connect("chosen", lambda _d, name: (on_chosen or self._set_album)(info.trip, name))
        dlg.present(self)

    def _create_trip_album(self, name, trips):
        """Create the album chosen while planning (empty for now) and keep it linked to the trip."""
        if not photos.empty_albums_supported():
            self.toasts.add_toast(Adw.Toast(title=_('Album nie powstał: zaktualizuj Linux iCloud Photos do 0.15.1'),
                                            timeout=5))
            self._unlink_album(trips)
            return
        self.toasts.add_toast(Adw.Toast(title=_('Tworzę album „{0}” w iCloud…').format(name), timeout=2))

        def done(result):
            if result.get("ok"):
                verb = _('Utworzono') if result.get("created") else _('Połączono istniejący')
                self.toasts.add_toast(Adw.Toast(title=_('{0} album „{1}” w iCloud').format(verb, name), timeout=4))
                photos.forget_thumbs()
            else:
                self.toasts.add_toast(Adw.Toast(
                    title=_('Album nie powstał: {0}').format(photos.error_text(result)), timeout=6))
                self._unlink_album(trips)
            return False
        photos.create_album(name, None, None, done, allow_empty=True)

    def _unlink_album(self, trips):
        for t in trips:
            t.album = ""
            if t.id is not None:
                self.app.store.save(t)
        if not self.locked:
            self.reload(select_id=trips[0].id)

    def _set_album(self, trip, name):
        trip.album = name
        if trip.id is not None:
            self.app.store.save(trip)
            self.reload(select_id=trip.id)
        self.toasts.add_toast(Adw.Toast(
            title=_('Połączono album „{0}”').format(name) if name else _('Odłączono album'), timeout=3))

    def _pick_album_for_dialog(self, trip, callback):
        info = next(iter(stats.enrich([trip], self.app.airports)), None)
        if info is None:
            return
        self.manage_album(info, on_chosen=lambda _t, name: callback(name))

    def _open_dialog(self, trip=None, title=None, return_trip=None, round_trip=None):
        dlg = TripDialog(self.app.airports, trip=trip, return_trip=return_trip,
                         home_airport=self._home_airport(), title=title, round_trip=round_trip,
                         album_picker=self._pick_album_for_dialog if photos.available() else None)
        dlg.connect("saved", self._on_saved)
        dlg.connect("closed", lambda *_: GLib.idle_add(self._clear_pending_album))
        if trip is not None and trip.id is not None:
            dlg.connect("deleted", self._on_deleted)
        dlg.present(self)

    def _clear_pending_album(self):
        self._pending_album = None       # dialog closed without saving
        return False

    def add_trip(self):
        self._open_dialog()

    def edit_trip(self, trip):
        """A flight that belongs to a there-and-back trip opens with its pair."""
        pair = []
        if trip.trip_group:
            pair = sorted((t for t in self.app.store.all() if t.trip_group == trip.trip_group),
                          key=lambda t: (t.dep_date, t.dep_time))
        if len(pair) == 2:
            self._open_dialog(pair[0], return_trip=pair[1], title=_('Edytuj podróż'))
        else:
            self._open_dialog(trip, title=_('Edytuj lot'))

    def return_flight(self, trip):
        self._open_dialog(Trip(origin=trip.dest, dest=trip.origin,
                               dep_date=trip.arr_date or trip.dep_date, airline=trip.airline),
                          _('Lot powrotny'))

    def plan_trip(self, template, back=None, album=""):
        """Planned trip from the calculator; optionally an (empty) iCloud album is created on save."""
        if album:
            template.album = album
            if back is not None:
                back.album = album
        self._pending_album = album or None
        self._open_dialog(template, _('Planowana podróż'), return_trip=back, round_trip=back is not None)

    def _on_saved(self, _dlg, trips, next_leg):
        is_new = trips[0].id is None
        for t in trips:
            self.app.store.save(t)
        pending, self._pending_album = getattr(self, "_pending_album", None), None
        if pending and trips[0].album == pending:
            self._create_trip_album(pending, trips)
        first = trips[0]
        a, b = self.app.airports.get(first.origin), self.app.airports.get(first.dest)
        km = geo.distance_km(a.lat, a.lon, b.lat, b.lon) * len(trips)
        if self.year is not None and int(first.dep_date[:4]) != self.year:
            self.year_dd.set_selected(0)
        self._selected_id = first.id
        self.reload(select_id=first.id)
        planned = geo.is_future(first.dep_date, first.dep_time, a.tz)
        verb = (_('Zaplanowano') if planned else _('Dodano')) if is_new else _('Zapisano')
        route = f"{first.origin} ⇄ {first.dest}" if len(trips) == 2 else f"{first.origin} → {first.dest}"
        self.toasts.add_toast(Adw.Toast(title=f"{verb}: {route} · {geo.fmt_km(km)}", timeout=3))
        if is_new and not next_leg:
            total = sum(i.km for i in stats.flown(self.all_infos))
            self.app.notify("trip-added", _('Zaplanowano podróż') if planned else _('Dodano podróż'),
                            _('{0} ⇄ {1} · {2}\nOdbyte loty łącznie: {3}').format(a.short, b.short, geo.fmt_km(km), geo.fmt_km(total))
                            if len(trips) == 2 else
                            _('{0} → {1} · {2}\nOdbyte loty łącznie: {3}').format(a.short, b.short, geo.fmt_km(km), geo.fmt_km(total)))
        if next_leg:
            last = trips[-1]
            GLib.timeout_add(250, lambda: (self._open_dialog(
                Trip(origin=last.dest, dest="", dep_date=last.arr_date or last.dep_date,
                     airline=last.airline), _('Kolejny lot')), False)[1])

    def _on_deleted(self, _dlg, trip_ids):
        for tid in trip_ids:
            self.app.store.delete(tid)
            if self._selected_id == tid:
                self._selected_id = None
        self.reload()
        self.toasts.add_toast(Adw.Toast(
            title=_('Usunięto podróż (oba loty)') if len(trip_ids) == 2 else _('Usunięto lot'), timeout=3))

    # Import / export -----------------------------------------------------------------------------
    def import_csv(self):
        dlg = Gtk.FileDialog(title=_('Importuj podróże'))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        f = Gtk.FileFilter()
        f.set_name(_('Arkusz lub CSV (szablon SkyTrack, myFlightradar24, Flighty)'))
        for pat in ("*.ods", "*.ODS", "*.xlsx", "*.XLSX", "*.csv", "*.CSV"):
            f.add_pattern(pat)
        filters.append(f)
        dlg.set_filters(filters)
        dlg.open(self, None, self._on_import_file)

    def save_template(self):
        dlg = Gtk.FileDialog(title=_('Zapisz szablon importu'), initial_name=TEMPLATE_BASE + ".ods")
        dlg.save(self, None, self._on_save_template)

    def _on_save_template(self, dlg, res):
        try:
            gfile = dlg.save_finish(res)
        except GLib.Error:
            return
        name = gfile.get_basename() or ""
        ext = ".csv" if name.lower().endswith(".csv") else ".ods"
        src = os.path.join(self.app.template_dir, TEMPLATE_BASE + ext)
        try:
            with open(src, "rb") as fh:
                data = fh.read()
            gfile.replace_contents(data, None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
        except (OSError, GLib.Error) as e:
            self.toasts.add_toast(Adw.Toast(title=_('Błąd zapisu szablonu: {0}').format(e), timeout=5))
            return
        toast = Adw.Toast(title=_('Zapisano szablon {0}').format(name), button_label=_('Otwórz'), timeout=6)
        toast.connect("button-clicked",
                      lambda *_: Gtk.FileLauncher.new(gfile).launch(self, None, None))
        self.toasts.add_toast(toast)

    def _on_import_file(self, dlg, res):
        try:
            gfile = dlg.open_finish(res)
        except GLib.Error:
            return
        ok, data, _etag = gfile.load_contents(None)
        try:
            trips, problems = importer.parse_file(gfile.get_basename() or "", bytes(data), self.app.airports)
        except Exception as e:  # damaged / unexpected spreadsheet
            trips, problems = [], [_('nie udało się odczytać pliku ({0})').format(e)]
        existing = self.app.store.all()
        new = [t for t in trips if not importer.is_duplicate(t, existing)]
        dups = len(trips) - len(new)
        body = [_('Znaleziono {0} {1} w pliku {2}.').format(len(trips), plural_loty(len(trips)), gfile.get_basename())]
        if dups:
            body.append(_('{0} już jest w SkyTrack — zostaną pominięte.').format(dups))
        if problems:
            body.append(_('Pominięte wiersze ({0}):\n').format(len(problems)) + "\n".join(problems[:6]) +
                        ("\n…" if len(problems) > 6 else ""))
        if new:
            km = sum(geo.distance_km(self.app.airports.get(t.origin).lat, self.app.airports.get(t.origin).lon,
                                     self.app.airports.get(t.dest).lat, self.app.airports.get(t.dest).lon)
                     for t in new)
            first = min(t.dep_date for t in new)[:4]
            last = max(t.dep_date for t in new)[:4]
            span = _('rok {0}').format(first) if first == last else _('lata {0}–{1}').format(first, last)
            body.append(_('Do dodania: {0} {1}, {2}, {3}.').format(len(new), plural_loty(len(new)), geo.fmt_km(km), span))
        alert = Adw.AlertDialog(heading=_('Import podróży') if new else _('Nic do zaimportowania'),
                                body="\n\n".join(body))
        alert.add_response("cancel", _('Anuluj') if new else "OK")
        if new:
            alert.add_response("import", _('Importuj {0}').format(len(new)))
            alert.set_response_appearance("import", Adw.ResponseAppearance.SUGGESTED)
            alert.set_default_response("import")
        alert.set_close_response("cancel")

        def on_resp(_d, r):
            if r == "import":
                for t in new:
                    self.app.store.save(t)
                self.year_dd.set_selected(0)
                self.reload()
                self.toasts.add_toast(Adw.Toast(
                    title=_('Zaimportowano {0} {1}').format(len(new), plural_loty(len(new))), timeout=4))
        alert.connect("response", on_resp)
        alert.present(self)

    def export_csv(self):
        dlg = Gtk.FileDialog(title=_('Eksportuj podróże do CSV'),
                             initial_name=f"{'skytrack-podroze' if IS_PL else 'skytrack-trips'}-{date.today().isoformat()}.csv")
        dlg.save(self, None, self._on_export_file)

    def _on_export_file(self, dlg, res):
        try:
            gfile = dlg.save_finish(res)
        except GLib.Error:
            return
        data = importer.export_csv(self.app.store.all()).encode("utf-8")
        try:
            gfile.replace_contents(data, None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
            self.toasts.add_toast(Adw.Toast(title=_('Zapisano {0}').format(gfile.get_basename()), timeout=3))
        except GLib.Error as e:
            self.toasts.add_toast(Adw.Toast(title=_('Błąd zapisu: {0}').format(e.message), timeout=5))

    # Window -----------------------------------------------------------------------------------
    def save_state(self):
        s = self.app.settings
        if not self.is_maximized():
            w, h = self.get_default_size()
            s["width"], s["height"] = w, h
        s["sidebar"] = self.paned.get_position()

    # Tower radio: keep playing on every tab, stop when the window is minimised ---------------
    def _watch_minimize(self, *_a):
        self._suspend_timer = 0
        surface = self.get_surface()
        if surface is not None:
            surface.connect("notify::state", self._on_surface_state)

    def _on_surface_state(self, surface, *_a):
        state = surface.get_state()
        if state & Gdk.ToplevelState.MINIMIZED:
            self.atc.turn_off()
            return
        # Wayland never reports "minimised"; GNOME marks a minimised window as suspended.
        susp = getattr(Gdk.ToplevelState, "SUSPENDED", None)
        if susp is not None and state & susp:
            if not self._suspend_timer:
                self._suspend_timer = GLib.timeout_add(1500, self._suspended_check)
        elif self._suspend_timer:
            GLib.source_remove(self._suspend_timer)
            self._suspend_timer = 0

    def _suspended_check(self):
        self._suspend_timer = 0
        surface = self.get_surface()
        susp = getattr(Gdk.ToplevelState, "SUSPENDED", None)
        if surface is not None and susp is not None and surface.get_state() & susp:
            self.atc.turn_off()
        return False

    def _on_close(self, *_a):
        self.atc.turn_off()
        self.save_state()
        return False
