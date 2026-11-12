"""Geometry and time helpers: great-circle distance, flight time, time zones."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from .i18n import IS_PL, _

EARTH_RADIUS_KM = 6371.0088
EARTH_CIRCUMFERENCE_KM = 40075.017
CRUISE_KMH = 820.0       # typical jet cruise ground speed used for estimates
OVERHEAD_MIN = 30.0      # taxi, climb, approach


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle (haversine) distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def estimate_minutes(km):
    """Rough block time for a jet flight of the given great-circle length."""
    if km <= 0:
        return 0
    return round(km / CRUISE_KMH * 60 + OVERHEAD_MIN)


def local_dt(date_str, time_str, tz_name):
    """Aware datetime from local date (YYYY-MM-DD), time (HH:MM) and IANA zone."""
    if not date_str or not time_str:
        return None
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        return naive.replace(tzinfo=ZoneInfo(tz_name or "UTC"))
    except (ValueError, KeyError):
        return None


def real_minutes(dep_date, dep_time, dep_tz, arr_date, arr_time, arr_tz):
    """Actual flight time from local departure/arrival, honouring both time zones."""
    d = local_dt(dep_date, dep_time, dep_tz)
    a = local_dt(arr_date, arr_time, arr_tz)
    if not d or not a:
        return None
    minutes = round((a - d).total_seconds() / 60)
    return minutes if 0 < minutes < 30 * 60 else None


def utc_offset_label(tz_name, date_str=None, time_str="12:00"):
    """'UTC+1', 'UTC+5:30' for the zone at the given local date (DST aware)."""
    try:
        if date_str:
            dt = local_dt(date_str, time_str or "12:00", tz_name)
        else:
            dt = datetime.now(ZoneInfo(tz_name))
        off = dt.utcoffset().total_seconds() / 60
    except Exception:
        return "UTC"
    sign = "+" if off >= 0 else "−"
    off = abs(int(off))
    h, m = divmod(off, 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def fmt_km(km):
    return f"{round(km):,}".replace(",", " " if IS_PL else ",") + " km"


def fmt_int(n):
    return f"{round(n):,}".replace(",", "\u202f" if IS_PL else ",")


def fmt_dec(x, digits=1):
    s = f"{x:.{digits}f}"
    return s.replace(".", ",") if IS_PL else s


def fmt_duration(minutes, approx=False):
    if minutes is None:
        return "—"
    h, m = divmod(int(round(minutes)), 60)
    s = f"{h} h {m:02d} min" if h else f"{m} min"
    return ("≈ " + s) if approx else s


# --- dates for manual / historical entry -------------------------------------------
_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d",
                 "%Y.%m.%d", "%d %m %Y")


def parse_date(text):
    """'14.02.2019', '2019-02-14', '14/02/2019', '14.2.19' -> '2019-02-14'; invalid -> None."""
    from datetime import date as _date
    t = (text or "").strip().replace(",", ".")
    if not t:
        return None
    for fmt in _DATE_FORMATS:
        try:
            d = datetime.strptime(t, fmt).date()
        except ValueError:
            continue
        if 1950 <= d.year <= _date.today().year + 5:
            return d.isoformat()
    return None


def fmt_date_pl(iso):
    try:
        y, m, d = iso.split("-")
        return f"{d}.{m}.{y}"
    except (ValueError, AttributeError):
        return ""


def arrival_estimate(dep_date, dep_time, dep_tz, minutes, arr_tz):
    """Local (date, time) at destination for a departure + block time, or (None, None)."""
    d = local_dt(dep_date, dep_time, dep_tz)
    if not d or minutes is None:
        return None, None
    from datetime import timedelta
    a = (d + timedelta(minutes=minutes)).astimezone(ZoneInfo(arr_tz or "UTC"))
    return a.date().isoformat(), a.strftime("%H:%M")


def tz_difference_label(tz_a, tz_b, date_str=None):
    """'+3 h', '−1 h', '+5:30 h', 'ta sama strefa'."""
    try:
        when = local_dt(date_str, "12:00", tz_a) if date_str else datetime.now(ZoneInfo(tz_a))
        oa = when.utcoffset().total_seconds()
        ob = when.astimezone(ZoneInfo(tz_b)).utcoffset().total_seconds()
    except Exception:
        return ""
    diff = int((ob - oa) / 60)
    if diff == 0:
        return _('ta sama strefa')
    sign = "+" if diff > 0 else "−"
    h, m = divmod(abs(diff), 60)
    return f"{sign}{h}" + (f":{m:02d}" if m else "") + " h"


def is_future(dep_date, dep_time, tz_name):
    """True when the departure is still ahead (planned trip)."""
    try:
        now = datetime.now(ZoneInfo(tz_name or "UTC"))
    except Exception:
        now = datetime.now()
    today = now.date().isoformat()
    if dep_date > today:
        return True
    if dep_date < today:
        return False
    if not dep_time:
        return False          # today without a time counts as flown
    return dep_time > now.strftime("%H:%M")


def countdown_label(dep_date, dep_time, tz_name):
    """'za 12 dni', 'jutro', 'za 3 h 20 min', 'dziś'."""
    from datetime import date as _date
    try:
        now = datetime.now(ZoneInfo(tz_name or "UTC"))
    except Exception:
        now = datetime.now()
    d = _date.fromisoformat(dep_date)
    days = (d - now.date()).days
    if days > 1:
        return _('za {0} dni').format(days)
    if days == 1:
        return _('jutro')
    dt = local_dt(dep_date, dep_time, tz_name)
    if dt:
        mins = int((dt - now).total_seconds() // 60)
        if mins > 0:
            h, m = divmod(mins, 60)
            return _('za {0} h {1:02d} min').format(h, m) if h else _('za {0} min').format(m)
    return _('dziś')
