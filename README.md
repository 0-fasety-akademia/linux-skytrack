# SkyTrack (linux-skytrack)

Dziennik lotów dla Ubuntu: zapisujesz swoje podróże samolotem, widzisz je na mapie (zwykłej lub satelitarnej) z pinezkami na odwiedzonych lotniskach. Kilometry odbytych lotów i statystyki rok / miesiąc / dzień liczą się same.

Część serii **JGu Linux Apps**. Created by: JGu · Supported by Claude.

![icon](icons/hicolor/scalable/apps/linux-skytrack.svg)

## Co nowego w 0.10.0: wersja angielska / English version

- Gdy język systemu **nie jest polski**, SkyTrack działa po angielsku: menu, okna, komunikaty, statystyki, mapa (Map / Satellite), daty („Mon, 1 Sep 2025”), nazwy krajów i liczby („8,486 km”). Przy polskim systemie wszystko zostaje jak było.
- Wymuszenie języka: `SKYTRACK_LANG=en linux-skytrack` albo `SKYTRACK_LANG=pl linux-skytrack`.
- Angielski szablon importu: **Menu → Save import template…** zapisuje `skytrack-import-en.ods` (kolumny From / To / Departure date / Return date…). Import rozpoznaje oba szablony.
- Kraj zamieszkania przy angielskim systemie: najpierw region formatów (Ubuntu: Ustawienia → Region i język → Formaty), potem lotnisko pierwszego lotu — `en_US` nie oznacza już automatycznie USA. Zawsze można go zmienić w Statystykach („I live in:”).

**English:** SkyTrack switches to English automatically when the system language is not Polish. Force a language with `SKYTRACK_LANG=en` or `SKYTRACK_LANG=pl`. The English import template is available from Menu → Save import template… (`skytrack-import-en.ods`, drop-down lists of countries and airports).

## Co nowego w 0.9.0: szablon importu z listami wyboru

- **Menu → Zapisz szablon importu…** zapisuje arkusz `skytrack-import.ods` (LibreOffice Calc). Jeden wiersz = jedna podróż, od 1 do kilkudziesięciu wpisów naraz.
- **Listy rozwijane:** najpierw wybierasz *Kraj wylotu* / *Kraj celu*, a w kolumnach *Skąd* / *Dokąd* pojawiają się tylko lotniska z tego kraju (np. „GDN – Gdańsk, …”). Można też wpisać sam kod IATA albo nazwę miasta („korfu”).
- Kolumny: Kraj wylotu, Skąd, Kraj celu, Dokąd, Data wylotu, Godzina startu, **Data powrotu**, Godzina startu powrotu, Nr lotu tam, Nr lotu powrót, Linia lotnicza, Notatka. Wypełniona *Data powrotu* tworzy podróż tam i z powrotem (dwa połączone loty); pusta — jeden lot.
- Arkusz zawiera zakładkę **Jak wypełnić** i listę **Lotniska**. Kolumna *Kraj wylotu* jest wstępnie ustawiona na Polskę; wiersze z samym krajem są pomijane, wiersz z notatką „przykład…” też.
- **Import** (`Ctrl+I`) przyjmuje teraz `.ods`, `.xlsx` (z pakietem `python3-openpyxl`) i `.csv`. Szablon jest też w wersji CSV — zapisz go z rozszerzeniem `.csv`.
- Albumy iCloud do zaimportowanych podróży możesz dodać potem ręcznie w szczegółach podróży (sekcja Zdjęcia).

## Co nowego w 0.8.0

- **Album w iCloud przy planowaniu.** Jeśli jest zainstalowane Linux iCloud Photos (0.15.1+), na końcu kalkulatora w „Planach” jest sekcja **Album w iCloud**:
  - przełącznik „Utworzyć album w Linux iCloud Photos?” (domyślnie włączony),
  - **tytuł albumu** do wpisania. Domyślny tytuł, np. „✈ Korfu · cze 2027”, zmienia się razem z celem i datą, dopóki nie wpiszesz własnego.
  - Po zapisaniu podróży SkyTrack tworzy w iCloud **pusty album** o tym tytule (albo łączy istniejący o tej samej nazwie) i łączy go z oboma lotami. Gdy się nie uda, pokazuje powód i odłącza album.
  - Po powrocie: karta lotu → „Album…” → **„Uzupełnij album zdjęciami z dni podróży”** dodaje zdjęcia od wylotu do powrotu do tego samego albumu (bez duplikatów).
