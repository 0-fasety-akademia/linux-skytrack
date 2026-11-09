# SkyTrack (linux-skytrack)

**Current version: 1.2.1 (2026-11-09)**

A flight log and live flight tracker for Ubuntu. Log your trips, see them on a map (street, satellite or an offline outline map) with pins on every airport you have visited, and let SkyTrack count the kilometres and build statistics per year, month and day. Watch all air traffic around you live, track any flight by its number, get a poster of your year in the air, and keep backups on your disk, in Google Drive or in iCloud Drive.

Part of the **JGu Linux Apps** series. Created by: JGu · Supported by Claude.

![icon](icons/hicolor/scalable/apps/linux-skytrack.svg)

## Version history

### 1.2.1 (2026-11-09)

- **iCloud Drive backup: Linux iCloud Photos is detected correctly.** SkyTrack now looks at every installation — the .deb and the Flatpak (user and system) — and uses the newest one that can upload to iCloud Drive. The switch is never locked because of a version guess; when the installed version looks too old, the row says which versions were found.
- **Linux iCloud Photos installed as a Flatpak works with SkyTrack** (albums, photos, iCloud Drive backups): the Flatpak gets access to SkyTrack's cache folder, where the bridge results, thumbnails and files to upload are kept.

### 1.2.0 (2026-11-09): cloud backup

- **Optional cloud copy of your backups** (Menu → Backup… → *Cloud backup*):
  - **Google Drive:** add your Google account in Ubuntu (*Settings → Online Accounts*, with **Files** on), then in SkyTrack choose *Choose… → Google Drive: you@gmail.com*. SkyTrack creates a **SkyTrack** folder in your Drive. You can pick **any other folder** instead (a USB stick, a network share, a folder synced by another app).
  - **iCloud Drive:** through **Linux iCloud Photos 0.16.0+**, using its saved session (no second sign-in). Backups go to a **SkyTrack** folder in iCloud Drive. Needs iCloud Drive with web access (with Advanced Data Protection, turn on “Access iCloud Data on the Web”).
- Uploads happen once a week together with the automatic backup, and on demand with **Upload**. One file per day (a second upload on the same day replaces it). The cloud keeps the newest 5, 10 or 20 backups; older ones are removed (from iCloud Drive they go to “Recently Deleted”). Other files in the folder are never touched.
- Each target shows the last upload date or the error. A failed automatic upload shows a message with a *Details* button.

### 1.1.2 (2026-11-09): tracking fixes

- **Clicking the map or another aircraft ends tracking**, for any flight except your own flight from the log (from *My flights* or automatic tracking on the day of departure), which stays until you press ■.
- **The map no longer zooms out by itself.** While tracking, only the dashed from → to route line and the flown trail are drawn. A flight typed in the panel is centred once when it is found; after that the map follows it only with *Follow the aircraft on the map* on.
- **Far fewer “Route unknown”.** Routes now come first from the same databases tar1090 uses (the routeset services of adsb.im and adsb.lol, which also know callsigns like RYR1JM), then from adsbdb. For multi-leg routes (A → B → C) SkyTrack picks the leg the aircraft is flying now. A route the service marks as implausible is labelled “(uncertain)”.
- **Ground stations are hidden.** Airport ADS-B transmitters and vehicles (e.g. “48E304 · TWR” at Gdańsk airport, which showed “On the ground”) no longer appear as aircraft.

### 1.1.1 (2026-11-09)

- **“Track this flight” on the traffic map works.** The button turns into “● Tracking this flight”, the route and the flight's trail appear on the map and the aircraft is highlighted. Details (altitude, speed, arrival) are in the left panel.

### 1.1.0 (2026-11-09): air traffic like Flightradar

