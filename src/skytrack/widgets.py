"""Flighty-style widgets: boarding-pass card, route line, animated counter."""
import math
import random

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

from . import geo, stats
from .i18n import _

# plane silhouette (16x16, nose up) — same shape as the app's symbolic icon
PLANE = [(8, .8), (9.2, 3), (9.2, 5.6), (15, 9.2), (15, 10.8), (9.2, 9), (9.2, 12.4), (11, 13.8),
         (11, 15), (8, 14.2), (5, 15), (5, 13.8), (6.8, 12.4), (6.8, 9), (1, 10.8), (1, 9.2),
         (6.8, 5.6), (6.8, 3)]


class RouteLine(Gtk.DrawingArea):
    """GDN ●----✈----● LHR line; dashed when planned, plane at progress (0..1)."""

    def __init__(self, planned=False, progress=0.5):
        super().__init__(hexpand=True, content_height=26)
        self.planned = planned
        self.progress = progress
        self.set_draw_func(self._draw)

    def _draw(self, area, cr, w, h):
        fg = area.get_color()
        y = h / 2
        x0, x1 = 6, w - 6
        cr.set_line_width(1.6)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, .45)
        if self.planned:
            cr.set_dash([4, 4])
        cr.move_to(x0, y)
        cr.line_to(x1, y)
        cr.stroke()
        cr.set_dash([])
        for x in (x0, x1):
            cr.arc(x, y, 3.5, 0, 2 * math.pi)
            cr.set_source_rgba(fg.red, fg.green, fg.blue, .9)
            cr.fill()
        # plane, nose pointing right
        px = x0 + (x1 - x0) * self.progress
        cr.save()
        cr.translate(px, y)
        cr.rotate(math.pi / 2)
        cr.scale(1.15, 1.15)
        cr.translate(-8, -8)
        cr.move_to(*PLANE[0])
        for p in PLANE[1:]:
            cr.line_to(*p)
        cr.close_path()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 1)
        cr.fill()
        cr.restore()


def _field(label, value, sub=""):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
    lab = Gtk.Label(label=label.upper(), xalign=0)
    lab.add_css_class("pass-label")
    val = Gtk.Label(label=value, xalign=0, ellipsize=3)
    val.add_css_class("pass-value")
    box.append(lab)
    box.append(val)
    if sub:
        s = Gtk.Label(label=sub, xalign=0, ellipsize=3)
        s.add_css_class("pass-sub")
        box.append(s)
    return box