- **Wyszukiwanie po polskich nazwach miejsc wakacyjnych:** Korfu, Kreta, Kos, Rodos, Zakintos, Majorka, Teneryfa, Cypr, Malta, Sycylia, Sardynia, Egipt, Malediwy i inne. „kos” znajduje teraz najpierw wyspę Kos (KGS).

## Co nowego w 0.7.1

- **Planowanie z datą powrotu.** Kalkulator na stronie „Plany” ma przełącznik **Tam i z powrotem** (domyślnie) / **Jeden lot**:
  - Wylot: data i godzina startu. Powrót: data i godzina startu powrotu. Data powrotu sama trzyma się tydzień po wylocie, dopóki jej nie zmienisz.
  - Wynik: dystans w każdą stronę i razem, czas lotu, lądowanie u celu i po powrocie w czasie lokalnym, liczba dni na miejscu, różnica stref i czas do wylotu.
  - „Zapisz jako planowaną podróż” otwiera okno podróży z obiema datami i godzinami już wpisanymi.
  - W „Nadchodzących podróżach” podróż tam i z powrotem to jedna karta („Tam i z powrotem · powrót 23 cze 2027”).

## Co nowego w 0.7.0: podróż tam i z powrotem

- **Nowa podróż = wylot i powrót.** Okno „Nowa podróż” ma na górze przełącznik **Tam i z powrotem** (domyślnie) / **Jeden lot**:
  - **Trasa:** skąd wylatujesz (np. GDN) i cel podróży (np. HER).
  - **Wylot:** data i godzina startu z domu.
  - **Powrót:** data i godzina startu w drodze do domu. Data powrotu sama ustawia się na tydzień po wylocie, dopóki jej nie zmienisz.
  - Każdy z dwóch lotów może mieć numer lotu, miejsce i (opcjonalnie) dokładną godzinę lądowania.
  - **Podsumowanie** pokazuje: dystans w każdą stronę i razem, czas lotu tam i z powrotem, lądowanie u celu i po powrocie (czas lokalny), liczbę dni na miejscu i strefy czasowe.
  - Zapis tworzy dwa loty połączone w jedną podróż. Na liście mają oznaczenie „wylot” / „powrót”, a karta pokazuje np. „Wylot · powrót 7 wrz 2025”. Edycja któregokolwiek otwiera oba, a usunięcie usuwa oba.
- **Jasne nazwy:** to, co wcześniej nazywało się „Przylot” przy pojedynczym locie, to teraz **Godzina lądowania** (lądowanie tego samolotu). „Wylot” i „Powrót” oznaczają podróż: wyjazd z domu i powrót do domu. Na karcie pola nazywają się „Start” i „Lądowanie”.
- **Starsze podróże wpisane jako dwa osobne loty** (np. GDN → KGS i KGS → GDN): na karcie jednego z nich jest przycisk **„Połącz w podróż”**, który łączy je w jedną podróż tam i z powrotem.
- Zdjęcia z dni podróży przy połączonej podróży obejmują czas od wylotu do powrotu.
- „Jeden lot” i „Zapisz i dodaj kolejny lot” zostają do podróży z przesiadkami i wielu miast.

## Co nowego w 0.6.1

- **Kraj zamieszkania ustawiany na stałe.** Wcześniej SkyTrack zgadywał go jako kraj, z którego startuje najwięcej lotów. Przy jednym wyjeździe tam i z powrotem (GDN → KGS → GDN) był remis i jako „dom” wychodziła Grecja. Teraz domyślnie jest to kraj z języka systemu (pl_PL → Polska). W statystykach, przy „Odwiedzone kraje”, jest wybór „Mieszkam w:”, a wybór zostaje zapamiętany.