- **Live → Air traffic:** the map shows **every aircraft in view** (up to about 460 km from the centre of the map), refreshed every 10 seconds. Click an aircraft to see its callsign, airline, **from → to** (with the route drawn on the map), altitude, speed, heading, aircraft type and registration, plus a **Track this flight** button. The map starts over your home airport.
- **Free, no account, no daily limits:** positions come from the community ADS-B networks **adsb.lol**, with **airplanes.live** and **adsb.fi** as fall-backs. OpenSky is used only when these do not answer.
- **Every tracked flight gets its route and arrival time**, also without a trip in the log: type a flight number or click an aircraft, and SkyTrack finds where it flies from and to. The line under the flight name says where the data came from (“route from adsbdb · data: adsb.lol”).
- Refresh of a tracked flight every 30 s by default (15 / 30 / 60 / 120 s to choose).
- **Summary:** year buttons right on the page (“All years · 2026 · 2025 …”), city names in the interface language, and airport labels on the poster no longer overlap.
- **The login screen shows the version and release date.**

### 1.0.0 (2026-11-09): the big release

- **Live tab (`Ctrl+4`): live flight tracking.** Enter a flight number (W6 1729, LO 3803, FR 1234) or a callsign (RYR5TG) and see the aircraft on its own map: position, trail, altitude, speed, heading, vertical speed, distance to go and **estimated arrival** in the destination's local time, compared with the schedule.
  - **My flights:** flights from your log for yesterday, today and tomorrow, one click to track.
  - **Automatic:** on the day of departure SkyTrack starts tracking your flight (when it has a flight number and a take-off time) about 40 minutes before take-off and notifies you: **took off**, **delayed** (15 min or more against the plan), **landed**. You can turn this off in the tracking settings.
  - Airlines such as Ryanair fly under callsigns like RYR5TG instead of RYR1234. For a flight in your log SkyTrack matches the aircraft by route and says so; you can always type the callsign yourself.
- **Summary tab (`Ctrl+5`): your year in the air.** A poster with a route map (visited countries highlighted), kilometres, flights, time in the air, longest flight, top destination, new countries and the busiest month, plus a list of facts. **Save as image…** writes a 1080×1350 PNG. The poster colours follow the app look (System / Flighty / Matrix).
- **Offline map:** without internet (on board, for example) the map shows **country outlines** under your routes instead of an empty background, with the countries you have visited highlighted. A third layer button, **Outline**, shows this map on demand.
- **Backups (Menu → Backup…):** one `.skytrack` file with all trips, settings and the account (login and password hash, never the password itself), readable only by you. **Restore** from a file or from the list of backups; SkyTrack saves the current state first. **Automatic weekly backup** when the app opens, keeping the last 5.
- Airports in lists (import template, search) are ordered by the number of routes: Heathrow before Aberdeen, Warsaw Chopin before Modlin. Better city names (Athens instead of Spata-Artemida, Kraków instead of Balice, Milan, Bergamo, Brussels…).

### 0.10.0: English interface

- When the system language is **not Polish**, SkyTrack runs in English: menus, dialogs, messages, statistics, the map, dates (“Mon, 1 Sep 2025”), country names and numbers (“8,486 km”). Force a language with `SKYTRACK_LANG=en` or `SKYTRACK_LANG=pl`.
- English import template: **Menu → Save import template…** writes `skytrack-import-en.ods`. The importer understands both templates.
- Home country with an English system: first the *Formats* region (Ubuntu: Settings → Region & Language → Formats), then the airport of your first flight, so `en_US` no longer means the USA. You can always change it in Statistics (“I live in:”).

### 0.9.0: import template with drop-down lists

- **Menu → Save import template…** saves a LibreOffice Calc sheet: one row per trip, one to dozens of trips at once.
- **Drop-down lists:** pick the departure / destination country first, and the *From* / *To* columns offer only the airports of that country. You can also type an IATA code or a city name.
- A filled-in *Return date* creates a round trip (two linked flights); an empty one creates a single flight.
- **Import** (`Ctrl+I`) now reads `.ods`, `.xlsx` (with `python3-openpyxl`) and `.csv`.

### 0.8.0

- **iCloud album while planning.** With Linux iCloud Photos (0.15.1+) the trip calculator in *Plans* can create an empty iCloud album with a title you choose (default e.g. “✈ Corfu · Jun 2027”) and link it to both flights. Back home, *Album… → Fill the album with photos from the trip days* adds the photos without duplicates.
- Search by Polish names of holiday places: Korfu, Kreta, Kos, Rodos, Zakintos, Majorka, Teneryfa and more.

### 0.7.1

