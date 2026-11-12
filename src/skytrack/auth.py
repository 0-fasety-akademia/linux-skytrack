"""App login: one local account (login + password), stored as a salted PBKDF2-SHA256 hash.

The password itself is never saved. File: ~/.config/linux-skytrack/auth.json (mode 600).
Forgotten password: optional hint (shown after a wrong attempt), or reset after
authenticating as an Ubuntu administrator (polkit / pkexec, see reset_with_system_auth).
Trips are never deleted by a reset.
"""
import hashlib
import hmac
import json
import os
import secrets
import time

from . import db
from .i18n import _

ITERATIONS = 310_000
MIN_PASSWORD = 6


def _path():
    return os.path.join(db.config_dir(), "auth.json")


def _hash(password, salt, iterations=ITERATIONS):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def _norm_login(login):
    return (login or "").strip().lower()


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        if data.get("login") and data.get("hash") and data.get("salt"):
            return data
    except (OSError, ValueError):
        pass
    return None


def has_account():
    return load() is not None


def account_login():
    data = load()
    return data.get("display_login", data["login"]) if data else ""


def hint():
    data = load()
    return (data or {}).get("hint", "")


def validate_new(login, password, repeat, hint_text=""):
    """Error message (Polish) or None."""
    if len(_norm_login(login)) < 2:
        return _('Login musi mieć co najmniej 2 znaki')
    if len(password) < MIN_PASSWORD:
        return _('Hasło musi mieć co najmniej {0} znaków').format(MIN_PASSWORD)
    if password != repeat:
        return _('Hasła się różnią')
    if hint_text and password.lower() in hint_text.lower():
        return _('Podpowiedź nie może zawierać hasła')
    if len(hint_text) > 120:
        return _('Podpowiedź może mieć najwyżej 120 znaków')
    return None


def save(login, password, hint_text=""):
    salt = secrets.token_bytes(16)
    data = {"version": 1, "algo": "pbkdf2_sha256", "iterations": ITERATIONS,
            "login": _norm_login(login), "display_login": login.strip(),
            "salt": salt.hex(), "hash": _hash(password, salt), "hint": hint_text.strip(),
            "created": int(time.time())}
    path = _path()
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def verify(login, password):
    data = load()
    if not data:
        return False
    try:
        expected = data["hash"]
        got = _hash(password, bytes.fromhex(data["salt"]), int(data.get("iterations", ITERATIONS)))
    except (ValueError, KeyError):
        return False
    login_ok = hmac.compare_digest(_norm_login(login), data["login"])
    pass_ok = hmac.compare_digest(got, expected)
    return login_ok and pass_ok


# --- reset with the Ubuntu administrator password (polkit) ------------------------------------
HELPER = "/usr/lib/linux-skytrack/confirm-admin"     # does nothing; pkexec only asks for the password
POLKIT_ACTION = "com.jgu.LinuxSkyTrack.reset-password"


def system_auth_command():
    """argv that makes polkit ask for an administrator password, or None without pkexec."""
    import shutil
    pkexec = shutil.which("pkexec")
    if not pkexec:
        return None
    if os.path.exists(HELPER):                # installed: our policy gives a clear message
        return [pkexec, HELPER]
    return [pkexec, "/usr/bin/true"]          # running from the source tree


def system_auth_result(exit_status):
    """'ok', 'cancelled' (dialog dismissed) or 'denied' (wrong password / not an admin / error)."""
    if exit_status == 0:
        return "ok"
    if exit_status == 126:
        return "cancelled"
    return "denied"


class Throttle:
    """After 5 wrong attempts: wait 30 s, then double the wait after each further failure."""

    def __init__(self):
        self.failures = 0
        self.until = 0.0

    def wait_left(self):
        return max(0, int(self.until - time.monotonic() + 0.999))

    def failed(self):
        self.failures += 1
        if self.failures >= 5:
            self.until = time.monotonic() + 30 * 2 ** (self.failures - 5)

    def ok(self):
        self.failures = 0
        self.until = 0.0