## Co nowego w 0.6.0: odzyskiwanie hasła

- **Podpowiedź do hasła** (opcjonalna). Ustawiasz ją przy zakładaniu konta albo w „Zmień login i hasło…”. Pokazuje się pod polem hasła po błędnej próbie logowania. Nie może zawierać samego hasła i jest zapisana jawnie, więc nie wpisuj w niej niczego poufnego.
- **„Nie pamiętam hasła” — reset hasłem administratora Ubuntu.** Przycisk otwiera systemowe okno „Podaj hasło administratora…” (polkit, to samo co przy instalacji programów). Po poprawnym haśle ustawiasz nowe hasło do SkyTrack (login i podpowiedź są już wpisane). Podróże zostają.
  - Działa dla konta z uprawnieniami administratora (grupa `sudo`; pierwsze konto w Ubuntu ma je domyślnie).
  - Pomocnik `/usr/lib/linux-skytrack/confirm-admin` niczego nie robi. Służy tylko do tego, żeby polkit zapytał o hasło. Regułę opisuje `/usr/share/polkit-1/actions/com.jgu.LinuxSkyTrack.policy` i za każdym razem wymaga hasła (`auth_admin`).
  - Awaryjnie nadal działa usunięcie `~/.config/linux-skytrack/auth.json`.

## Co nowego w 0.5.0

- **Bez zasobnika (tray).** SkyTrack to zwykła aplikacja w oknie: zamknięcie okna kończy program. Usunięte zostały ikona w górnym pasku, opcje „Zamykanie do zasobnika” i „Blokuj po schowaniu okna”, przełącznik `--hidden` i zależności od AppIndicatora / GTK3. Logowanie działa przy każdym uruchomieniu, a Ctrl+L blokuje okno w trakcie pracy.
- Przypomnienie o locie (24 h przed) pojawia się, gdy SkyTrack jest otwarty.

## Co nowego w 0.4.0

- **Logowanie loginem i hasłem.** Przy pierwszym uruchomieniu ustawiasz login i hasło (co najmniej 6 znaków), potem każde otwarcie zaczyna się od ekranu logowania.
  - Hasło nie jest nigdzie zapisane, tylko jego skrót (PBKDF2-SHA256, 310 000 iteracji, losowa sól) w `~/.config/linux-skytrack/auth.json` z uprawnieniami 600.
  - Menu → **Zablokuj** (Ctrl+L) i **Zmień login i hasło…**.
  - Po 5 błędnych próbach trzeba odczekać 30 s, przy kolejnych coraz dłużej.
  - Gdy aplikacja jest zablokowana, powiadomienia o lotach są wstrzymane.
  - **Nie pamiętasz hasła?** Od 0.6.0 jest podpowiedź i reset hasłem administratora Ubuntu (patrz wyżej). Awaryjnie: usuń `~/.config/linux-skytrack/auth.json`, a SkyTrack poprosi o nowe konto. Podróże zostają.
  - Logowanie chroni dostęp do aplikacji, ale nie szyfruje pliku z podróżami (`skytrack.db`).
- **„Odbyta” zamiast „przeleciana”:** loty z przeszłości to teraz loty odbyte (licznik „ODBYTE LOTY”, plakietka „odbyta”).
- **Odwiedzone kraje.**
  - Kliknięcie karty „Kraje” w statystykach przewija do nowej tabeli „Odwiedzone kraje”: flaga, nazwa po polsku, lotniska, okres i liczba wizyt.
  - Każdy kraj się rozwija; kliknięcie lotu pokazuje go na mapie.
  - Kraj zamieszkania (od 0.6.1 do wyboru w „Mieszkam w:”, domyślnie z języka systemu) nie jest liczony.
  - Kliknięcie karty „Najdłuższy lot” pokazuje ten lot na mapie.
- **Matrix bez spadających znaków:** kolorystyka zostaje.
- Poprawka: mapa ustawia widok poprawnie także wtedy, gdy dane wczytały się przy ukrytym oknie.