- **Planning with a return date.** The calculator has *Round trip* (default) / *One way*: distance each way and in total, flight time, landing at the destination and back home in local time, days at the destination, time difference and time to departure.

### 0.7.0: round trips

- **A new trip is an outbound and a return flight.** The *New trip* dialog has *Round trip* / *One way*, a summary (distance, flight times, local landing times, days at the destination) and saves two linked flights. Editing either one opens both, deleting removes both.
- Clear names: *Departure* and *Return* describe the trip, *Take-off* and *Landing* describe one flight.
- Older trips entered as two separate flights can be joined with **Link as a trip**.

### 0.6.1

- **Home country you can set.** It used to be guessed from the most common departure country, which tied on a single round trip. Now it comes from the system language by default and can be chosen in Statistics.

### 0.6.0: password recovery

- **Password hint** (optional), shown after a failed login.
- **“I forgot my password” — reset with the Ubuntu administrator password** (polkit). Your trips stay.

### 0.5.0

- **No tray icon.** SkyTrack is a normal windowed app; closing the window quits it. Flight reminders appear while SkyTrack is open.

### 0.4.0

- **Login and password.** Only a PBKDF2-SHA256 hash is stored (310,000 iterations, random salt, file mode 600). Lock with `Ctrl+L`, change the login and password in the menu, a growing wait after 5 failed attempts.
- **Visited countries** table in Statistics (flag, name, airports, period, visits), without your home country. Clicking the *Longest flight* card shows that flight on the map.
- *Matrix* look without falling characters.

### 0.3.0: iCloud photos (Linux iCloud Photos)

- **Photos on the boarding pass** from a linked iCloud album or from the photos taken during the trip. *Open album* / *Photos from these days* opens Linux iCloud Photos right there.
- **Link an iCloud album** to a flight, or **create an album from the trip days** (with a preview of how many photos it will get). Uses the session of Linux iCloud Photos, no separate sign-in.

### 0.2.0

- **Historical trips:** dates typed from the keyboard, *Save and add next flight*, return flight in one click, **CSV import** (myFlightradar24, Flighty, SkyTrack or any CSV with from / to / date) and **CSV export**.
- **Planning:** trips with a future date, countdowns, dashed arcs, a flight calculator with local arrival time, a reminder 24 hours before.
- **Looks:** *System* (light / dark with Ubuntu), *Flighty* (night blue, golden pins) and *Matrix* (green phosphor). Boarding-pass card and animated kilometre counter.

### 0.1.0

- Trips with from, to, date, optional local times, flight number, airline, aircraft, seat and note. Offline airport search (about 5,300 airports). Trip map with great-circle arcs and pins, street / satellite map, total kilometres and statistics per year → month → day, notifications.

## Features

- **Trips:** round trips or single flights, historical and planned, with local times, flight numbers, seats and notes; keyboard date entry and a calendar.
- **Map:** great-circle arcs, pins with visit counts, street / satellite / offline outline layers, visited countries highlighted.
- **Statistics:** kilometres, flights, time in the air, airports, countries, longest flight, around the Earth / to the Moon, year → month → day breakdown, visited countries.
- **Plans:** a calculator for distance, flight time, local arrival and return times and time zones; upcoming trips with countdowns; optional iCloud album.
- **Live:** all air traffic in view, from → to routes, tracking by flight number or callsign, automatic tracking of your flights with notifications.
- **Summary:** a poster of your year (or all years), saved as PNG.
- **Import / export:** spreadsheet template with drop-down lists (`.ods`), `.xlsx`, CSV from myFlightradar24 and Flighty; CSV export.
- **Backups:** one-file backups, restore, weekly automatic backups, optional copy in Google Drive / any folder / iCloud Drive.
- **Privacy:** login and password (hash only), lock with `Ctrl+L`, password reset with the Ubuntu administrator password.
- **Photos:** iCloud albums and trip photos through Linux iCloud Photos.
- **Looks:** System, Flighty and Matrix. **Languages:** English and Polish.

## Installation

```bash
sudo apt install ./linux-skytrack_1.2.1_all.deb
sudo apt install ./linux-icloud-photos_0.16.1_all.deb   # optional: trip photos and iCloud Drive backups
```

