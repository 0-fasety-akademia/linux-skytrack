"""CSV import/export of trips.

Import understands:
  * SkyTrack's own CSV (export of this app),
  * myFlightradar24 export ("Date","Flight number","From","To","Dep time",...),
  * Flighty export ("Date","Airline","Flight","From","To", ... ISO times),
  * OpenFlights / generic CSVs with recognisable column names.
Airports may be given as IATA, ICAO, or text containing "(GDN/EPGD)".
"""
import csv
import io
import re

from . import geo
from .db import COLS, Trip
from .i18n import _

IATA_IN_PARENS = re.compile(r"\(([A-Z]{3})(?:/([A-Z]{4}))?\)")
CODE = re.compile(r"\b([A-Z]{3,4})\b")
ISO_DT = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{1,2}:\d{2})")
TIME = re.compile(r"(\d{1,2})[:.](\d{2})")

# canonical field -> candidate column names (lower-case, compared without spaces/_)
ALIASES = {
    "origin": ["origin", "from", "departure", "departureairport", "depairport", "fromairport",
               "skad", "skąd", "wylotz"],
    "dest": ["dest", "destination", "to", "arrival", "arrivalairport", "arrairport", "toairport",
             "dokad", "dokąd"],
    "dep_date": ["depdate", "date", "departuredate", "flightdate", "data", "datawylotu"],
    "dep_time": ["deptime", "departuretime", "std", "scheduleddeparture", "takeoff",
                 "gatedeparture(scheduled)", "gatedeparture(actual)", "godzinawylotu", "godzinastartu"],
    "ret_date": ["datapowrotu", "returndate", "powrot", "powrót"],
    "ret_time": ["godzinastartupowrotu", "godzinapowrotu", "returntime", "returndeparturetime"],
    "ret_flight": ["nrlotupowrót", "nrlotupowrot", "numerlotupowrót", "returnflight", "returnflightno", "flightno.return", "flightnoreturn"],
    "arr_date": ["arrdate", "arrivaldate"],
    "arr_time": ["arrtime", "arrivaltime", "sta", "scheduledarrival", "landing",
                 "gatearrival(scheduled)", "gatearrival(actual)", "godzinaprzylotu"],
    "flight_no": ["flightno", "flightnumber", "flight", "numerlotu", "nrlotutam", "nrlotu", "numerlotutam", "flightno.out", "flightnoout"],
    "airline": ["airline", "carrier", "linia", "linialotnicza"],
    "aircraft": ["aircraft", "aircrafttype", "plane", "equipment", "samolot", "aircrafttypename"],
    "seat": ["seat", "seatnumber", "miejsce"],
    "notes": ["notes", "note", "comment", "comments", "notatka", "notatki"],
    "album": ["album", "icloudalbum", "albumicloud", "photos"],
    "trip_group": ["tripgroup", "podroz", "trip"],
}


def _key(name):
    return re.sub(r"[\s_\-]", "", (name or "").strip().lower())


def _map_columns(header):
    keys = [_key(h) for h in header]
    mapping = {}
    for field, cands in ALIASES.items():
        for c in cands:
            if c in keys:
                mapping[field] = keys.index(c)
                break
    return mapping


def _airport(value, airports):
    v = (value or "").strip()
    if not v:
        return None
    m = IATA_IN_PARENS.search(v.upper())
    if m:
        ap = airports.get(m.group(1)) or (airports.get(m.group(2)) if m.group(2) else None)
        if ap:
            return ap
    ap = airports.get(v)
    if ap:
        return ap
    for code in CODE.findall(v.upper()):
        ap = airports.get(code)
        if ap:
            return ap
    # plain city name ("Gdańsk", "Londyn"): accept the best match when the city matches exactly
    from .airports import _norm, CITY_PL
    hits = airports.search(v, limit=1)
    if hits:
        ap = hits[0]
        if _norm(v) in (_norm(ap.city), _norm(CITY_PL.get(ap.city, ""))):
            return ap
    return None


def _date_time(value):
    v = (value or "").strip()
    m = ISO_DT.match(v)
    if m:
        hh, mm = m.group(2).split(":")
        return m.group(1), f"{int(hh):02d}:{mm}"
    d = geo.parse_date(v.split(" ")[0]) if v else None
    t = ""
    if d and " " in v:
        tm = TIME.search(v.split(" ", 1)[1])
        if tm:
            t = f"{int(tm.group(1)):02d}:{tm.group(2)}"
    return d, t


