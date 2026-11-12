#!/usr/bin/env python3
"""Build the import template: templates/skytrack-import.xlsx (+ .ods via LibreOffice, + .csv).

Sheet "Podróże": one row = one trip (there and back, or a single flight when "Data powrotu" is
empty). Country columns have a drop-down; the airport column then offers only airports of that
country (named range K_<ISO code>, INDIRECT). Typing your own value is allowed too (IATA code,
city, "Korfu"…) — SkyTrack resolves it on import.

Usage: python3 tools/build_template.py [pl|en]   (needs python3-openpyxl; LibreOffice for the .ods)
       pl -> templates/skytrack-import.*, en -> templates/skytrack-import-en.*
"""
import csv
import os
import shutil
import subprocess
import sys

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
LANG = (sys.argv[1] if len(sys.argv) > 1 else "pl").lower()
os.environ["SKYTRACK_LANG"] = LANG          # country names in the template's language
from skytrack.airports import CITY_PL, AirportDB, default_path  # noqa: E402

ROWS = 60
OUT_DIR = os.path.join(ROOT, "templates")
HEADERS_PL = [
    ("Kraj wylotu", 18, "Wybierz z listy (domyślnie Polska). Zawęża listę lotnisk w kolumnie obok."),
    ("Skąd", 42, "Lotnisko wylotu z listy — albo wpisz kod (GDN) lub miasto."),
    ("Kraj celu", 18, "Kraj, do którego lecisz. Zawęża listę lotnisk w kolumnie obok."),
    ("Dokąd", 42, "Lotnisko docelowe z listy — albo wpisz kod (KGS), miasto lub wyspę (Korfu, Kreta)."),
    ("Data wylotu", 13, "DD.MM.RRRR, np. 01.09.2026"),
    ("Godzina startu", 11, "HH:MM czasu lokalnego — opcjonalnie"),
    ("Data powrotu", 13, "DD.MM.RRRR — zostaw puste dla lotu w jedną stronę"),
    ("Godzina startu powrotu", 13, "HH:MM czasu lokalnego (na lotnisku docelowym) — opcjonalnie"),
    ("Nr lotu tam", 12, "np. W6 1729 — opcjonalnie"),
    ("Nr lotu powrót", 12, "np. W6 1730 — opcjonalnie"),
    ("Linia lotnicza", 16, "opcjonalnie"),
    ("Notatka", 30, "opcjonalnie"),
]
HEADERS_EN = [
    ("Departure country", 18, "Pick from the list. It narrows the airport list in the next column."),
    ("From", 42, "Departure airport from the list — or type a code (LHR) or a city."),
    ("Destination country", 18, "Country you fly to. It narrows the airport list in the next column."),
    ("To", 42, "Destination airport from the list — or type a code (JFK), a city or an island (Corfu, Crete)."),
    ("Departure date", 13, "e.g. 2026-09-01 (or a date in your spreadsheet's format)"),
    ("Departure time", 11, "HH:MM local time — optional"),
    ("Return date", 13, "Leave empty for a one-way flight"),
    ("Return departure time", 13, "HH:MM local time (at the destination airport) — optional"),
    ("Flight no. out", 12, "e.g. BA 117 — optional"),
    ("Flight no. return", 12, "e.g. BA 112 — optional"),
    ("Airline", 16, "optional"),
    ("Notes", 30, "optional"),
]
EN = LANG == "en"
HEADERS = HEADERS_EN if EN else HEADERS_PL
BASE = "skytrack-import-en" if EN else "skytrack-import"
SHEETS = (("Trips", "How to fill in", "Airports", "Countries") if EN
          else ("Podróże", "Jak wypełnić", "Lotniska", "Kraje"))


def airport_label(ap):
    city = (ap.city if EN else CITY_PL.get(ap.city, ap.city)) or ap.name
    if "(" in city and city.endswith(")"):
        city = city[city.index("(") + 1:-1]
    return f"{ap.iata} – {city}, {ap.name}"