Needs Ubuntu 24.04 or newer (GTK 4, libadwaita ≥ 1.5, WebKitGTK 6.0). Dependencies are installed automatically. `python3-openpyxl` (for `.xlsx` import) is recommended; Google Drive backups use `gvfs-backends` and `gnome-online-accounts`, which are part of the standard Ubuntu desktop.

Start it from the app grid (“SkyTrack”) or from a terminal:

```bash
linux-skytrack            # normal start
linux-skytrack --add      # open the "New trip" dialog right away
SKYTRACK_LANG=en linux-skytrack   # force English (or pl for Polish)
```

Keyboard shortcuts: `Ctrl+N` new trip, `Ctrl+1` trips, `Ctrl+2` plans, `Ctrl+3` statistics, `Ctrl+4` live, `Ctrl+5` summary, `Ctrl+I` import, `Ctrl+E` export CSV, `Ctrl+L` lock, `Ctrl+W` close the window, `Ctrl+Q` quit.

## Importing your history

| From | How |
|---|---|
| SkyTrack template | Menu → Save import template…, fill it in LibreOffice Calc and import the `.ods` file |
| myFlightradar24 | CSV export in your account settings on my.flightradar24.com |
| Flighty | CSV export of your flight data in the app settings |
| Any spreadsheet | `.ods`, `.xlsx` or CSV with `from`, `to` and `date` columns (optionally times, flight number, airline, aircraft, seat, note); separator `,` or `;` |

Airports are recognised by IATA / ICAO code, “(GDN/EPGD)” or city name. Duplicates are skipped, and a summary is shown before anything is imported.

## Live tracking and data sources

- **Air traffic** and **tracked flights** come from the community ADS-B networks adsb.lol, airplanes.live and adsb.fi — free, no key, no daily limit. SkyTrack asks only while the *Live* tab is open (every 10 s for the map, every 30 s by default for a tracked flight) and identifies itself with its User-Agent.
- **Routes (from → to)** come from the routeset services of adsb.im / adsb.lol and from adsbdb.com, cached for a day. They are based on schedules and can be out of date when airlines change flight numbers, so SkyTrack always says where a route came from.
- **OpenSky Network** is a fall-back. Without an account it allows 400 requests a day; a free OpenSky API client (Account → API client) gives 4,000. The client id and secret are stored in `~/.config/linux-skytrack/opensky.json` (mode 600).
- Positions come from volunteers' receivers: over oceans and in some regions there may be none (“No signal”).

## Backups

- **Menu → Backup…** creates a `.skytrack` file (a zip with the database, settings and the account hash), restores one, and lists the automatic weekly backups (the last 5 are kept in `~/.local/share/linux-skytrack/backups/`). Before every restore the current state is saved.
- **Cloud backup (optional):** Google Drive (via Ubuntu Online Accounts) or any folder, and iCloud Drive (via Linux iCloud Photos 0.16.0+). Weekly with the automatic backup and on demand; the cloud keeps the newest 5 / 10 / 20 backups in a **SkyTrack** folder.

## Where your data is

| What | Path |
|---|---|
| Trips (SQLite) | `~/.local/share/linux-skytrack/skytrack.db` |
| Settings | `~/.config/linux-skytrack/settings.json` |
| Account (password hash) | `~/.config/linux-skytrack/auth.json` |
| OpenSky account (optional) | `~/.config/linux-skytrack/opensky.json` |
| Automatic backups | `~/.local/share/linux-skytrack/backups/` |
| Map tiles, photo thumbnails, routes | `~/.cache/linux-skytrack/` |

The login protects access to the app; it does not encrypt the trips database. *Menu → Open data folder* opens the data folder.

## How kilometres are counted

The distance is the great-circle distance between the airports (haversine formula, R = 6,371 km), the same way Flighty, my.flightradar24 and similar services count it. The real flight path is usually a few percent longer because of airways and approaches.

Estimated flight time = distance / 820 km/h + 30 min (taxi, climb, approach).

## Running from source

```bash
sudo apt install python3-gi python3-gi-cairo python3-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-webkit-6.0
./linux-skytrack
```

`tools/build_deb.sh` builds the .deb into `dist/`. WebKit developer tools for the map: `SKYTRACK_DEVTOOLS=1 ./linux-skytrack`.

