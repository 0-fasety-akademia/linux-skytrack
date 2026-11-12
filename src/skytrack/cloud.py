"""Optional copy of the backup in the cloud: Google Drive and iCloud Drive.

* Google Drive (or any other folder): through GIO. With a Google account added in Ubuntu's
  Settings → Online Accounts (with "Files" on), Google Drive is a gvfs location
  (google-drive://you@gmail.com/). Any other folder works too, e.g. one synced by another app.
* iCloud Drive: through Linux iCloud Photos 0.16.0+ (`--drive-upload`, the same saved session).

The cloud keeps the newest `keep` backups named skytrack-kopia-*.skytrack (one a day: a second
upload on the same day replaces the first). Other files in the folder are never touched.
"""
import os
import tempfile
import threading
from datetime import date, datetime

from gi.repository import Gio, GLib

from . import backup, photos
from .i18n import IS_PL, _

PREFIX = "skytrack-kopia-" if IS_PL else "skytrack-backup-"
PREFIXES = ("skytrack-kopia-", "skytrack-backup-")
FOLDER = "SkyTrack"
DEFAULT_KEEP = 10
ICLOUD_MIN = (0, 16, 0)


def file_name(day=None):
    return f"{PREFIX}{(day or date.today()).isoformat()}{backup.EXT}"


# ---- targets ------------------------------------------------------------------------------------
def google_accounts():
    """[(label, root uri)] of Google Drive locations from Online Accounts (mounted or not)."""
    out, seen = [], set()
    mon = Gio.VolumeMonitor.get()
    for m in mon.get_mounts():
        uri = m.get_root().get_uri()
        if uri.startswith("google-drive://") and uri not in seen:
            seen.add(uri)
            out.append((m.get_name(), uri))
    for v in mon.get_volumes():
        act = v.get_activation_root()
        uri = act.get_uri() if act else ""
        if uri.startswith("google-drive://") and uri not in seen:
            seen.add(uri)
            out.append((v.get_name(), uri))
    return out


def icloud_state():
    """'ok', 'old' (every installed Linux iCloud Photos is too old) or 'missing'."""
    inst = photos.installations()
    if not inst:
        return "missing"
    if all(v is not None and v < ICLOUD_MIN for _c, v, _l in inst):
        return "old"
    return "ok"


def describe_uri(uri):
    if not uri:
        return ""
    if uri.startswith("google-drive://"):
        account = uri[len("google-drive://"):].split("/", 1)[0]
        return _('Dysk Google ({0}) / {1}').format(account, FOLDER)
    f = Gio.File.new_for_uri(uri)
    return f.get_path() or f.get_parse_name()


# ---- Google Drive / folder via GIO -----------------------------------------------------------------
def _mount_if_needed(root):
    """Mount a gvfs location (Google Drive from Online Accounts) synchronously from a thread."""
    try:
        root.query_info("standard::type", Gio.FileQueryInfoFlags.NONE, None)
        return
    except GLib.Error as e:
        if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_MOUNTED):
            raise
    done = threading.Event()
    err = []

    def mounted(f, res):
        try:
            f.mount_enclosing_volume_finish(res)
        except GLib.Error as ex:
            if not ex.matches(Gio.io_error_quark(), Gio.IOErrorEnum.ALREADY_MOUNTED):
                err.append(ex)
        done.set()
    GLib.idle_add(lambda: (root.mount_enclosing_volume(Gio.MountMountFlags.NONE, None, None, mounted), False)[1])
    done.wait(60)
    if err:
        raise err[0]


def _children(folder):
    out = []
    en = folder.enumerate_children("standard::name,standard::display-name,standard::type,time::modified",
                                   Gio.FileQueryInfoFlags.NONE, None)
    for info in en:
        out.append((info, folder.get_child(info.get_name())))
    en.close(None)
    return out


def _subfolder(root, name):
    """The child folder shown as `name` (Google Drive names files by id), created when missing."""
    for info, f in _children(root):
        if info.get_file_type() == Gio.FileType.DIRECTORY and info.get_display_name() == name:
            return f
    child = root.get_child_for_display_name(name)
    try:
        child.make_directory(None)
    except GLib.Error as e:
        if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.EXISTS):
            raise
    for info, f in _children(root):          # Google Drive: re-read to get the id-based path
        if info.get_file_type() == Gio.FileType.DIRECTORY and info.get_display_name() == name:
            return f
    return child


