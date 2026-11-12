"""Planned flights → .ics for Linux iCloud Calendar (`linux-icloud-calendar --import`).
Times carry the airport's own time zone (TZID), so the calendar shows them right in any zone."""
import os
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone

from . import geo
from .i18n import _

CALENDAR_APP = "linux-icloud-calendar"
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "linux-skytrack", "calendar")


def _esc(s):
    return (str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line):
    """RFC 5545: lines over 75 octets continue on the next line after a space."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > 74:
            out.append(cur.decode("utf-8"))
            cur = b" "
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def _local(d, t):
    return d.replace("-", "") + "T" + t.replace(":", "")[:4] + "00"


def summary(info):
    t = info.trip
    s = f"✈ {t.origin} → {t.dest}"
    return s + (f" · {t.flight_no}" if t.flight_no else "")


def event(info, now=None):
    t, a, b = info.trip, info.origin, info.dest
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VEVENT", f"UID:skytrack-{t.id}-{t.dep_date}@linux-skytrack", f"DTSTAMP:{stamp}",
             "SUMMARY:" + _esc(summary(info))]
    if t.dep_time:
        lines.append(f"DTSTART;TZID={a.tz}:{_local(t.dep_date, t.dep_time)}")
        ad, at, _est = info.arrival
        if at:
            lines.append(f"DTEND;TZID={b.tz}:{_local(ad or t.dep_date, at)}")
        else:
            lines.append(f"DURATION:PT{max(30, int(info.minutes))}M")
    else:                                   # no time known: an all-day event on the departure day
        d = date.fromisoformat(t.dep_date)
        lines.append("DTSTART;VALUE=DATE:" + d.strftime("%Y%m%d"))
        lines.append("DTEND;VALUE=DATE:" + (d + timedelta(days=1)).strftime("%Y%m%d"))
    lines.append("LOCATION:" + _esc(f"{a.name} ({t.origin})"))
    desc = [f"{a.label} → {b.label}"]
    if t.flight_no or t.airline:
        desc.append(" · ".join(x for x in (t.flight_no, t.airline) if x))
    if t.seat:
        desc.append(_('Miejsce: {0}').format(t.seat))
    if t.aircraft:
        desc.append(_('Samolot: {0}').format(t.aircraft))
    desc.append(_('{0} · ok. {1} w powietrzu').format(geo.fmt_km(info.km), geo.fmt_duration(info.minutes, info.approx)))
    desc.append(_('Dodane z Linux-SkyTrack'))
    lines.append("DESCRIPTION:" + _esc("\n".join(desc)))
    lines.append("END:VEVENT")
    return lines


def ics(legs, now=None):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JGu//Linux-SkyTrack//EN", "CALSCALE:GREGORIAN"]
    for info in legs:
        lines += event(info, now)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def export(legs, parent=None):
    """Write the file and hand it to Linux iCloud Calendar (or the default calendar app).
    Returns 'calendar', 'default' or raises OSError."""
    os.makedirs(CACHE, exist_ok=True)
    first = legs[0].trip
    path = os.path.join(CACHE, f"skytrack-{first.origin}-{first.dest}-{first.dep_date}.ics")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(ics(legs))
    exe = shutil.which(CALENDAR_APP)
    if exe:
        subprocess.Popen([exe, "--import", path], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "calendar"
    from gi.repository import Gio
    Gio.AppInfo.launch_default_for_uri("file://" + path, None)
    return "default"
