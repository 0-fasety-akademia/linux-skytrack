"""Integration with linux-icloud-photos (0.15.0+): albums, thumbnails, opening, creating trip albums.

SkyTrack never logs in to iCloud itself. It calls linux-icloud-photos, which uses its own saved
session (bridge.py): no window, JSON result. If that session needs a login, the bridge answers
"login_required" and the user opens Linux iCloud Photos once.
"""
import hashlib
import json
import os
import shutil
import tempfile
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from gi.repository import Gio, GLib

from . import db, stats
from .i18n import IS_PL, _

FLATPAK_ID = "local.linuxicloudphotos.Photos"
CACHE_TTL = 6 * 3600          # thumbnails / album list are refreshed after 6 h (or on demand)
MIN_BRIDGE = (0, 15, 0)


def work_dir():
    """Temporary files shared with linux-icloud-photos (inside SkyTrack's cache: a Flatpak
    installation is given access to exactly this folder)."""
    d = os.path.join(db.cache_dir(), "bridge")
    os.makedirs(d, exist_ok=True)
    return d


def _cache():
    d = os.path.join(db.cache_dir(), "icloud")
    os.makedirs(d, exist_ok=True)
    return d


def _read_version(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.replace(" ", "").startswith("VERSION="):
                    v = line.split("=", 1)[1].strip().strip('"\'')
                    return tuple(int(x) for x in v.split(".")[:3])
    except (OSError, ValueError):
        pass
    return None


def installations():
    """[(argv prefix, version tuple or None, label)] of every Linux iCloud Photos found:
    the .deb (or any linux-icloud-photos in PATH) and the Flatpak (user and system)."""
    out = []
    exe = shutil.which("linux-icloud-photos")
    if exe:
        v = _read_version("/usr/lib/linux-icloud-photos/version.py")
        out.append(([exe], v, "deb"))
    if shutil.which("flatpak"):
        for base in (os.path.expanduser("~/.local/share/flatpak/app"), "/var/lib/flatpak/app"):
            root = os.path.join(base, FLATPAK_ID)
            if os.path.isdir(root):
                v = _read_version(os.path.join(root, "current", "active", "files", "lib",
                                               "linux-icloud-photos", "version.py"))
                # the Flatpak sees only what it is given: SkyTrack's cache folder holds the
                # bridge's JSON results, thumbnails and files to upload
                out.append((["flatpak", "run", f"--filesystem={db.cache_dir()}", FLATPAK_ID], v, "flatpak"))
                break
    return out


def command(min_version=None):
    """argv prefix that starts linux-icloud-photos (the newest one when several are installed and
    a minimum version is asked for), or None when it is not installed."""
    inst = installations()
    if not inst:
        return None
    if min_version is not None:
        ok = [i for i in inst if i[1] is None or i[1] >= min_version]
        if ok:
            ok.sort(key=lambda i: i[1] or (999,), reverse=True)
            return ok[0][0]
    return inst[0][0]


def available():
    return command() is not None


def installed_version():
    """Newest known version among the installations (None when unknown)."""
    vs = [i[1] for i in installations() if i[1] is not None]
    if not vs:
        return None
    return max(vs)


def version_text():
    """'0.16.0 (deb), 0.15.1 (flatpak)' — for messages."""
    return ", ".join(f"{'.'.join(map(str, v)) if v else '?'} ({label})" for _c, v, label in installations())


def bridge_supported():
    v = installed_version()
    return v is None or v >= MIN_BRIDGE


def empty_albums_supported():
    """Empty albums (planned trips) need linux-icloud-photos 0.15.1+."""
    v = installed_version()
    return v is None or v >= (0, 15, 1)


# --- trip time range ----------------------------------------------------------------------
def trip_range(info, all_infos):
    """(start, end) aware datetimes of 'the trip' for this flight: from departure day until the
    next flight in the log (the next leg / the return), at most 30 days; 3 days when nothing follows."""
    t = info.trip
    if t.trip_group:          # there-and-back trip: from the outbound flight to the return flight
        legs = sorted((i for i in all_infos if i.trip.trip_group == t.trip_group),
                      key=lambda i: (i.trip.dep_date, i.trip.dep_time))
        if len(legs) == 2:
            out, back = legs
            start = datetime.fromisoformat(out.trip.dep_date).replace(tzinfo=ZoneInfo(out.origin.tz))
            end = datetime.combine(date.fromisoformat(back.trip.dep_date), datetime.max.time()).replace(
                microsecond=0, tzinfo=ZoneInfo(back.origin.tz))
            return start, end
    start = datetime.fromisoformat(t.dep_date).replace(tzinfo=ZoneInfo(info.origin.tz))
    later = sorted((i for i in all_infos if (i.trip.dep_date, i.trip.dep_time) >
                    (t.dep_date, t.dep_time) and i.trip.id != t.id),
                   key=lambda i: (i.trip.dep_date, i.trip.dep_time))
    if later:
        nxt = later[0]
        end_day = date.fromisoformat(nxt.trip.dep_date)
        end = datetime.combine(end_day, datetime.max.time()).replace(
            microsecond=0, tzinfo=ZoneInfo(nxt.origin.tz))
        if (end - start).days > 30:
            end = start + timedelta(days=3, hours=23, minutes=59)
    else:
        end = start + timedelta(days=3, hours=23, minutes=59)
    return start, end


def default_album_name(info, start=None, end=None):
    from .airports import CITY_PL
    d = date.fromisoformat(info.trip.dep_date)
    city = CITY_PL.get(info.dest.city, info.dest.short) if IS_PL else info.dest.short
    return f"✈ {city} · {stats.MONTHS_GEN[d.month - 1]} {d.year}"


# --- running the bridge -----------------------------------------------------------------------
class BridgeCall:
    """One async call. callback(result_dict) on the main thread; progress(done, total) optional."""

    def __init__(self, args, callback, progress=None, min_version=None):
        cmd = command(min_version)
        self.callback = callback
        self.progress = progress
        if cmd is None:
            GLib.idle_add(callback, {"ok": False, "error": "not_installed"})
            return
        fd, self.out = tempfile.mkstemp(prefix="skytrack-icp-", suffix=".json", dir=work_dir())
        os.close(fd)
        try:
            self.proc = Gio.Subprocess.new(cmd + list(args) + ["--json", self.out],
                                           Gio.SubprocessFlags.STDOUT_PIPE |
                                           Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error as e:
            GLib.idle_add(callback, {"ok": False, "error": "failed", "message": e.message})
            return
        self.stream = Gio.DataInputStream.new(self.proc.get_stdout_pipe())
        self.stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self._on_line)
        self.proc.wait_async(None, self._on_exit)

    def _on_line(self, stream, res):
        try:
            line, _n = stream.read_line_finish_utf8(res)
        except GLib.Error:
            return
        if line is None:
            return
        parts = line.split()
        if self.progress and len(parts) == 3 and parts[0] == "progress":
            try:
                self.progress(int(parts[1]), int(parts[2]))
            except ValueError:
                pass
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self._on_line)

    def _on_exit(self, proc, res):
        try:
            proc.wait_finish(res)
        except GLib.Error:
            pass
        try:
            with open(self.out, encoding="utf-8") as f:
                result = json.load(f)
        except (OSError, ValueError):
            result = {"ok": False, "error": "failed",
                      "message": _('linux-icloud-photos nie zwróciło wyniku (wymagana wersja 0.15.0+)')}
        try:
            os.unlink(self.out)
        except OSError:
            pass
        self.callback(result)

    def cancel(self):
        try:
            self.proc.force_exit()
        except Exception:  # noqa: BLE001
            pass


