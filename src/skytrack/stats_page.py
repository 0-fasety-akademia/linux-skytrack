"""Statistics page: totals, km chart, year → month → day breakdown."""
import math

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, GObject, Gtk

from . import geo, stats
from .airports import flag
from .i18n import IS_PL, _, plural


def esc(s):
    return GLib.markup_escape_text(str(s))


def _dec(s):
    return s.replace(".", ",") if IS_PL else s


class StatCard(Gtk.Box):
    def __init__(self, icon, caption):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("card")
        self.add_css_class("stat-card")
        top = Gtk.Box(spacing=8)
        img = Gtk.Image.new_from_icon_name(icon)
        img.add_css_class("accent")
        cap = Gtk.Label(label=caption, xalign=0)
        cap.add_css_class("caption-heading")
        cap.add_css_class("dim-label")
        top.append(img)
        top.append(cap)
        self.value = Gtk.Label(xalign=0, ellipsize=3)
        self.value.add_css_class("title-2")
        self.note = Gtk.Label(xalign=0, ellipsize=3)
        self.note.add_css_class("caption")
        self.note.add_css_class("dim-label")
        self.append(top)
        self.append(self.value)
        self.append(self.note)

    def make_clickable(self, callback, tooltip):
        self.add_css_class("clickable-card")
        self.set_cursor_from_name("pointer")
        self.set_tooltip_text(tooltip)
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: callback())
        self.add_controller(click)

    def set(self, value, note=""):
        self.value.set_label(value)
        self.note.set_label(note)
        self.note.set_visible(bool(note))


class BarChart(Gtk.DrawingArea):
    def __init__(self):
        super().__init__(content_height=220, hexpand=True)
        self.labels, self.values = [], []
        self.set_draw_func(self._draw)

    def set_data(self, labels, values):
        self.labels, self.values = labels, values
        self.queue_draw()

    def _draw(self, area, cr, w, h):
        if not self.values:
            return
        fg = area.get_color()
        import warnings
        from gi.repository import Gdk
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ok, accent = area.get_style_context().lookup_color("accent_bg_color")
        if not ok:
            accent = Gdk.RGBA()
            accent.parse("#3584e4")
        n = len(self.values)
        top_pad, bottom_pad, side = 22, 24, 8
        ch = h - top_pad - bottom_pad
        vmax = max(self.values) or 1
        slot = (w - 2 * side) / n
        bw = max(4, min(48, slot * 0.62))
        cr.select_font_face("Sans")
        for i, (lab, v) in enumerate(zip(self.labels, self.values)):
            x = side + i * slot + (slot - bw) / 2
            bh = ch * (v / vmax) if v else 0
            y = top_pad + ch - bh
            # bar
            r = min(6, bw / 2, bh / 2) if bh else 0
            cr.set_source_rgba(accent.red, accent.green, accent.blue, 0.9 if v else 0.15)
            if bh < 2:
                cr.rectangle(x, top_pad + ch - 2, bw, 2)
            else:
                cr.new_sub_path()
                cr.arc(x + bw - r, y + r, r, -math.pi / 2, 0)
                cr.line_to(x + bw, y + bh)
                cr.line_to(x, y + bh)
                cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
                cr.close_path()
            cr.fill()
            # value
            if v:
                txt = (f"{v / 1000:.1f}".replace(".", ",") + " tys." if IS_PL else f"{v / 1000:.1f}k") if v >= 10000 else f"{round(v)}"
                cr.set_font_size(10)
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.75)
                ext = cr.text_extents(txt)
                cr.move_to(x + bw / 2 - ext.width / 2 - ext.x_bearing, y - 6)
                cr.show_text(txt)
            # label
            cr.set_font_size(11)
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            ext = cr.text_extents(lab)
            cr.move_to(x + bw / 2 - ext.width / 2 - ext.x_bearing, h - 6)
            cr.show_text(lab)