def main():
    db = AirportDB(default_path())
    wb = Workbook()
    # sheets in their final order (LibreOffice ties validations to sheet files by position)
    ws = wb.active
    ws.title = SHEETS[0]
    wi = wb.create_sheet(SHEETS[1])
    ws_a = wb.create_sheet(SHEETS[2])

    # Data sheets ------------------------------------------------------------------------------
    ws_a.append(["Country", "Airport (for the list)", "IATA code", "City", "Name"] if EN else
                ["Kraj", "Lotnisko (do listy)", "Kod IATA", "Miasto", "Nazwa"])
    by_cc = {}
    for ap in db.by_iata.values():
        by_cc.setdefault(ap.cc, []).append(ap)
    countries = sorted(by_cc, key=lambda cc: db.country_name(cc))
    row = 2
    for cc in countries:
        aps = sorted(by_cc[cc], key=lambda a: (-db.popularity.get(a.iata, 0), -a.rank, airport_label(a)))
        first = row
        for ap in aps:
            ws_a.append([db.country_name(cc), airport_label(ap), ap.iata, ap.city, ap.name])
            row += 1
        ref = f"'{SHEETS[2]}'!$B${first}:$B${row - 1}"
        wb.defined_names[f"K_{cc}"] = DefinedName(f"K_{cc}", attr_text=ref)
    for col, w in zip("ABCDE", (22, 52, 9, 22, 50)):
        ws_a.column_dimensions[col].width = w
    ws_a.freeze_panes = "A2"
    for c in ws_a[1]:
        c.font = Font(bold=True)

    ws_k = wb.create_sheet(SHEETS[3])
    ws_k.append(["Country (for the list)" if EN else "Kraj (do listy)"])
    for cc in countries:
        ws_k.append([f"{cc} – {db.country_name(cc)}"])
    ws_k.column_dimensions["A"].width = 40
    n_k = len(countries) + 1
    wb.defined_names["KRAJE"] = DefinedName("KRAJE", attr_text=f"'{SHEETS[3]}'!$A$2:$A${n_k}")

    # Main sheet ---------------------------------------------------------------------------------
    head_fill = PatternFill("solid", fgColor="1C71D8")
    thin = Side(style="thin", color="C0C0C0")
    for i, (title, width, note) in enumerate(HEADERS, start=1):
        c = ws.cell(row=1, column=i, value=title)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head_fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
        c.comment = Comment(note, "SkyTrack")
        ws.column_dimensions[c.column_letter].width = width
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"

    pl = None if EN else next((f"{cc} – {db.country_name(cc)}" for cc in countries if cc == "PL"), None)
    for r in range(2, ROWS + 2):
        if pl:
            ws.cell(row=r, column=1, value=pl)
        for col in (5, 7):
            ws.cell(row=r, column=col).number_format = "YYYY-MM-DD" if EN else "DD.MM.YYYY"
        for col in (6, 8):
            ws.cell(row=r, column=col).number_format = "@"
        for col in range(1, len(HEADERS) + 1):
            ws.cell(row=r, column=col).border = Border(bottom=thin)

    def dv(formula, prompt_title, prompt):
        v = DataValidation(type="list", formula1=formula, allow_blank=True)
        v.showErrorMessage = False          # own text allowed (code / city / island)
        v.showInputMessage = True
        v.promptTitle = prompt_title
        v.prompt = prompt
        ws.add_data_validation(v)
        return v

    last = ROWS + 1
    if EN:
        dv("KRAJE", "Country", "Pick a country from the list").add(f"A2:A{last}")
        dv("KRAJE", "Country", "Pick a country from the list").add(f"C2:C{last}")
        dv('INDIRECT("K_"&LEFT($A2,2))', "From",
           "Airports of the country in column A. You can also type a code, e.g. LHR").add(f"B2:B{last}")
        dv('INDIRECT("K_"&LEFT($C2,2))', "To",
           "Airports of the country in column C. You can also type a code or a name, e.g. JFK, Corfu").add(f"D2:D{last}")
    else:
        dv("KRAJE", "Kraj", "Wybierz kraj z listy").add(f"A2:A{last}")
        dv("KRAJE", "Kraj", "Wybierz kraj z listy").add(f"C2:C{last}")
        dv('INDIRECT("K_"&LEFT($A2,2))', "Skąd",
           "Lotniska z kraju z kolumny A. Możesz też wpisać kod, np. GDN").add(f"B2:B{last}")
        dv('INDIRECT("K_"&LEFT($C2,2))', "Dokąd",
           "Lotniska z kraju z kolumny C. Możesz też wpisać kod lub nazwę, np. KGS, Korfu").add(f"D2:D{last}")
    date_dv = DataValidation(type="date", operator="greaterThan", formula1="18264", allow_blank=True)
    date_dv.showErrorMessage = True
    date_dv.errorTitle = "Date" if EN else "Data"
    date_dv.error = "Type a date, e.g. 2026-09-01" if EN else "Wpisz datę, np. 01.09.2026"
    ws.add_data_validation(date_dv)
    date_dv.add(f"E2:E{last}")
    date_dv.add(f"G2:G{last}")

    # Instructions -------------------------------------------------------------------------------
    lines = [
        ("SkyTrack — szablon importu podróży", True),
        ("", False),
        ("1. Jeden wiersz = jedna podróż. Jeśli wpiszesz „Datę powrotu”, SkyTrack zapisze dwa loty "
         "(wylot i powrót) połączone w jedną podróż. Bez daty powrotu = jeden lot.", False),
        ("2. Kolumna „Kraj wylotu” jest już ustawiona na Polskę. W „Skąd” rozwiń listę i wybierz lotnisko "
         "(lista pokazuje tylko lotniska z wybranego kraju, najważniejsze na górze).", False),
        ("3. W „Kraj celu” wybierz kraj, potem w „Dokąd” lotnisko z listy. Możesz też wpisać sam kod "
         "(KGS, HER) albo nazwę (Korfu, Kreta, Londyn) — SkyTrack to rozpozna.", False),
        ("4. Daty w formacie DD.MM.RRRR. Godziny HH:MM (czas lokalny lotniska startu) są opcjonalne.", False),
        ("5. Zapisz plik (ODS, XLSX albo CSV) i w SkyTrack wybierz Menu → „Importuj podróże z CSV…” "
         "(Ctrl+I) — przyjmuje też pliki .ods i .xlsx.", False),
        ("6. Puste wiersze są pomijane. Podróże, które już są w SkyTrack (ta sama trasa i data), też.", False),
        ("", False),
        ("Przykład (wpisz w arkuszu „Podróże”):", True),
        ("PL – Polska | GDN – Gdańsk, Gdańsk Lech Wałęsa Airport | GR – Grecja | KGS – Kos, Kos Island "
         "International Airport | 01.09.2026 | 06:00 | 08.09.2026 | 12:00", False),
    ]
    if EN:
        lines = [
            ("SkyTrack — trip import template", True),
            ("", False),
            ("1. One row = one trip. If you fill in “Return date”, SkyTrack saves two flights (out and "
             "back) linked as one trip. No return date = a single flight.", False),
            ("2. Pick the “Departure country”, then open the list in “From” and choose the airport "
             "(the list only shows airports of that country, the biggest first).", False),
            ("3. Pick the “Destination country”, then the airport in “To”. You can also just type a code "
             "(JFK, HER) or a name (Corfu, Crete, London) — SkyTrack recognises it.", False),
            ("4. Dates as dates of your spreadsheet (e.g. 2026-09-01). Times HH:MM (local time at the "
             "departure airport) are optional.", False),
            ("5. Save the file (ODS, XLSX or CSV) and in SkyTrack choose Menu → “Import trips "
             "(spreadsheet / CSV)…” (Ctrl+I).", False),
            ("6. Empty rows are skipped, and so are trips already in SkyTrack (same route and date).", False),
            ("", False),
            ("Example (type it in the “Trips” sheet):", True),
            ("GB – United Kingdom | LHR – London, London Heathrow Airport | US – United States | "
             "JFK – New York, John F Kennedy International Airport | 2026-09-01 | 09:00 | 2026-09-08 | 18:30",
             False),
        ]
    for text, bold in lines:
        wi.append([text])
        wi.cell(row=wi.max_row, column=1).font = Font(bold=bold, size=13 if bold else 11)
        wi.cell(row=wi.max_row, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    wi.column_dimensions["A"].width = 120

    os.makedirs(OUT_DIR, exist_ok=True)
    xlsx = os.path.join(OUT_DIR, BASE + ".xlsx")
    wb.save(xlsx)
    print("written", xlsx)

    # CSV (no drop-downs): header + example
    with open(os.path.join(OUT_DIR, BASE + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([h for h, _w, _n in HEADERS])
        if EN:
            w.writerow(["GB", "LHR", "US", "JFK", "2026-09-01", "09:00", "2026-09-08", "18:30",
                        "", "", "", "example — delete this row"])
        else:
            w.writerow(["PL", "GDN", "GR", "KGS", "01.09.2026", "06:00", "08.09.2026", "12:00",
                        "", "", "", "przykład — usuń ten wiersz"])
    print("written", os.path.join(OUT_DIR, BASE + ".csv"))

    # ODS via LibreOffice (keeps lists, named ranges and validation)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "ods", "--outdir", OUT_DIR, xlsx],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("written", os.path.join(OUT_DIR, BASE + ".ods"))
    else:
        print("LibreOffice not found — .ods skipped")


if __name__ == "__main__":
    main()