def _time(value):
    v = (value or "").strip()
    if not v:
        return "", None
    m = ISO_DT.match(v)
    if m:
        hh, mm = m.group(2).split(":")
        return f"{int(hh):02d}:{mm}", m.group(1)
    tm = TIME.search(v)
    if tm and int(tm.group(1)) < 24:
        return f"{int(tm.group(1)):02d}:{tm.group(2)}", None
    return "", None


def parse_csv(text, airports):
    """Return (trips, problems) where problems is a list of 'line N: reason'."""
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    return parse_rows(rows, airports)


def parse_rows(rows, airports):
    """Like parse_csv, for rows already split into cells (lists of strings)."""
    rows = [[("" if c is None else str(c)) for c in r] for r in rows]
    if not rows:
        return [], [_('plik jest pusty')]
    mapping = _map_columns(rows[0])
    missing = [f for f in ("origin", "dest", "dep_date") if f not in mapping]
    if missing:
        names = {"origin": _('skąd/from'), "dest": _('dokąd/to'), "dep_date": "data/date"}
        return [], [_('brak kolumn: ') + ", ".join(names[m] for m in missing)]

    def cell(row, field):
        i = mapping.get(field)
        return row[i].strip() if i is not None and i < len(row) else ""

    trips, problems = [], []
    for n, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        if not (cell(row, "origin") or cell(row, "dest") or cell(row, "dep_date")):
            continue            # e.g. template rows with only the country filled in
        if cell(row, "notes").lower().startswith(("przykład", "example")):
            continue            # the template's example row
        a, b = _airport(cell(row, "origin"), airports), _airport(cell(row, "dest"), airports)
        dep_date, dep_time = _date_time(cell(row, "dep_date"))
        if not a or not b:
            problems.append(_('wiersz {0}: nieznane lotnisko ({1})').format(n, cell(row, 'origin') if not a else cell(row, 'dest')))
            continue
        if not dep_date:
            problems.append(_('wiersz {0}: nieczytelna data ({1})').format(n, cell(row, 'dep_date')))
            continue
        t, d_from_time = _time(cell(row, "dep_time"))
        if t:
            dep_time = t
            dep_date = d_from_time or dep_date
        arr_time, arr_date_from_time = _time(cell(row, "arr_time"))
        arr_date = ""
        if arr_time:
            arr_date = arr_date_from_time or (_date_time(cell(row, "arr_date"))[0]) or dep_date
            # overnight flight written without an arrival date
            if not arr_date_from_time and not cell(row, "arr_date") and dep_time and \
                    geo.real_minutes(dep_date, dep_time, a.tz, arr_date, arr_time, b.tz) is None:
                from datetime import date, timedelta
                nxt = (date.fromisoformat(dep_date) + timedelta(days=1)).isoformat()
                if geo.real_minutes(dep_date, dep_time, a.tz, nxt, arr_time, b.tz) is not None:
                    arr_date = nxt
            if not dep_time or geo.real_minutes(dep_date, dep_time, a.tz, arr_date, arr_time, b.tz) is None:
                arr_date, arr_time = "", ""
        ret_date = _date_time(cell(row, "ret_date"))[0] if cell(row, "ret_date") else None
        if cell(row, "ret_date") and not ret_date:
            problems.append(_('wiersz {0}: nieczytelna data powrotu ({1})').format(n, cell(row, 'ret_date')))
            continue
        if ret_date and ret_date < dep_date:
            problems.append(_('wiersz {0}: powrót ({1}) przed wylotem').format(n, cell(row, 'ret_date')))
            continue
        flight_no = re.sub(r"\s+", " ", cell(row, "flight_no").upper())
        if flight_no.isdigit() and re.fullmatch(r"[A-Z0-9]{2,3}", cell(row, "airline").upper()):
            flight_no = f"{cell(row, 'airline').upper()} {flight_no}"     # Flighty: BAW + 117
        trips.append(Trip(origin=a.iata, dest=b.iata, dep_date=dep_date, dep_time=dep_time,
                          arr_date=arr_date, arr_time=arr_time,
                          flight_no=flight_no,
                          airline=cell(row, "airline"), aircraft=cell(row, "aircraft"),
                          seat=cell(row, "seat").upper(), notes=cell(row, "notes"),
                          album=cell(row, "album"), trip_group=cell(row, "trip_group")))
        if ret_date:
            import uuid
            group = trips[-1].trip_group or uuid.uuid4().hex[:12]
            trips[-1].trip_group = group
            ret_time, _d = _time(cell(row, "ret_time"))
            trips.append(Trip(origin=b.iata, dest=a.iata, dep_date=ret_date, dep_time=ret_time,
                              flight_no=re.sub(r"\s+", " ", cell(row, "ret_flight").upper()),
                              airline=cell(row, "airline"), aircraft=cell(row, "aircraft"),
                              notes=cell(row, "notes"), album=cell(row, "album"), trip_group=group))
    return trips, problems