## Co nowego w 0.3.0: zdjęcia z iCloud (Linux iCloud Photos)

Wymaga **Linux iCloud Photos 0.15.0+** (paczka .deb albo Flatpak). Bez niej SkyTrack działa jak dotąd, a sekcja zdjęć się nie pokazuje.

- **Zdjęcia na karcie pokładowej.** Pod wybranym lotem jest pasek miniatur: z połączonego albumu albo, jeśli albumu nie ma, ze zdjęć zrobionych w czasie podróży. Czas podróży liczy się od dnia wylotu do następnego lotu w dzienniku (kolejny odcinek albo powrót), najwyżej 30 dni; gdy nic nie następuje, 4 dni.
- **„Otwórz album” / „Zdjęcia z tych dni”** otwiera Linux iCloud Photos od razu na tym albumie albo przewinięte do dni podróży. Gdy aplikacja jest już otwarta, przełącza się w otwartym oknie.
- **„Album…”: połącz album z lotem.** Lista albumów z iCloud z wyszukiwarką. Na górze są te, które pasują do celu (miasto po polsku i angielsku, kraj, kod lotniska), np. „Dubaj 2025” przy locie do DXB. Połączony album widać też przy edycji podróży (sekcja „Zdjęcia”) i jako ikonkę na liście.
- **„Utwórz album z dni podróży”.** Podajesz nazwę (domyślnie np. „✈ Dubaj · lut 2025”) i zakres dat, „Sprawdź” pokazuje, ile zdjęć jest w tym czasie, z podglądem. Potem Linux iCloud Photos tworzy album w iCloud, dodaje zdjęcia z postępem (pomija duplikaty) i od razu łączy album z lotem.
- **Bez osobnego logowania.** SkyTrack korzysta z sesji Linux iCloud Photos. Jeśli sesja wymaga ponownego logowania, na karcie pojawia się „Zaloguj się”, który otwiera Linux iCloud Photos. Miniatury są zapamiętywane na 6 h (`~/.cache/linux-skytrack/icloud`), przycisk ⟳ odświeża je od razu.
- Kolumna `album` w eksporcie / imporcie CSV.

## Co nowego w 0.2.0

- **Historyczne podróże:**
  - Datę wpisujesz z klawiatury (`04.05.2012`, `2012-05-04`, `4.5.12`) albo wybierasz z kalendarza.
  - „Zapisz i dodaj kolejny lot” zapisuje lot i od razu otwiera następny: wylot z lotniska docelowego, ta sama data. Cała dawna wycieczka (np. GDN → WAW → DXB → BKK) wpisuje się w minutę.
  - **Lot powrotny** jednym kliknięciem z karty pokładowej.
  - **Import CSV:** eksport z myFlightradar24, eksport z Flighty, własny format SkyTrack albo dowolny CSV z kolumnami skąd / dokąd / data. Lotniska rozpoznaje po kodzie IATA/ICAO, po „(GDN/EPGD)” i po nazwie miasta. Duplikaty pomija. Przed importem pokazuje podsumowanie (ile lotów, km, lata, pominięte wiersze).
  - **Eksport CSV** wszystkich podróży, przydatny też jako kopia zapasowa.
- **Planowanie (etap 2):**
  - Podróż z przyszłą datą to podróż zaplanowana. Ma sekcję „Nadchodzące” z odliczaniem (za 12 dni, jutro, za 3 h 20 min) i przerywany łuk na mapie. Nie wlicza się do odbytych km, dopóki nie minie jej data; potem przechodzi do historii sama.
  - Strona **Plany** ma kalkulator lotu: dystans, szacowany czas, przylot w czasie lokalnym celu (np. „pon, 23 lis 2026, 08:26 UTC+9”), różnicę stref i czas do wylotu. Wynik zapisujesz jednym przyciskiem.
  - Przy dodawaniu podróży widać status (zaplanowana / odbyta) i szacowany przylot w czasie lokalnym.
  - **Przypomnienie** 24 h przed zaplanowanym lotem (gdy SkyTrack jest otwarty).