Data files are rebuilt with the scripts in `tools/`:

| File | Script | Source |
|---|---|---|
| `data/airports.json` | `build_airports.py airports.csv countries.csv data/airports.json` (needs `timezonefinder`) | OurAirports |
| `data/countries_pl.json` | `build_countries_pl.py` (needs `babel`) | CLDR |
| `data/airlines.json` | `build_airlines.py` | OpenFlights `airlines.dat` (+ current codes) |
| `data/popularity.json` | `build_popularity.py` | OpenFlights `routes.dat` |
| `web/world.js` | `build_world.py` | world-atlas / Natural Earth |
| `templates/*.ods`, `*.csv` | `build_template.py pl` / `en`, then `fix_template_lo.py` | the airport database |

## Project structure

```
linux-skytrack            launcher
skytrack/app.py           application, actions, notifications, About, automatic tracking
skytrack/window.py        main window: trips list, boarding pass, map; tabs
skytrack/trip_dialog.py   add / edit trip, airport search, keyboard dates
skytrack/plan_page.py     Plans: trip calculator, upcoming trips, iCloud album
skytrack/stats_page.py    Statistics: cards, chart, year/month/day tree, visited countries
skytrack/live_page.py     Live tab: tracking panel, air traffic, settings
skytrack/live.py          tracker: flight number → callsign, OpenSky client, events, ETA
skytrack/adsb.py          ADS-B networks (adsb.lol, airplanes.live, adsb.fi) and route lookups
skytrack/traffic.py       air traffic layer: every aircraft in view
skytrack/summary_page.py  Summary tab
skytrack/wrapped.py       year summary: numbers and the poster (cairo)
skytrack/backup.py        backup / restore (.skytrack = zip)
skytrack/backup_ui.py     Backup dialog
skytrack/cloud.py         cloud backup: Google Drive / folder (GIO), iCloud Drive (Linux iCloud Photos)
skytrack/importer.py      import (.ods / .xlsx / CSV) and CSV export
skytrack/photos.py        bridge to Linux iCloud Photos (albums, thumbnails, opening, creating)
skytrack/photos_ui.py     photo strip on the boarding pass, iCloud album dialog
skytrack/auth.py, lock.py login: PBKDF2 hash, lock screen, polkit reset, change password
skytrack/mapview.py       WebKitGTK map with a JSON bridge
skytrack/widgets.py       boarding pass, route line, animated counter
skytrack/theme.py         System / Flighty / Matrix looks
skytrack/i18n.py          interface language; i18n_en.py: English texts
skytrack/{db,geo,stats,airports}.py   storage, geometry and time zones, aggregation, airports
web/                      map page (Leaflet 1.9.4, topojson-client, world.js)
data/                     airports, airlines, airport popularity, Polish country names
templates/                import templates (Polish and English)
packaging/                desktop file, polkit policy, confirm-admin helper
tools/                    build scripts
```

## Data sources and licences

- Airports: [OurAirports](https://ourairports.com/data/), public domain.
- Map: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, ODbL. Tiles from tile.openstreetmap.org under its usage policy; the app sends its own User-Agent and caches tiles.
- Satellite imagery: Esri World Imagery (Esri, Maxar, Earthstar Geographics, GIS User Community).
- Offline map: country outlines from [Natural Earth](https://www.naturalearthdata.com/) 1:50m (public domain) via [world-atlas](https://github.com/topojson/world-atlas) (ISC); [topojson-client](https://github.com/topojson/topojson-client) (ISC).
- Air traffic: [adsb.lol](https://adsb.lol) (data ODbL), [airplanes.live](https://airplanes.live), [adsb.fi](https://adsb.fi) — free community ADS-B APIs for non-commercial use. Routes: [adsb.im](https://adsb.im) / adsb.lol routeset and [adsbdb](https://www.adsbdb.com).
- Fall-back live data: [The OpenSky Network](https://opensky-network.org), for non-commercial use.
- Airline codes and airport route counts: [OpenFlights](https://openflights.org/data.php), Open Database License (ODbL).
- [Leaflet](https://leafletjs.com/), BSD-2-Clause.
- Application code: MIT.