class PassCard(Gtk.Box):
    """Boarding-pass style summary of one trip."""

    __gsignals__ = {
        "edit": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "return-flight": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "calendar": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, info, buttons=True, caption=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("pass")
        self.info = info
        t, a, b = info.trip, info.origin, info.dest

        # top line: flight / date  ……  badge
        top = Gtk.Box(spacing=8)
        bits = [x for x in (t.flight_no, t.airline) if x]
        head = " · ".join(bits + [stats.nice_date(t.dep_date, with_weekday=True)])
        if caption:
            head = f"{caption} · {head}"
        tl = Gtk.Label(label=head, xalign=0, hexpand=True, ellipsize=3)
        tl.add_css_class("pass-top")
        top.append(tl)
        badge = Gtk.Label(label=info.countdown if info.planned else "odbyta")
        badge.add_css_class("badge")
        badge.add_css_class("planned" if info.planned else "flown")
        top.append(badge)
        self.append(top)

        # codes + route line
        mid = Gtk.Box(spacing=10)
        ca = Gtk.Label(label=t.origin)
        ca.add_css_class("pass-code")
        cb = Gtk.Label(label=t.dest)
        cb.add_css_class("pass-code")
        mid.append(ca)
        mid.append(RouteLine(planned=info.planned, progress=0.5))
        mid.append(cb)
        self.append(mid)
        cities = Gtk.Box()
        la = Gtk.Label(label=a.short, xalign=0, hexpand=True, ellipsize=3)
        la.add_css_class("pass-city")
        lb = Gtk.Label(label=b.short, xalign=1, hexpand=True, ellipsize=3)
        lb.add_css_class("pass-city")
        cities.append(la)
        cities.append(lb)
        self.append(cities)

        sep = Gtk.Separator()
        sep.add_css_class("pass-sep")
        self.append(sep)

        # fields
        grid = Gtk.Box(spacing=8, homogeneous=True)
        dep_val = t.dep_time or "—"
        dep_sub = geo.utc_offset_label(a.tz, t.dep_date, t.dep_time or "12:00")
        ad, at, est = info.arrival
        if at:
            arr_val = ("≈ " if est else "") + at
            nxt = ""
            if ad and ad != t.dep_date:
                nxt = " +1 d" if ad > t.dep_date else " −1 d"
            arr_sub = geo.utc_offset_label(b.tz, ad, at) + nxt
        else:
            arr_val, arr_sub = "—", geo.utc_offset_label(b.tz, t.dep_date)
        grid.append(_field("Start", dep_val, dep_sub))
        grid.append(_field(_('Lądowanie'), arr_val, arr_sub))
        grid.append(_field(_('Czas lotu'), geo.fmt_duration(info.minutes, info.approx).replace(" min", "m")
                           .replace(" h ", "h ").replace("≈ ", "≈"),
                           geo.tz_difference_label(a.tz, b.tz, t.dep_date)))
        grid.append(_field(_('Dystans'), geo.fmt_km(info.km), t.aircraft or ""))
        self.append(grid)

        self.buttons = None
        if buttons:
            row = Gtk.Box(spacing=6, halign=Gtk.Align.END, margin_top=4)
            self.buttons = row
            ret = Gtk.Button(label=_('Lot powrotny'), tooltip_text=_('Dodaj lot w drugą stronę'))
            ret.add_css_class("flat")
            ret.connect("clicked", lambda *_: self.emit("return-flight", info.trip))
            self.ret_btn = ret
            ed = Gtk.Button(label=_('Edytuj'))
            ed.add_css_class("flat")
            ed.connect("clicked", lambda *_: self.emit("edit", info.trip))
            if info.planned:
                cal = Gtk.Button(label=_('📅 Do kalendarza'),
                                 tooltip_text=_('Dodaj ten lot (i powrót, jeśli jest) do kalendarza'))
                cal.add_css_class("flat")
                cal.connect("clicked", lambda *_: self.emit("calendar", info))
                row.append(cal)
            row.append(ret)
            row.append(ed)
            self.append(row)


def add_card_button(card, label, tooltip, callback):
    if card.buttons is None:
        return None
    b = Gtk.Button(label=label, tooltip_text=tooltip)
    b.add_css_class("flat")
    b.connect("clicked", lambda *_: callback())
    card.buttons.prepend(b)
    return b


class CounterAnimator:
    """Animate a label to a value: count-up, or 'decode' scramble in Matrix mode."""

    def __init__(self, label, fmt=geo.fmt_km):
        self.label = label
        self.fmt = fmt
        self.value = 0.0
        self.anim = None
        self.matrix = False

    def set(self, value, animate=True):
        start = self.value
        self.value = value
        if self.anim:
            self.anim.skip()
        if not animate or abs(value - start) < 1:
            self.label.set_label(self.fmt(value))
            return
        final = self.fmt(value)

        def tick(p):
            if self.matrix:
                done = int(len(final) * p)
                out = []
                for i, ch in enumerate(final):
                    out.append(ch if i < done or not ch.isdigit() else random.choice("0123456789"))
                self.label.set_label("".join(out))
            else:
                self.label.set_label(self.fmt(start + (value - start) * p))

        target = Adw.CallbackAnimationTarget.new(tick)
        self.anim = Adw.TimedAnimation.new(self.label, 0.0, 1.0, 1100 if self.matrix else 900, target)
        self.anim.set_easing(Adw.Easing.LINEAR if self.matrix else Adw.Easing.EASE_OUT_CUBIC)
        self.anim.connect("done", lambda *_: self.label.set_label(final))
        self.anim.play()