def export_csv(trips):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLS)
    for t in sorted(trips, key=lambda t: (t.dep_date, t.dep_time)):
        w.writerow([getattr(t, c) or "" for c in COLS])
    return buf.getvalue()


def is_duplicate(trip, existing):
    return any(e.origin == trip.origin and e.dest == trip.dest and e.dep_date == trip.dep_date
               for e in existing)


SPREADSHEET_EXT = (".ods", ".xlsx")


def _cell_text(v):
    import datetime as _dt
    if isinstance(v, _dt.datetime):
        return v.strftime("%Y-%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, _dt.time):
        return v.strftime("%H:%M")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return "" if v is None else str(v).strip()


def read_ods(data):
    """First sheet of an .ods file (bytes) as a list of rows of strings. Pure Python."""
    import zipfile
    import xml.etree.ElementTree as ET
    ns = {"table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
          "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
          "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
    T, O = "{%s}" % ns["table"], "{%s}" % ns["office"]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("content.xml"))
    sheet = root.find(".//table:table", ns)
    if sheet is None:
        return []
    rows = []
    for tr in sheet.iter(T + "table-row"):
        rep_rows = min(int(tr.get(T + "number-rows-repeated", "1")), 500)
        cells = []
        for tc in tr:
            if tc.tag not in (T + "table-cell", T + "covered-table-cell"):
                continue
            rep = min(int(tc.get(T + "number-columns-repeated", "1")), 64)
            vt = tc.get(O + "value-type")
            if vt == "date":
                v = tc.get(O + "date-value", "")
                v = v.replace("T", " ")[:16] if "T" in v and not v.endswith("T00:00:00") else v[:10]
            elif vt == "time":
                m = re.match(r"PT(\d+)H(\d+)M", tc.get(O + "time-value", ""))
                v = f"{int(m.group(1)) % 24:02d}:{m.group(2)}" if m else ""
            elif vt in ("float", "percentage", "currency"):
                v = _cell_text(float(tc.get(O + "value", "0")))
            else:
                v = "\n".join("".join(p.itertext()) for p in tc.findall("text:p", ns)).strip()
            cells.extend([v] * rep)
        while cells and not cells[-1]:
            cells.pop()
        rows.extend([cells] * (rep_rows if cells else min(rep_rows, 1)))
    while rows and not any(rows[-1]):
        rows.pop()
    return rows


def read_xlsx(data):
    """First sheet of an .xlsx file (bytes) as rows of strings (needs python3-openpyxl)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = [[_cell_text(v) for v in r] for r in ws.iter_rows(values_only=True)]
    while rows and not any(rows[-1]):
        rows.pop()
    return rows


def parse_file(name, data, airports):
    """Dispatch on file extension: .ods / .xlsx / anything else as CSV text."""
    low = name.lower()
    if low.endswith(".ods"):
        return parse_rows(read_ods(data), airports)
    if low.endswith(".xlsx"):
        try:
            return parse_rows(read_xlsx(data), airports)
        except ImportError:
            return [], [_('do plików .xlsx potrzebny jest pakiet python3-openpyxl (sudo apt install python3-openpyxl) — albo zapisz arkusz jako .ods lub .csv')]
    text = None
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            text = bytes(data).decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return parse_csv(text or "", airports)