def error_text(result):
    code = result.get("error")
    if code == "login_required":
        return _('Zaloguj się raz w Linux iCloud Photos — SkyTrack korzysta z tej samej sesji.')
    if code == "not_installed":
        return _('Linux iCloud Photos nie jest zainstalowane.')
    if code == "album_not_found":
        return _('Nie ma albumu „{0}” w iCloud.').format(result.get('message', ''))
    if code == "bad_option":
        return _('Zainstalowana wersja Linux iCloud Photos jest za stara (potrzebna 0.15.0 lub nowsza).')
    return result.get("message") or _('Nie udało się połączyć z iCloud.')


# --- albums list (cached) -----------------------------------------------------------------------
def cached_albums():
    try:
        with open(os.path.join(_cache(), "albums.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data.get("albums", []), data.get("time", 0)
    except (OSError, ValueError):
        return [], 0


def load_albums(callback, force=False):
    albums, when = cached_albums()
    if albums and not force and time.time() - when < CACHE_TTL:
        GLib.idle_add(callback, {"ok": True, "albums": albums, "cached": True})
        return None

    def done(result):
        if result.get("ok"):
            try:
                with open(os.path.join(_cache(), "albums.json"), "w", encoding="utf-8") as f:
                    json.dump({"time": time.time(), "albums": result["albums"]}, f, ensure_ascii=False)
            except OSError:
                pass
        elif albums:   # offline / session problem: fall back to the old list, keep the error
            result = dict(result, albums=albums, cached=True)
        callback(result)
    return BridgeCall(["--albums-json"], done)


def suggest(albums, info):
    """Albums sorted so the ones that look like this trip come first (city, country, IATA, year)."""
    from .airports import CITY_PL, _norm
    d = date.fromisoformat(info.trip.dep_date)
    keys = {_norm(x) for x in (info.dest.city, CITY_PL.get(info.dest.city, ""), info.dest.country,
                               info.dest.iata) if x and len(x) >= 3}
    year = str(d.year)

    def score(a):
        n = _norm(a["name"])
        s = 0
        if any(k in n for k in keys):
            s += 10
        if year in n:
            s += 3
        if a.get("smart"):
            s -= 20
        return -s

    return sorted(albums, key=lambda a: (score(a), a["name"].lower()))


# --- thumbnails ----------------------------------------------------------------------------------
def _thumb_key(*parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def cached_thumbs(key):
    try:
        with open(os.path.join(_cache(), key, "result.json"), encoding="utf-8") as f:
            data = json.load(f)
        if all(os.path.exists(p) for p in data.get("files", [])):
            return data
    except (OSError, ValueError):
        pass
    return None


def load_thumbs(album, start, end, callback, maxn=6, force=False):
    """Thumbnails for an album name, or (album None) for photos taken between start and end."""
    key = _thumb_key(album or "", start.isoformat() if not album else "", end.isoformat() if not album else "",
                     str(maxn))
    data = cached_thumbs(key)
    if data and not force and time.time() - data.get("time", 0) < CACHE_TTL:
        GLib.idle_add(callback, dict(data, ok=True, cached=True))
        return None
    out_dir = os.path.join(_cache(), key)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    if album:
        args = ["--album-thumbs", album]
    else:
        args = ["--range-thumbs", "--from", start.isoformat(), "--to", end.isoformat()]
    args += ["--out-dir", out_dir, "--max", str(maxn)]

    def done(result):
        if result.get("ok"):
            result["time"] = time.time()
            try:
                with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False)
            except OSError:
                pass
        elif data:
            result = dict(data, ok=True, cached=True, stale_error=result)
        callback(result)
    return BridgeCall(args, done)


def forget_thumbs():
    shutil.rmtree(_cache(), ignore_errors=True)


# --- actions -------------------------------------------------------------------------------------
def _spawn(args):
    cmd = command()
    if not cmd:
        return False
    try:
        Gio.Subprocess.new(cmd + args, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
        return True
    except GLib.Error:
        return False


def open_app():
    return _spawn([])


def open_album(name):
    return _spawn(["--open-album", name])


def open_dates(start, end):
    a, b = start.date().isoformat(), end.date().isoformat()
    return _spawn(["--open-date", a if a == b else f"{a}..{b}"])


def create_album(name, start, end, callback, progress=None, allow_empty=False):
    """Create (or reuse) an iCloud album; adds photos taken between start and end when given."""
    args = ["--create-album", name]
    if start is not None and end is not None:
        args += ["--from", start.isoformat(), "--to", end.isoformat()]
    if allow_empty:
        args.append("--allow-empty")
    return BridgeCall(args, callback, progress)
