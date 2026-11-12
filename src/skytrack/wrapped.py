"""'Podsumowanie' — the year (or all years) in flights, and a poster image drawn with cairo."""
import json
import math
import os
from collections import Counter
from functools import lru_cache

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo

from . import geo, stats
from .i18n import IS_PL, _, plural

W, H = 1080, 1350
FONT = "Ubuntu Sans,Ubuntu,Cantarell,Inter,Sans"

THEMES = {
    #           background top, bottom,  text,      muted,     accent,    accent 2,  land,      border,    visited
    "system":  ("#1a4fa0", "#0b1f45", "#ffffff", "#b9cdf2", "#ffffff", "#ffbe6f", "#284a86", "#3e63a3", "#ffbe6f"),
    "flighty": ("#0c1222", "#05070d", "#ffffff", "#8a95b3", "#6f97ff", "#ffc83d", "#151d33", "#26324f", "#ffc83d"),
    "matrix":  ("#001a07", "#000000", "#39ff6a", "#1fa344", "#39ff6a", "#d4ff5c", "#032c0e", "#0d6b25", "#1f8f00"),
}


# ---- numbers ------------------------------------------------------------------------------------
def summary(all_flown, year, home, airports):
    """Facts for one year (or all years when year is None). None when there is nothing to show."""
    infos = [i for i in all_flown if year is None or i.year == year]
    if not infos:
        return None
    infos.sort(key=lambda i: (i.trip.dep_date, i.trip.dep_time))
    t = stats.totals(infos, home)
    before = {i.dest.cc for i in all_flown if year is not None and i.year < year} - {home}
    countries = []
    for i in infos:
        cc = i.dest.cc
        if cc != home and cc not in countries:
            countries.append(cc)
    new = [cc for cc in countries if cc not in before] if year is not None else countries
    dest_count = Counter(i.trip.dest for i in infos if i.dest.cc != home) or Counter(i.trip.dest for i in infos)
    top_dest, top_n = dest_count.most_common(1)[0]
    by_month = Counter()
    for i in infos:
        by_month[i.month] += i.km
    best_month = by_month.most_common(1)[0][0] if year is not None else None
    airlines = Counter(i.trip.airline.strip() for i in infos if i.trip.airline.strip())
    trips = len({i.trip.trip_group or f"#{i.trip.id}" for i in infos})
    return {
        "year": year, "infos": infos, "totals": t, "countries": countries, "new": new,
        "names": {cc: airports.country_name(cc) for cc in countries},
        "top_dest": airports.get(top_dest), "top_n": top_n,
        "best_month": best_month, "month_km": [by_month.get(m, 0) for m in range(1, 13)],
        "airline": airlines.most_common(1)[0] if airlines else None,
        "trips": trips, "home": home,
        "first": infos[0], "last": infos[-1],
    }


def facts(s):
    """[(label, value)] for the list next to the poster."""
    t = s["totals"]
    out = [
        (_('Kilometry'), geo.fmt_km(t["km"])),
        (_('Loty'), f"{t['flights']} · {s['trips']} {plural(s['trips'], 'podróż', 'podróże', 'podróży', 'trip', 'trips')}"),
        (_('W powietrzu'), geo.fmt_duration(t["minutes"], t["approx"])),
        (_('Lotniska'), str(t["airports"])),
        (_('Kraje (za granicą)'), ", ".join(s["names"][c] for c in s["countries"]) or "—"),
    ]
    if s["year"] is not None:
        out.append((_('Nowe kraje w tym roku'), ", ".join(s["names"][c] for c in s["new"]) or "—"))
    lg = t["longest"]
    out.append((_('Najdłuższy lot'), f"{lg.trip.origin} → {lg.trip.dest} · {geo.fmt_km(lg.km)}"))
    d = s["top_dest"]
    if d:
        out.append((_('Najczęstszy cel'), f"{city(d)} ({d.iata}) · {s['top_n']}×"))
    if s["best_month"]:
        out.append((_('Najbardziej lotniczy miesiąc'), stats.MONTHS[s["best_month"] - 1]))
    if s["airline"]:
        out.append((_('Najczęstsza linia'), f"{s['airline'][0]} · {s['airline'][1]}×"))
    out.append((_('Dookoła Ziemi'), _dec(f"{t['laps']:.2f}×")))
    out.append((_('Do Księżyca'), _dec(f"{t['km'] / 384400 * 100:.1f} %")))
    return out


