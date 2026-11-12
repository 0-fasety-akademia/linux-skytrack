"""Backup and restore: one .skytrack file (a zip) with the trips database, settings and the
login (password hash only — never the password itself).

Layout of the zip:
    manifest.json   {"app": "linux-skytrack", "format": 1, "version", "created", "trips", "auth"}
    skytrack.db     consistent copy made with SQLite's online backup API
    settings.json   app settings (window size is not restored)
    auth.json       optional: login + PBKDF2 hash + hint
"""
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime, timedelta

from . import db
from .version import VERSION

EXT = ".skytrack"
FORMAT = 1
AUTO_KEEP = 5
AUTO_EVERY_DAYS = 7
NOT_RESTORED = ("width", "height", "sidebar")


class BackupError(Exception):
    pass


def backups_dir():
    d = os.path.join(db.data_dir(), "backups")
    os.makedirs(d, exist_ok=True)
    return d


def _auth_path():
    return os.path.join(db.config_dir(), "auth.json")


def _settings_path():
    return os.path.join(db.config_dir(), "settings.json")


def create(store, dest, include_auth=True, kind="manual"):
    """Write a backup of the open TripStore to dest. Returns the manifest."""
    tmp = tempfile.mkdtemp(prefix="skytrack-backup-")
    try:
        db_copy = os.path.join(tmp, "skytrack.db")
        out = sqlite3.connect(db_copy)
        with out:
            store.conn.backup(out)
        trips = out.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
        out.close()
        has_auth = include_auth and os.path.exists(_auth_path())
        manifest = {"app": "linux-skytrack", "format": FORMAT, "version": VERSION,
                    "created": datetime.now().isoformat(timespec="seconds"),
                    "trips": trips, "auth": has_auth, "kind": kind}
        part = dest + ".part"
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.write(db_copy, "skytrack.db")
            if os.path.exists(_settings_path()):
                z.write(_settings_path(), "settings.json")
            if has_auth:
                z.write(_auth_path(), "auth.json")
        os.replace(part, dest)
        try:
            os.chmod(dest, 0o600)       # contains the password hash
        except OSError:
            pass
        return manifest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def inspect(path):
    """Manifest of a backup file; raises BackupError when it is not a SkyTrack backup."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "manifest.json" not in names or "skytrack.db" not in names:
                raise BackupError("missing")
            manifest = json.loads(z.read("manifest.json"))
    except (zipfile.BadZipFile, OSError, ValueError, KeyError) as e:
        raise BackupError(str(e)) from e
    if manifest.get("app") != "linux-skytrack":
        raise BackupError("not skytrack")
    if int(manifest.get("format", 0)) > FORMAT:
        raise BackupError("newer")
    manifest["auth"] = bool(manifest.get("auth")) and "auth.json" in names
    return manifest


def restore(store, path, settings, include_auth=True):
    """Replace trips (and settings, optionally the login) with the backup. A safety copy of the
    current state is written to backups/ first. Returns (manifest, safety_copy_path)."""
    manifest = inspect(path)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safety = os.path.join(backups_dir(), f"przed-przywroceniem_{stamp}{EXT}")
    create(store, safety, include_auth=True, kind="safety")
    tmp = tempfile.mkdtemp(prefix="skytrack-restore-")
    try:
        with zipfile.ZipFile(path) as z:
            z.extract("skytrack.db", tmp)
            src = sqlite3.connect(os.path.join(tmp, "skytrack.db"))
            try:
                src.execute("SELECT origin, dest, dep_date FROM trips LIMIT 1")
            except sqlite3.DatabaseError as e:
                src.close()
                raise BackupError(str(e)) from e
            with src:
                src.backup(store.conn)          # replaces the live database in place
            src.close()
            store.migrate()
            if "settings.json" in z.namelist():
                try:
                    data = json.loads(z.read("settings.json"))
                except ValueError:
                    data = {}
                for k, v in data.items():
                    if k not in NOT_RESTORED:
                        settings.data[k] = v
                settings.save()
            if include_auth and manifest["auth"]:
                part = _auth_path() + ".part"
                with open(part, "wb") as f:
                    f.write(z.read("auth.json"))
                os.chmod(part, 0o600)
                os.replace(part, _auth_path())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return manifest, safety


def list_backups():
    """[(path, manifest)] of backups in backups/, newest first."""
    out = []
    d = backups_dir()
    for name in os.listdir(d):
        if not name.endswith(EXT):
            continue
        p = os.path.join(d, name)
        try:
            out.append((p, inspect(p)))
        except BackupError:
            continue
    out.sort(key=lambda x: x[1].get("created", ""), reverse=True)
    return out


def auto_backup_if_due(store, settings):
    """Weekly automatic backup into backups/ (keeps the last AUTO_KEEP). Returns path or None."""
    if not settings["auto_backup"]:
        return None
    last = settings["last_auto_backup"] or ""
    today = date.today()
    try:
        if last and date.fromisoformat(last) > today - timedelta(days=AUTO_EVERY_DAYS):
            return None
    except ValueError:
        pass
    if not store.all():
        return None
    path = os.path.join(backups_dir(), f"auto_{today.isoformat()}{EXT}")
    create(store, path, include_auth=True, kind="auto")
    settings["last_auto_backup"] = today.isoformat()
    autos = [p for p, m in list_backups() if m.get("kind") == "auto"]
    for old in autos[AUTO_KEEP:]:
        try:
            os.remove(old)
        except OSError:
            pass
    return path