- **Wygląd** (Menu → Wygląd):
  - **Systemowy:** klasyczny Adwaita, sam przełącza się jasny / ciemny razem z Ubuntu.
  - **Flighty:** nocny granat, złote pinezki, świecące łuki, ciemna mapa.
  - **Matrix:** zielony fosfor na czerni, czcionka monospace, świecące cyfry, zielona mapa, licznik km „dekodujący” cyfry (od 0.4.0 bez spadających znaków na mapie).
  - We wszystkich stylach jest karta pokładowa (wybrany lot, następny albo ostatni), animowany licznik kilometrów i samolot na podświetlonym łuku.
- **Statystyki:** nowe karty „dookoła Ziemi”, „do Księżyca”, „zaplanowane” i liczba różnych tras.

## Funkcje z wersji 0.1

- Podróże: skąd, dokąd, data, opcjonalnie godziny (czas lokalny), numer lotu, linia, samolot, miejsce, notatka.
- Wyszukiwarka lotnisk offline (ok. 5 300 lotnisk, polskie nazwy popularnych miast).
- Mapa podróży: łuki po ortodromie, pinezki z liczbą wizyt, przełącznik Mapa / Satelita.
- Suma km i statystyki rok → miesiąc → dzień, czas lotu ze stref czasowych.
- Powiadomienia, ikona w motywie.

## Instalacja

```bash
sudo apt install ./linux-skytrack_0.8.0_all.deb
sudo apt install ./linux-icloud-photos_0.15.1_all.deb   # opcjonalnie: zdjęcia z podróży
```

Wymaga Ubuntu 24.04 lub nowszego (GTK 4, libadwaita ≥ 1.5, WebKitGTK 6.0). Zależności doinstalują się same.

Uruchamianie z menu aplikacji („SkyTrack”) albo z terminala:

```bash
linux-skytrack            # normalnie
linux-skytrack --add      # od razu okno „Nowa podróż”
```

Skróty: `Ctrl+L` zablokuj, `Ctrl+N` nowa podróż, `Ctrl+1` podróże, `Ctrl+2` plany, `Ctrl+3` statystyki, `Ctrl+I` import (arkusz / CSV), `Ctrl+E` eksport CSV, `Ctrl+W` zamknij okno, `Ctrl+Q` zakończ.

## Import historii z innych aplikacji

| Skąd | Jak wyeksportować |
|---|---|
| myFlightradar24 | eksport CSV w ustawieniach konta na my.flightradar24.com |
| Flighty | eksport danych lotów do CSV w ustawieniach aplikacji |
| Szablon SkyTrack | Menu → Zapisz szablon importu…, wypełnij w LibreOffice Calc i zaimportuj plik `.ods` |
| Arkusz / inny | `.ods`, `.xlsx` lub CSV z kolumnami `skąd`/`from`, `dokąd`/`to`, `data`/`date` (opcjonalnie godziny, numer lotu, linia, samolot, miejsce, notatka). Separator `,` lub `;`. |

## Gdzie są dane

| Co | Ścieżka |
|---|---|
| Podróże (SQLite) | `~/.local/share/linux-skytrack/skytrack.db` |
| Ustawienia | `~/.config/linux-skytrack/settings.json` |
| Konto (skrót hasła) | `~/.config/linux-skytrack/auth.json` |
| Cache kafelków mapy | `~/.cache/linux-skytrack/webkit/` |

Kopia zapasowa to po prostu skopiowanie pliku `skytrack.db`. W menu jest też „Otwórz folder z danymi”.

## Jak liczone są kilometry

Dystans to odległość po ortodromie między lotniskami (wzór haversine, R = 6371 km). Tak samo liczą ją Flighty, my.flightradar24 i podobne serwisy. Prawdziwa trasa samolotu bywa o kilka procent dłuższa przez korytarze powietrzne i podejścia. Etap 3 doda zapis rzeczywistej trasy dla lotów śledzonych na żywo.

Szacowany czas lotu = dystans / 820 km/h + 30 min (kołowanie, wznoszenie, podejście).

## Plan dalszych etapów