def _dec(s):
    return s.replace(".", ",") if IS_PL else s


# ---- world outlines (shared with the map: web/world.js) -----------------------------------------
@lru_cache(maxsize=1)
def world(web_dir):
    """[(cc, [ring, …])] with rings as [(lon, lat), …]."""
    try:
        with open(os.path.join(web_dir, "world.js"), encoding="utf-8") as f:
            text = f.read()
        topo = json.loads(text[text.index("=") + 1:].strip().rstrip(";"))
    except (OSError, ValueError):
        return []
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idx):
        pts = []
        for a in idx:
            seg = arcs[a] if a >= 0 else arcs[~a][::-1]
            pts.extend(seg if not pts else seg[1:])
        return pts

    out = []
    for g in topo["objects"]["countries"]["geometries"]:
        cc = (g.get("properties") or {}).get("cc", "")
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]] if g["type"] == "Polygon" else []
        rings = [ring(r) for poly in polys for r in poly]
        out.append((cc, rings))
    return out


# ---- drawing --------------------------------------------------------------------------------------
def _rgb(hex_):
    h = hex_.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def city(ap):
    """City name in the interface language (Kijów, Ateny in Polish)."""
    if ap is None:
        return ""
    if IS_PL:
        from .airports import CITY_PL
        return CITY_PL.get(ap.city, ap.short)
    return ap.short


def _measure(cr, text, size, weight="Bold"):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription.from_string(f"{FONT} {weight} {size}px"))
    layout.set_text(text, -1)
    return layout.get_pixel_size()


