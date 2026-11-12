"""'Podsumowanie' page: the selected year (or all years) as a poster + facts, saved as PNG."""
import io
from datetime import date

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, GObject, Gtk

from . import wrapped
from .i18n import IS_PL, _


def esc(s):
    return GLib.markup_escape_text(str(s))


class SummaryPage(Gtk.Box):
    __gsignals__ = {"year-chosen": (GObject.SignalFlags.RUN_FIRST, None, (int,))}   # 0 = all years

    def __init__(self, airports, web_dir):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.airports, self.web_dir = airports, web_dir
        self.theme = "system"
        self._summary = None
        self._png = None
        self._args = None

        self.stack = Gtk.Stack(vexpand=True)
        self.empty = Adw.StatusPage(icon_name="skytrack-plane-symbolic",
                                    title=_('Brak lotów do podsumowania'),
                                    description=_('Gdy odbędziesz pierwszy lot, zobaczysz tu swój rok w powietrzu.'))
        self.stack.add_named(self.empty, "empty")

        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        clamp = Adw.Clamp(maximum_size=1100, margin_top=24, margin_bottom=24, margin_start=18, margin_end=18)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.title = Gtk.Label(xalign=0, css_classes=["title-1"])
        self.subtitle = Gtk.Label(xalign=0, css_classes=["dim-label"], wrap=True)
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        head.append(self.title)
        head.append(self.subtitle)
        outer.append(head)
        # year picker right here (the same choice as "Okres" in the header bar)
        self.years_box = Gtk.Box(spacing=0, css_classes=["linked"])
        ys = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                propagate_natural_width=True, halign=Gtk.Align.START)
        ys.set_child(self.years_box)
        outer.append(ys)
        self._years_shown = None
        self._year_buttons = {}
        self._setting_year = False

        self.flow = Gtk.Box(spacing=28)
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True,
                                   width_request=432, height_request=540, valign=Gtk.Align.START,
                                   css_classes=["card"], overflow=Gtk.Overflow.HIDDEN,
                                   alternative_text=_('Podsumowanie jako obraz'))
        self.flow.append(self.picture)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, hexpand=True)
        btns = Gtk.Box(spacing=8)
        save = Gtk.Button(css_classes=["suggested-action", "pill"])
        save.set_child(Adw.ButtonContent(icon_name="document-save-symbolic", label=_('Zapisz jako obraz…')))
        save.connect("clicked", self._on_save)
        btns.append(save)
        right.append(btns)
        self.facts = Adw.PreferencesGroup()
        right.append(self.facts)
        self._fact_rows = []
        self.flow.append(right)
        outer.append(self.flow)
        clamp.set_child(outer)
        scroll.set_child(clamp)
        self.stack.add_named(scroll, "summary")
        self.append(self.stack)
        self.toasts = None

    def set_narrow(self, narrow):
        self.flow.set_orientation(Gtk.Orientation.VERTICAL if narrow else Gtk.Orientation.HORIZONTAL)
        self.picture.set_halign(Gtk.Align.CENTER if narrow else Gtk.Align.FILL)

    def set_theme(self, theme):
        self.theme = theme
        if self._args:
            self.refresh(*self._args)

    def _fill_years(self, all_flown, year):
        years = sorted({i.year for i in all_flown}, reverse=True)
        if years != self._years_shown:
            self._years_shown = years
            while (c := self.years_box.get_first_child()) is not None:
                self.years_box.remove(c)
            self._year_buttons = {}
            first = None
            for y in [0] + years:
                b = Gtk.ToggleButton(label=_('Wszystkie lata') if y == 0 else str(y))
                if first is None:
                    first = b
                else:
                    b.set_group(first)
                b.connect("toggled", self._on_year_toggled, y)
                self.years_box.append(b)
                self._year_buttons[y] = b
        self._setting_year = True
        btn = self._year_buttons.get(year or 0)
        if btn:
            btn.set_active(True)
        else:
            for b in self._year_buttons.values():
                b.set_active(False)
        self._setting_year = False

    def _on_year_toggled(self, btn, year):
        if btn.get_active() and not self._setting_year:
            self.emit("year-chosen", year)

    def refresh(self, all_flown, year, home):
        self._args = (all_flown, year, home)
        self._fill_years(all_flown, year)
        s = wrapped.summary(all_flown, year, home, self.airports)
        self._summary = s
        if not s:
            if year is not None:
                self.empty.set_title(_('Brak lotów w {0}').format(year))
            else:
                self.empty.set_title(_('Brak lotów do podsumowania'))
            self.stack.set_visible_child_name("empty")
            return
        self.stack.set_visible_child_name("summary")
        if year is not None:
            self.title.set_label(_('Podsumowanie {0}').format(year))
            running = year == date.today().year
            self.subtitle.set_label(_('Twój rok w powietrzu') +
                                    (_(' — rok jeszcze trwa, podsumowanie rośnie z każdym lotem.') if running else "."))
        else:
            self.title.set_label(_('Podsumowanie — wszystkie lata'))
            self.subtitle.set_label(_('Wybierz rok poniżej, żeby zobaczyć jeden rok.'))
        surf = wrapped.render(s, self.theme, self.web_dir)
        buf = io.BytesIO()
        surf.write_to_png(buf)
        self._png = buf.getvalue()
        self.picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(self._png)))
        for r in self._fact_rows:
            self.facts.remove(r)
        self._fact_rows = []
        for label, value in wrapped.facts(s):
            row = Adw.ActionRow(title=esc(label), subtitle=esc(value), css_classes=["property"])
            self.facts.add(row)
            self._fact_rows.append(row)

    def _on_save(self, *_a):
        if not self._png:
            return
        y = self._summary["year"] if self._summary else None
        base = "skytrack-podsumowanie" if IS_PL else "skytrack-summary"
        name = f"{base}-{y}.png" if y is not None else f"{base}.png"
        dlg = Gtk.FileDialog(title=_('Zapisz podsumowanie jako obraz'), initial_name=name)
        dlg.save(self.get_root(), None, self._on_save_file)

    def _on_save_file(self, dlg, res):
        try:
            gfile = dlg.save_finish(res)
        except GLib.Error:
            return
        root = self.get_root()
        try:
            gfile.replace_contents(self._png, None, False, 0, None)
            msg = _('Zapisano {0}').format(gfile.get_basename())
        except GLib.Error as e:
            msg = _('Błąd zapisu: {0}').format(e.message)
        if hasattr(root, "toasts"):
            root.toasts.add_toast(Adw.Toast(title=msg, timeout=4))