1. ✅ **Etap 1 (0.1):** podróże, mapa podróży z pinezkami, mapa/satelita, suma km, statystyki rok/miesiąc/dzień.
2. ✅ **Etap 2 (0.2):** planowanie, historia i import/eksport CSV, style Systemowy / Flighty / Matrix.
   ✅ **0.3:** albumy i zdjęcia z Linux iCloud Photos przy lotach.
3. **Etap 3, śledzenie na żywo:** wyszukiwanie po numerze lotu (AeroDataBox), pozycja z adsb.lol (zapasowo OpenSky), osobna mapa śledzenia, powiadomienia o starcie i lądowaniu.
4. **Etap 4:** zapis prawdziwej trasy, podsumowanie roku („Rok w lotach”).

## Uruchamianie ze źródeł

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-webkit-6.0
./linux-skytrack
```

Paczkę .deb buduje `tools/build_deb.sh` (wynik trafia do `dist/`).

Bazę lotnisk odświeża się tak:

```bash
pip install timezonefinder
curl -LO https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv
curl -LO https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/countries.csv
python3 tools/build_airports.py airports.csv countries.csv data/airports.json
```

Polskie nazwy krajów (`data/countries_pl.json`, z CLDR) odświeża `pip install babel && python3 tools/build_countries_pl.py`.

Narzędzia deweloperskie WebKit (inspektor mapy) włącza `SKYTRACK_DEVTOOLS=1 ./linux-skytrack`.

## Struktura

```
linux-skytrack            launcher
skytrack/app.py           aplikacja, akcje, powiadomienia, O aplikacji
skytrack/window.py        okno główne: lista podróży + mapa
skytrack/stats_page.py    statystyki, wykres, drzewo rok/miesiąc/dzień
skytrack/trip_dialog.py   dodawanie/edycja podróży, wyszukiwarka lotnisk, daty z klawiatury
skytrack/plan_page.py     planowanie: kalkulator lotu, nadchodzące podróże
skytrack/widgets.py       karta pokładowa, linia trasy, animowany licznik
skytrack/theme.py         style Systemowy / Flighty / Matrix
skytrack/auth.py          konto: skrót hasła PBKDF2, weryfikacja, opóźnienie po błędach
skytrack/lock.py          ekran logowania / zakładania konta, reset przez polkit, zmiana hasła
packaging/*.policy        reguła polkit dla resetu hasła (+ packaging/confirm-admin)
skytrack/importer.py      import (.ods/.xlsx/CSV) i eksport CSV (szablon, myFlightradar24, Flighty)
templates/                szablony importu PL i EN (.ods z listami wyboru, .csv)
skytrack/i18n.py          język interfejsu (polski z systemu, inaczej angielski), _() i plural()
skytrack/i18n_en.py       teksty angielskie (klucz = tekst polski)
tools/build_template.py   generuje szablon (openpyxl + LibreOffice, potem tools/fix_template_lo.py)
skytrack/photos.py        most do linux-icloud-photos (albumy, miniatury, otwieranie, tworzenie albumu)
skytrack/photos_ui.py     pasek zdjęć na karcie, okno „Album iCloud dla podróży”
skytrack/mapview.py       WebKitGTK + most JSON do mapy
skytrack/{db,geo,stats,airports}.py   dane, geometria, strefy czasowe, agregacje
web/                      mapa (Leaflet 1.9.4 lokalnie)
data/airports.json        lotniska (OurAirports) ze strefami czasowymi
```

## Źródła danych i licencje

- Lotniska: [OurAirports](https://ourairports.com/data/), domena publiczna.
- Mapa: © [OpenStreetMap](https://www.openstreetmap.org/copyright), ODbL. Kafelki ładowane z tile.openstreetmap.org zgodnie z polityką użycia; aplikacja przedstawia się własnym User-Agentem i cache'uje kafelki.
- Satelita: Esri World Imagery (Esri, Maxar, Earthstar Geographics, GIS User Community).
- [Leaflet](https://leafletjs.com/), BSD-2-Clause.
- Kod aplikacji: MIT.