def _text(cr, x, y, text, size, color, weight="Bold", width=None, align="left", alpha=1.0, spacing=0):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription.from_string(f"{FONT} {weight} {size}px"))
    if spacing:
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
        layout.set_attributes(attrs)
    layout.set_text(text, -1)
    if width:
        layout.set_width(int(width * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
    if align != "left":
        layout.set_alignment(Pango.Alignment.RIGHT if align == "right" else Pango.Alignment.CENTER)
    r, g, b = _rgb(color)
    cr.set_source_rgba(r, g, b, alpha)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)
    return layout.get_pixel_size()[1]


def _gc(a, b, n=64):
    """Great-circle points (lon, lat) between airports a and b."""
    φ1, λ1, φ2, λ2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    d = 2 * math.asin(math.sqrt(math.sin((φ2 - φ1) / 2) ** 2 +
                                math.cos(φ1) * math.cos(φ2) * math.sin((λ2 - λ1) / 2) ** 2))
    if d < 1e-9:
        return [(a.lon, a.lat), (b.lon, b.lat)]
    pts, prev = [], None
    for i in range(n + 1):
        f = i / n
        A, B = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
        x = A * math.cos(φ1) * math.cos(λ1) + B * math.cos(φ2) * math.cos(λ2)
        y = A * math.cos(φ1) * math.sin(λ1) + B * math.cos(φ2) * math.sin(λ2)
        z = A * math.sin(φ1) + B * math.sin(φ2)
        lon = math.degrees(math.atan2(y, x))
        lat = math.degrees(math.atan2(z, math.hypot(x, y)))
        if prev is not None:
            while lon - prev > 180:
                lon -= 360
            while lon - prev < -180:
                lon += 360
        prev = lon
        pts.append((lon, lat))
    return pts


def _draw_map(cr, s, box, pal, web_dir):
    x0, y0, bw, bh = box
    lines = [_gc(i.origin, i.dest) for i in s["infos"]]
    lons = [p[0] for ln in lines for p in ln]
    lats = [p[1] for ln in lines for p in ln]
    lo1, lo2, la1, la2 = min(lons), max(lons), min(lats), max(lats)
    # padding and a sensible minimum span
    span_lo, span_la = max(lo2 - lo1, 8), max(la2 - la1, 5)
    clo, cla = (lo1 + lo2) / 2, (la1 + la2) / 2
    span_lo, span_la = span_lo * 1.35, span_la * 1.35
    kx = math.cos(math.radians(max(min(cla, 70), -70)))
    # fit the box keeping the aspect ratio (equirectangular with cos(lat) scaling)
    scale = min(bw / (span_lo * kx), bh / span_la)

    def P(lon, lat):
        return x0 + bw / 2 + (lon - clo) * kx * scale, y0 + bh / 2 - (lat - cla) * scale

    cr.save()
    r = 28
    cr.new_path()
    cr.arc(x0 + bw - r, y0 + r, r, -math.pi / 2, 0)
    cr.arc(x0 + bw - r, y0 + bh - r, r, 0, math.pi / 2)
    cr.arc(x0 + r, y0 + bh - r, r, math.pi / 2, math.pi)
    cr.arc(x0 + r, y0 + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
    cr.clip()
    cr.set_source_rgba(0, 0, 0, 0.22)
    cr.paint()
    visited = set(s["countries"])
    for cc, rings in world(web_dir):
        for shift in (-360, 0, 360):
            for rg in rings:
                if len(rg) < 3:
                    continue
                if max(p[0] for p in rg) + shift < clo - span_lo or min(p[0] for p in rg) + shift > clo + span_lo:
                    continue
                cr.move_to(*P(rg[0][0] + shift, rg[0][1]))
                for lon, lat in rg[1:]:
                    cr.line_to(*P(lon + shift, lat))
                cr.close_path()
            if not cr.has_current_point():
                continue
            fill = pal[8] if cc in visited else pal[6]
            cr.set_source_rgba(*_rgb(fill), 0.55 if cc in visited else 1)
            cr.fill_preserve()
            cr.set_source_rgb(*_rgb(pal[7]))
            cr.set_line_width(1)
            cr.stroke()
    # arcs
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for ln in lines:
        cr.new_path()
        cr.move_to(*P(*ln[0]))
        for p in ln[1:]:
            cr.line_to(*P(*p))
        cr.set_source_rgba(*_rgb(pal[4]), 0.9)
        cr.set_line_width(3.5)
        cr.stroke()
    # airports
    seen = {}
    for i in s["infos"]:
        seen[i.origin.iata] = i.origin
        seen[i.dest.iata] = i.dest
    dots = {code: P(ap.lon, ap.lat) for code, ap in seen.items()}
    for x, y in dots.values():
        cr.new_path()
        cr.arc(x, y, 8, 0, 2 * math.pi)
        cr.set_source_rgb(*_rgb(pal[5]))
        cr.fill_preserve()
        cr.set_source_rgb(*_rgb(pal[1]))
        cr.set_line_width(3)
        cr.stroke()
    # labels: try right, left, above, below … and skip spots taken by other labels or dots
    placed = [(x - 10, y - 10, 20, 20) for x, y in dots.values()]

    def free(r):
        x, y, w, h = r
        return (x0 <= x and x + w <= x0 + bw and y0 <= y and y + h <= y0 + bh and
                not any(x < px + pw and px < x + w and y < py + ph and py < y + h for px, py, pw, ph in placed))
    order = sorted(dots.items(), key=lambda kv: (kv[1][1], kv[1][0]))
    for code, (x, y) in order:
        w, h = _measure(cr, code, 22)
        tries = [(x + 12, y - h / 2), (x - 12 - w, y - h / 2), (x - w / 2, y - 12 - h), (x - w / 2, y + 12),
                 (x + 10, y - h - 6), (x + 10, y + 6), (x - 10 - w, y - h - 6), (x - 10 - w, y + 6),
                 (x + 12, y - h * 1.6), (x + 12, y + h * 0.6)]
        spot = next(((tx, ty) for tx, ty in tries if free((tx, ty, w, h))), None)
        if spot is None:
            continue                     # crowded: the dot stays, the label is left out
        placed.append((spot[0], spot[1], w, h))
        _text(cr, spot[0], spot[1], code, 22, pal[2])
        cr.new_path()
    cr.restore()


def render(s, theme, web_dir):
    """Poster (cairo.ImageSurface, 1080×1350) for the summary s."""
    pal = THEMES.get(theme, THEMES["system"])
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    grad = cairo.LinearGradient(0, 0, 0, H)
    grad.add_color_stop_rgb(0, *_rgb(pal[0]))
    grad.add_color_stop_rgb(1, *_rgb(pal[1]))
    cr.set_source(grad)
    cr.paint()
    t = s["totals"]
    M = 72
    title = (_('MÓJ ROK {0} W POWIETRZU').format(s["year"]) if s["year"] is not None
             else _('WSZYSTKIE MOJE LOTY'))
    _text(cr, M, 64, "✈  SKYTRACK", 26, pal[3], spacing=4)
    _text(cr, M, 104, title, 44, pal[2], weight="Heavy")

    _draw_map(cr, s, (M, 180, W - 2 * M, 540), pal, web_dir)

    y = 750
    _text(cr, M, y, geo.fmt_km(t["km"]), 112, pal[2], weight="Heavy")
    y += 138
    flights = f"{t['flights']} {plural(t['flights'], 'lot', 'loty', 'lotów', 'flight', 'flights')}"
    _text(cr, M, y, f"{flights} · {geo.fmt_duration(t['minutes'], t['approx'])} "
          f"{_('w powietrzu')} · {_dec(format(t['laps'], '.2f'))}× {_('dookoła Ziemi')}",
          30, pal[3], weight="SemiBold", width=W - 2 * M)
    y += 66

    def stat(x, y, label, value, w):
        _text(cr, x, y, label.upper(), 20, pal[3], weight="Bold", spacing=2.5)
        _text(cr, x, y + 30, value, 36, pal[2], weight="Bold", width=w)

    col = (W - 2 * M) / 2
    nc = len(s["countries"])
    stat(M, y, _('Lotniska'), str(t["airports"]), col - 20)
    stat(M + col, y, _('Kraje za granicą'), str(nc), col - 20)
    y += 104
    lg = t["longest"]
    stat(M, y, _('Najdłuższy lot'), f"{lg.trip.origin} → {lg.trip.dest} · {geo.fmt_km(lg.km)}", col - 20)
    d = s["top_dest"]
    stat(M + col, y, _('Najczęstszy cel'), f"{city(d)} · {s['top_n']}×" if d else "—", col - 20)
    y += 104
    if s["year"] is not None:
        new = [s["names"][c] for c in s["new"]]
        stat(M, y, _('Nowe kraje'), ", ".join(new) if new else "—", col - 20)
        if s["best_month"]:
            stat(M + col, y, _('Najwięcej w powietrzu'), stats.MONTHS[s["best_month"] - 1], col - 20)
    else:
        first = s["first"].trip.dep_date[:4]
        stat(M, y, _('Od roku'), first, col - 20)
        stat(M + col, y, _('Kraje'), ", ".join(s["names"][c] for c in s["countries"][:4]) or "—", col - 20)

    cr.set_source_rgba(*_rgb(pal[3]), 0.35)
    cr.rectangle(M, H - 92, W - 2 * M, 1.5)
    cr.fill()
    _text(cr, M, H - 74, "linux-skytrack", 22, pal[3], weight="SemiBold")
    _text(cr, M, H - 74, "Created by: JGu", 22, pal[3], weight="SemiBold", width=W - 2 * M, align="right")
    surf.flush()
    return surf
