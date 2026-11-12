"""Interface language: Polish when it is the system language, English otherwise.

Polish is the source language — texts are written in Polish in the code and wrapped in _().
In English mode _() looks the text up in i18n_en.EN (missing entries fall back to Polish).
Force a language with SKYTRACK_LANG=pl or SKYTRACK_LANG=en.
"""
import os


def _detect():
    forced = os.environ.get("SKYTRACK_LANG", "").strip().lower()
    if forced[:2] in ("pl", "en"):
        return forced[:2]
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "")
        if not val:
            continue
        first = val.split(":")[0].strip().lower()
        if not first:
            continue
        return "pl" if first.startswith("pl") else "en"
    return "en"


LANG = _detect()
IS_PL = LANG == "pl"

if IS_PL:
    _TABLE = {}
else:
    from .i18n_en import EN as _TABLE


def _(text):
    return _TABLE.get(text, text) if _TABLE else text


def plural(n, one, few, many, en_one=None, en_many=None):
    """Polish plural (1 lot, 2 loty, 5 lotów); English one/many when not Polish."""
    if not IS_PL:
        return en_one if n == 1 else en_many
    if n == 1:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many
