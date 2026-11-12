"""SQLite storage for trips and small JSON settings."""
import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict

from gi.repository import GLib

APP_DIR = "linux-skytrack"


def data_dir():
    d = os.path.join(GLib.get_user_data_dir(), APP_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def config_dir():
    d = os.path.join(GLib.get_user_config_dir(), APP_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def cache_dir():
    d = os.path.join(GLib.get_user_cache_dir(), APP_DIR)
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class Trip:
    origin: str
    dest: str
    dep_date: str               # YYYY-MM-DD, local at origin
    dep_time: str = ""          # HH:MM local at origin (optional)
    arr_date: str = ""          # YYYY-MM-DD local at destination (optional)
    arr_time: str = ""          # HH:MM local at destination (optional)
    flight_no: str = ""
    airline: str = ""
    aircraft: str = ""
    seat: str = ""
    notes: str = ""
    album: str = ""             # linked iCloud album (linux-icloud-photos)
    trip_group: str = ""        # same value for the outbound and return flight of one trip
    id: int | None = field(default=None)


SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT NOT NULL,
    dest TEXT NOT NULL,
    dep_date TEXT NOT NULL,
    dep_time TEXT DEFAULT '',
    arr_date TEXT DEFAULT '',
    arr_time TEXT DEFAULT '',
    flight_no TEXT DEFAULT '',
    airline TEXT DEFAULT '',
    aircraft TEXT DEFAULT '',
    seat TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS trips_dep ON trips(dep_date);
"""

COLS = ["origin", "dest", "dep_date", "dep_time", "arr_date", "arr_time",
        "flight_no", "airline", "aircraft", "seat", "notes", "album", "trip_group"]


class TripStore:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "skytrack.db")
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.migrate()

    def migrate(self):
        """Create / upgrade the schema (also after restoring an older backup)."""
        self.conn.executescript(SCHEMA)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(trips)")}
        if "album" not in cols:                       # 0.3.0: linked iCloud album
            self.conn.execute("ALTER TABLE trips ADD COLUMN album TEXT DEFAULT ''")
        if "trip_group" not in cols:                  # 0.7.0: there-and-back trips
            self.conn.execute("ALTER TABLE trips ADD COLUMN trip_group TEXT DEFAULT ''")
        self.conn.commit()

    def all(self):
        rows = self.conn.execute(
            "SELECT * FROM trips ORDER BY dep_date DESC, dep_time DESC, id DESC").fetchall()
        return [Trip(**{c: (r[c] or "") for c in COLS}, id=r["id"]) for r in rows]

    def save(self, trip):
        vals = [getattr(trip, c) or "" for c in COLS]
        if trip.id is None:
            cur = self.conn.execute(
                f"INSERT INTO trips ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})", vals)
            trip.id = cur.lastrowid
        else:
            self.conn.execute(
                f"UPDATE trips SET {','.join(c + '=?' for c in COLS)} WHERE id=?", vals + [trip.id])
        self.conn.commit()
        return trip

    def delete(self, trip_id):
        self.conn.execute("DELETE FROM trips WHERE id=?", (trip_id,))
        self.conn.commit()


class Settings:
    DEFAULTS = {"map_layer": "map", "width": 1320, "height": 860,
                "sidebar": 400, "theme": "system", "notified": [],
                "home_country": "", "auto_backup": True, "last_auto_backup": "",
                "live_auto": True, "live_interval": 30, "live_traffic": True,
                "cloud_gdrive_uri": "", "cloud_icloud": False, "cloud_keep": 10, "cloud_last": {},
                "cloud_last_auto": "",
                "atc_source": "", "atc_custom": [], "atc_all_eu": False, "atc_collapsed": False}

    def __init__(self):
        self.path = os.path.join(config_dir(), "settings.json")
        self.data = dict(self.DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def __getitem__(self, k):
        return self.data.get(k, self.DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.data[k] = v
        self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except OSError:
            pass