class StatsPage(Gtk.ScrolledWindow):
    __gsignals__ = {"show-trip": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
                    "home-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self, airports):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.airports = airports
        clamp = Adw.Clamp(maximum_size=980, tightening_threshold=700)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                      margin_top=24, margin_bottom=32, margin_start=16, margin_end=16)
        clamp.set_child(box)
        self.set_child(clamp)

        self.title = Gtk.Label(xalign=0)
        self.title.add_css_class("title-1")
        box.append(self.title)

        self.cards = {
            "km": StatCard("mark-location-symbolic", _('PRZEBYTY DYSTANS')),
            "flights": StatCard("skytrack-plane-symbolic", _('LOTY')),
            "time": StatCard("alarm-symbolic", _('CZAS W POWIETRZU')),
            "airports": StatCard("skytrack-pin-symbolic", _('LOTNISKA')),
            "countries": StatCard("preferences-desktop-locale-symbolic", _('KRAJE')),
            "longest": StatCard("skytrack-route-symbolic", _('NAJDŁUŻSZY LOT')),
            "laps": StatCard("skytrack-plane-symbolic", _('DOOKOŁA ZIEMI')),
            "moon": StatCard("weather-clear-night-symbolic", _('DO KSIĘŻYCA')),
            "planned": StatCard("x-office-calendar-symbolic", _('ZAPLANOWANE')),
        }
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           min_children_per_line=2, max_children_per_line=3,
                           column_spacing=12, row_spacing=12)
        for c in self.cards.values():
            flow.append(c)
        box.append(flow)
        self.cards["countries"].make_clickable(self.scroll_to_countries, _('Pokaż odwiedzone kraje'))
        self.cards["longest"].make_clickable(
            lambda: self._longest_id is not None and self.emit("show-trip", self._longest_id),
            _('Pokaż ten lot na mapie'))
        self._longest_id = None

        self.chart_group = Adw.PreferencesGroup()
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.add_css_class("card")
        self.chart = BarChart()
        self.chart.set_margin_top(12)
        self.chart.set_margin_bottom(8)
        self.chart.set_margin_start(12)
        self.chart.set_margin_end(12)
        frame.append(self.chart)
        self.chart_group.add(frame)
        box.append(self.chart_group)

        self.countries_group = Adw.PreferencesGroup(title=_('Odwiedzone kraje'))
        # home country picker (not counted as visited)
        names = sorted(airports.countries_pl.items(), key=lambda kv: kv[1])
        self._home_codes = [cc for cc, _n in names]
        self.home_dd = Gtk.DropDown(model=Gtk.StringList.new([f"{flag(cc)}  {n}" for cc, n in names]),
                                    valign=Gtk.Align.CENTER, enable_search=True,
                                    tooltip_text=_('Kraj zamieszkania — nie liczy się do odwiedzonych'))
        expr = Gtk.PropertyExpression.new(Gtk.StringObject, None, "string")
        self.home_dd.set_expression(expr)
        self.home_dd.connect("notify::selected", self._on_home_selected)
        self._setting_home = False
        hbox = Gtk.Box(spacing=8)
        lab = Gtk.Label(label=_('Mieszkam w:'))
        lab.add_css_class("dim-label")
        hbox.append(lab)
        hbox.append(self.home_dd)
        self.countries_group.set_header_suffix(hbox)
        box.append(self.countries_group)
        self._country_rows = []

        self.tree_group = Adw.PreferencesGroup(title=_('Rok / miesiąc / dzień'))
        box.append(self.tree_group)
        self._tree_rows = []

    def _on_home_selected(self, dd, _p):
        if self._setting_home:
            return
        i = dd.get_selected()
        if 0 <= i < len(self._home_codes):
            self.emit("home-changed", self._home_codes[i])

    def scroll_to_countries(self):
        from gi.repository import Graphene
        ok, pt = self.countries_group.compute_point(self.get_child(), Graphene.Point())
        if ok:
            adj = self.get_vadjustment()
            adj.set_value(min(max(0, pt.y - 12), adj.get_upper() - adj.get_page_size()))
        first = self._country_rows[0] if self._country_rows else None
        if isinstance(first, Adw.ExpanderRow):
            first.grab_focus()

    def refresh(self, infos, year, plans=(), home=None, home_name=""):
        self.title.set_label(_('Statystyki {0}').format(year) if year else _('Statystyki — wszystkie lata'))
        t = stats.totals(infos, home)
        self.cards["km"].set(geo.fmt_km(t["km"]),
                             _('średnio {0} na lot').format(geo.fmt_km(t['km'] / t['flights'])) if t["flights"] else "")
        self.cards["laps"].set(_dec(f"{t['laps']:.2f}×"), _('równik: 40 075 km'))
        moon = t["km"] / 384400 * 100
        self.cards["moon"].set(_dec(f"{moon:.1f} %"), _('średnio 384 400 km'))
        pk = sum(i.km for i in plans)
        n = len(plans)
        word = plural(n, "lot", "loty", "lotów", "flight", "flights")
        self.cards["planned"].set(f"{n} {word}" if plans else "—",
                                  geo.fmt_km(pk) + _(' przed Tobą') if plans else _('brak planów'))
        self.cards["flights"].set(str(t["flights"]),
                                  _('{0} różnych tras').format(len({(i.trip.origin, i.trip.dest) for i in infos}))
                                  if t["flights"] else "")
        self.cards["time"].set(geo.fmt_duration(t["minutes"], approx=t["approx"]) if t["flights"] else "—",
                               _('część szacowana z dystansu') if t["approx"] and t["flights"] else "")
        self.cards["airports"].set(str(t["airports"]), _('{0} jako cel podróży').format(t['destinations']) if t["destinations"] else "")
        self.cards["countries"].set(str(t["countries"]),
                                    (_('bez kraju zamieszkania ({0}) · kliknij').format(home_name)
                                     if home_name else _('kliknij, żeby zobaczyć listę')))
        lg = t["longest"]
        self._longest_id = lg.trip.id if lg else None
        self.cards["longest"].set(geo.fmt_km(lg.km) if lg else "—",
                                  f"{lg.route} · {stats.nice_date(lg.trip.dep_date)}" if lg else "")

        labels, values = stats.chart_series(infos, year)
        self.chart_group.set_title(_('Kilometry w miesiącach {0}').format(year) if year else _('Kilometry w latach'))
        self.chart.set_data(labels, values)
        self.chart_group.set_visible(bool(infos))

        self._fill_countries(infos, home, home_name)

        for r in self._tree_rows:
            self.tree_group.remove(r)
        self._tree_rows = []
        tr = stats.tree(infos)
        if not tr:
            empty = Adw.ActionRow(title=_('Brak lotów w tym okresie'))
            self.tree_group.add(empty)
            self._tree_rows.append(empty)
            return
        first = True
        for y, months in tr.items():
            y_infos = [i for m in months.values() for d in m.values() for i in d]
            yrow = Adw.ExpanderRow(title=f"<b>{y}</b>", subtitle=self._sub(y_infos),
                                   expanded=first)
            yrow.add_suffix(self._km_label(y_infos, "heading"))
            first = False
            for m, days in months.items():
                m_infos = [i for d in days.values() for i in d]
                mrow = Adw.ExpanderRow(title=stats.MONTHS[m - 1].capitalize(),
                                       subtitle=self._sub(m_infos))
                mrow.add_suffix(self._km_label(m_infos))
                for d, d_infos in days.items():
                    routes = ",  ".join(
                        f"{i.route}" + (f" ({esc(i.trip.flight_no)})" if i.trip.flight_no else "")
                        for i in d_infos)
                    drow = Adw.ActionRow(title=esc(stats.nice_date(d, with_weekday=True)),
                                         subtitle=esc(routes), activatable=True)
                    drow.add_suffix(self._km_label(d_infos))
                    drow.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
                    drow.connect("activated", lambda _r, tid=d_infos[0].trip.id:
                                 self.emit("show-trip", tid))
                    mrow.add_row(drow)
                yrow.add_row(mrow)
            self.tree_group.add(yrow)
            self._tree_rows.append(yrow)

    def _fill_countries(self, infos, home, home_name):
        if home in self._home_codes:
            self._setting_home = True
            self.home_dd.set_selected(self._home_codes.index(home))
            self._setting_home = False
        for r in self._country_rows:
            self.countries_group.remove(r)
        self._country_rows = []
        visited = stats.visited_countries(infos, home)
        n = len(visited)
        self.countries_group.set_title(_('Odwiedzone kraje ({0})').format(n))
        self.countries_group.set_description(
            (_('Kraje docelowe Twoich lotów') + (_(', bez kraju zamieszkania ({0})').format(home_name) if home_name else "")
             + _('. Rozwiń kraj, żeby zobaczyć loty; kliknięcie lotu pokaże go na mapie.')) if n else None)
        if not visited:
            empty = Adw.ActionRow(title=_('Brak lotów za granicę w tym okresie'))
            self.countries_group.add(empty)
            self._country_rows.append(empty)
            return
        for c in visited:
            v = len(c["visits"])
            vw = plural(v, "wizyta", "wizyty", "wizyt", "visit", "visits")
            when = (stats.nice_date(c["first"]) if c["first"] == c["last"]
                    else f"{stats.nice_date(c['first'])} – {stats.nice_date(c['last'])}")
            row = Adw.ExpanderRow(title=esc(f"{flag(c['cc'])}  {c['name']}"),
                                  subtitle=esc(f"{', '.join(c['airports'])} · {when}"))
            count = Gtk.Label(label=f"{v} {vw}", valign=Gtk.Align.CENTER)
            count.add_css_class("numeric")
            count.add_css_class("dim-label")
            row.add_suffix(count)
            for i in reversed(c["visits"]):
                t = i.trip
                r = Adw.ActionRow(
                    title=esc(f"{t.origin} → {t.dest} · {i.dest.short}"),
                    subtitle=esc(stats.nice_date(t.dep_date, with_weekday=True)
                                 + (f" · {t.flight_no}" if t.flight_no else "")),
                    activatable=True)
                r.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
                r.connect("activated", lambda _r, tid=t.id: self.emit("show-trip", tid))
                row.add_row(r)
            self.countries_group.add(row)
            self._country_rows.append(row)

    @staticmethod
    def _sub(infos):
        n = len(infos)
        word = plural(n, "lot", "loty", "lotów", "flight", "flights")
        mins = sum(i.minutes for i in infos)
        approx = any(i.approx for i in infos)
        return f"{n} {word} · {geo.fmt_duration(mins, approx)}"

    @staticmethod
    def _km_label(infos, css="numeric"):
        lab = Gtk.Label(label=geo.fmt_km(sum(i.km for i in infos)), valign=Gtk.Align.CENTER)
        lab.add_css_class(css)
        if css == "numeric":
            lab.add_css_class("dim-label")
        return lab