def upload_gio(uri, src_path, keep=DEFAULT_KEEP):
    """Copy src_path into the folder at uri (Google Drive root → its SkyTrack folder).
    Returns {'ok', 'where', 'removed'} — blocking, run it in a thread."""
    root = Gio.File.new_for_uri(uri)
    _mount_if_needed(root)
    folder = _subfolder(root, FOLDER) if uri.startswith("google-drive://") else root
    name = os.path.basename(src_path)
    for info, f in _children(folder):
        if info.get_display_name() == name and info.get_file_type() == Gio.FileType.REGULAR:
            f.delete(None)
    dest = folder.get_child_for_display_name(name)
    Gio.File.new_for_path(src_path).copy(dest, Gio.FileCopyFlags.OVERWRITE, None, None, None)
    removed = []
    if keep > 0:
        files = [(info, f) for info, f in _children(folder)
                 if info.get_file_type() == Gio.FileType.REGULAR
                 and info.get_display_name().startswith(PREFIXES)
                 and info.get_display_name().endswith(backup.EXT)
                 and info.get_display_name() != name]
        files.sort(key=lambda x: (x[0].get_modification_date_time().to_unix()
                                  if x[0].get_modification_date_time() else 0, x[0].get_display_name()),
                   reverse=True)
        for info, f in files[max(0, keep - 1):]:
            try:
                f.delete(None)
                removed.append(info.get_display_name())
            except GLib.Error:
                pass
    return {"ok": True, "where": describe_uri(uri), "removed": removed}


# ---- one run over all enabled targets -----------------------------------------------------------
def enabled(settings):
    return bool(settings["cloud_gdrive_uri"]) or bool(settings["cloud_icloud"])


def run(store, settings, callback):
    """Write today's backup to a temp file and send it to every enabled target.
    callback({'gdrive': result|None, 'icloud': result|None}) on the main thread."""
    tmpdir = tempfile.mkdtemp(prefix="skytrack-cloud-", dir=photos.work_dir())
    path = os.path.join(tmpdir, file_name())
    try:
        backup.create(store, path, include_auth=True, kind="cloud")
    except Exception as e:  # noqa: BLE001
        GLib.idle_add(callback, {"error": str(e)})
        return
    keep = int(settings["cloud_keep"] or DEFAULT_KEEP)
    results = {"gdrive": None, "icloud": None}
    pending = []

    def finish():
        for f in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, f))
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
        now = datetime.now().isoformat(timespec="minutes")
        last = dict(settings["cloud_last"] or {})
        for k, r in results.items():
            if r is not None:
                last[k] = {"ok": bool(r.get("ok")), "when": now, "msg": r.get("message", "")}
        settings["cloud_last"] = last
        callback(results)

    def one_done():
        pending.pop()
        if not pending:
            finish()

    uri = settings["cloud_gdrive_uri"]
    if uri:
        pending.append("gdrive")

        def work():
            try:
                r = upload_gio(uri, path, keep)
            except GLib.Error as e:
                r = {"ok": False, "message": e.message}
            except Exception as e:  # noqa: BLE001
                r = {"ok": False, "message": str(e)}
            results["gdrive"] = r
            GLib.idle_add(lambda: (one_done(), False)[1])
        threading.Thread(target=work, daemon=True).start()
    if settings["cloud_icloud"]:
        pending.append("icloud")

        def icloud_done(result):
            if not result.get("ok"):
                code = result.get("error")
                if code == "drive_unavailable":
                    result["message"] = _('iCloud Drive jest niedostępny (wyłączony albo włączona Zaawansowana '
                                          'ochrona danych bez dostępu przez www).')
                elif code == "bad_option":
                    result["message"] = _('Potrzebny Linux iCloud Photos 0.16.0 lub nowszy.')
                else:
                    result["message"] = photos.error_text(result)
            results["icloud"] = result
            one_done()
        photos.BridgeCall(["--drive-upload", path, "--drive-folder", FOLDER, "--prefix", PREFIX,
                           "--keep", str(keep)], icloud_done, min_version=ICLOUD_MIN)
    if not pending:
        finish()


def auto_if_due(store, settings, callback=None):
    """After the weekly automatic backup: send it to the cloud too (once a week)."""
    if not enabled(settings):
        return False
    last = settings["cloud_last_auto"] or ""
    today = date.today()
    try:
        if last and (today - date.fromisoformat(last)).days < backup.AUTO_EVERY_DAYS:
            return False
    except ValueError:
        pass
    settings["cloud_last_auto"] = today.isoformat()
    run(store, settings, callback or (lambda _r: None))
    return True
