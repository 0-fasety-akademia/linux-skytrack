#!/usr/bin/env python3
"""Post-process the template in LibreOffice (python3-uno): set the dependent airport lists
with the right anchor sheet (openpyxl → LibreOffice puts it on the wrong sheet), then save
templates/skytrack-import.ods and .xlsx.

Usage: soffice --headless --accept="socket,host=localhost,port=2002;urp;" &
       python3 tools/fix_template_lo.py templates/skytrack-import.xlsx
       python3 tools/fix_template_lo.py templates/skytrack-import-en.xlsx
"""
import os
import sys

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.table import CellAddress


def prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def main(src):
    src = os.path.abspath(src)
    out_dir = os.path.dirname(src)
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    ctx = resolver.resolve("uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(src), "_blank", 0, (prop("Hidden", True),))
    sheets = doc.Sheets
    en = src.endswith("-en.xlsx")
    main_name, countries_name = ("Trips", "Countries") if en else ("Podróże", "Kraje")
    sh = sheets.getByName(main_name)
    sheet_idx = [sheets.getByIndex(i).Name for i in range(sheets.Count)].index(main_name)
    LIST = uno.Enum("com.sun.star.sheet.ValidationType", "LIST")
    rows = 61
    texts = ((1, "A", "B", "From", "Airports of the country in column A (biggest first). You can also type a code, e.g. LHR."),
             (3, "C", "D", "To", "Airports of the country in column C. You can also type a code or a name, e.g. JFK, Corfu.")) if en else (
            (1, "A", "B", "Skąd", "Lotniska z kraju z kolumny A (najważniejsze na górze). Możesz też wpisać kod, np. GDN."),
            (3, "C", "D", "Dokąd", "Lotniska z kraju z kolumny C. Możesz też wpisać kod lub nazwę, np. KGS, Korfu."))
    for col, country_col, letter, title, msg in texts:
        rng = sh.getCellRangeByName(f"{letter}2:{letter}{rows}")
        v = rng.Validation
        v.Type = LIST
        v.setFormula1(f'INDIRECT("K_"&LEFT(${country_col}2;2))')
        v.setSourcePosition(CellAddress(sheet_idx, col, 1))
        v.ShowErrorMessage = False
        v.ShowInputMessage = True
        v.InputTitle = title
        v.InputMessage = msg
        v.ShowList = 1
        v.IgnoreBlankCells = True
        rng.Validation = v
    for col, letter in ((0, "A"), (2, "C")):
        rng = sh.getCellRangeByName(f"{letter}2:{letter}{rows}")
        v = rng.Validation
        v.Type = LIST
        v.setFormula1("KRAJE")
        v.setSourcePosition(CellAddress(sheet_idx, col, 1))
        v.ShowErrorMessage = False
        v.ShowInputMessage = True
        v.InputTitle = "Country" if en else "Kraj"
        v.InputMessage = "Pick a country from the list" if en else "Wybierz kraj z listy"
        v.ShowList = 1
        rng.Validation = v
    sheets.getByName(countries_name).IsVisible = False
    doc.CurrentController.setActiveSheet(sh)
    base = src[:-len(".xlsx")]
    doc.storeToURL(uno.systemPathToFileUrl(base + ".ods"), (prop("FilterName", "calc8"),))
    doc.storeToURL(uno.systemPathToFileUrl(base + ".xlsx"), (prop("FilterName", "Calc MS Excel 2007 XML"),))
    # check: anchors and the list behind B2/D2
    for addr in ("B2", "B30", "D2"):
        v = sh.getCellRangeByName(addr).Validation
        print(addr, v.getFormula1(), "sheet", v.getSourcePosition().Sheet)
    doc.close(True)


if __name__ == "__main__":
    main(sys.argv[1])
