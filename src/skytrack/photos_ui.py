"""UI for the linux-icloud-photos integration: photo strip on the boarding pass, album dialog."""
from datetime import date, datetime

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from zoneinfo import ZoneInfo

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from . import photos, stats
from .trip_dialog import DateRow
from .i18n import IS_PL, _, plural


def esc(s):
    return GLib.markup_escape_text(str(s))


def photo_word(n):
    return plural(n, "zdjęcie", "zdjęcia", "zdjęć", "photo", "photos")


class Strip(Gtk.Box):
    """Row of square thumbnails."""

    def __init__(self, size=58):
        super().__init__(spacing=6, homogeneous=True)
        self.size = size

    def set_files(self, files, total=None):
        child = self.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.remove(child)
            child = nxt
        for i, path in enumerate(files):
            try:
                tex = Gdk.Texture.new_from_filename(path)
            except GLib.Error:
                continue
            pic = Gtk.Picture.new_for_paintable(tex)
            pic.set_content_fit(Gtk.ContentFit.COVER)
            pic.set_can_shrink(True)
            frame = Gtk.Overlay(hexpand=True)
            frame.set_size_request(24, self.size)
            frame.set_child(pic)
            frame.add_css_class("thumb")
            frame.set_overflow(Gtk.Overflow.HIDDEN)
            last = i == len(files) - 1
            if last and total and total > len(files):
                more = Gtk.Label(label=f"+{total - len(files)}")
                more.add_css_class("thumb-more")
                more.set_halign(Gtk.Align.FILL)
                more.set_valign(Gtk.Align.FILL)
                frame.add_overlay(more)
            self.append(frame)


class PhotoSection(Gtk.Box):
    """Bottom part of the boarding pass: photos from the linked album or from the trip days."""

    __gsignals__ = {"manage-album": (GObject.SignalFlags.RUN_FIRST, None, (object,))}

    def __init__(self, info, all_infos):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6)
        self.info = info
        self.all_infos = all_infos
        self.call = None
        self.alive = True
        self.connect("unrealize", lambda *_: self._stop())

        sep = Gtk.Separator()
        sep.add_css_class("pass-sep")
        self.append(sep)

        head = Gtk.Box(spacing=6)
        lab = Gtk.Label(label=_('ZDJĘCIA'), xalign=0)
        lab.add_css_class("pass-label")
        head.append(lab)
        self.src = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.src.add_css_class("pass-sub")
        head.append(self.src)
        self.spinner = Gtk.Spinner(spinning=False, visible=False)
        head.append(self.spinner)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_('Odśwież zdjęcia'))
        refresh.add_css_class("flat")
        refresh.add_css_class("circular")
        refresh.connect("clicked", lambda *_: self.load(force=True))
        head.append(refresh)
        self.append(head)

        self.strip = Strip()
        self.append(self.strip)
        self.msg = Gtk.Label(xalign=0, wrap=True, visible=False)
        self.msg.add_css_class("pass-sub")
        self.append(self.msg)

        btns = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        self.open_btn = Gtk.Button()
        self.open_btn.add_css_class("flat")
        self.open_btn.connect("clicked", self._on_open)
        self.login_btn = Gtk.Button(label=_('Zaloguj się'), visible=False,
                                    tooltip_text=_('Otwórz Linux iCloud Photos i zaloguj się'))
        self.login_btn.add_css_class("flat")
        self.login_btn.connect("clicked", lambda *_: photos.open_app())
        manage = Gtk.Button(label=_('Album…'), tooltip_text=_('Połącz album z iCloud albo utwórz go z dni podróży'))
        manage.add_css_class("flat")
        manage.connect("clicked", lambda *_: self.emit("manage-album", info))
        btns.append(self.login_btn)
        btns.append(self.open_btn)
        btns.append(manage)
        self.append(btns)

        self.start, self.end = photos.trip_range(info, all_infos)
        album = info.trip.album
        if album:
            self.src.set_label(_('album „{0}”').format(album))
            self.open_btn.set_label(_('Otwórz album'))
        else:
            self.src.set_label(_('z dni podróży {0}').format(self._span()))
            self.open_btn.set_label(_('Zdjęcia z tych dni'))
        if info.planned and not album:
            self.strip.set_visible(False)
            self.open_btn.set_visible(False)
            refresh.set_visible(False)
            self._message(_('Po podróży pokażę tu zdjęcia z tych dni albo połącz album.'))
        else:
            self.load()

    def _span(self):
        a, b = self.start.date(), self.end.date()
        if a == b:
            return stats.nice_date(a.isoformat())
        return f"{a.day}.{a.month:02d}–{b.day}.{b.month:02d}.{b.year}"

    def _message(self, text):
        self.msg.set_label(text)
        self.msg.set_visible(bool(text))

    def _stop(self):
        self.alive = False
        if self.call:
            self.call.cancel()

    def load(self, force=False):
        self.spinner.set_visible(True)
        self.spinner.start()
        self._message("")
        self.call = photos.load_thumbs(self.info.trip.album or None, self.start, self.end,
                                       self._loaded, maxn=6, force=force)

    def _loaded(self, result):
        if not self.alive:
            return False
        self.spinner.stop()
        self.spinner.set_visible(False)
        self.login_btn.set_visible(False)
        if not result.get("ok"):
            self.strip.set_files([])
            self._message(photos.error_text(result))
            login = result.get("error") == "login_required"
            self.login_btn.set_visible(login)
            self.open_btn.set_visible(not login and result.get("error") != "not_installed")
            return False
        self.open_btn.set_visible(True)
        files, count = result.get("files", []), result.get("count")
        self.strip.set_files(files, count)
        if count is not None:
            src = _('album „{0}”').format(self.info.trip.album) if self.info.trip.album else _('z dni podróży {0}').format(self._span())
            self.src.set_label(f"{src} · {count} {photo_word(count)}")
        if not files:
            self._message(_('Brak zdjęć z tych dni w iCloud.') if not self.info.trip.album
                          else _('Album jest pusty.'))
        stale = result.get("stale_error")
        if stale:
            self._message(_('Pokazuję zapamiętane miniatury — ') + photos.error_text(stale))
        return False

    def _on_open(self, *_a):
        if self.info.trip.album:
            photos.open_album(self.info.trip.album)
        else:
            photos.open_dates(self.start, self.end)


class AlbumDialog(Adw.Dialog):
    """Link an existing iCloud album to a flight, or create one from the trip days."""

    __gsignals__ = {"chosen": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self, info, all_infos):
        super().__init__(title=_('Album iCloud dla podróży'), content_width=560, content_height=760)
        self.info = info
        self.albums = []
        self.calls = []
        self.connect("closed", lambda *_: [c.cancel() for c in self.calls if c])

        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_('Odśwież listę albumów'))
        self.refresh_btn.connect("clicked", lambda *_: self._load_albums(force=True))
        hb.pack_end(self.refresh_btn)
        tv.add_top_bar(hb)
        self.banner = Adw.Banner(button_label=_('Otwórz iCloud Photos'))
        self.banner.connect("button-clicked", lambda *_: photos.open_app())
        tv.add_top_bar(self.banner)
        self.toasts = Adw.ToastOverlay()
        page = Adw.PreferencesPage()
        self.toasts.set_child(page)
        tv.set_content(self.toasts)
        self.set_child(tv)

        t = info.trip
        head = Adw.PreferencesGroup(
            title=f"{t.origin} → {t.dest} · {stats.nice_date(t.dep_date, True)}",
            description=(_('Połączony album: „') + t.album + "”") if t.album else
            _('Wybierz album z iCloud albo utwórz nowy ze zdjęć zrobionych w czasie podróży.'))
        page.add(head)
        if t.album:
            unlink = Gtk.Button(label=_('Odłącz album'), halign=Gtk.Align.START, margin_top=6)
            unlink.add_css_class("destructive-action")
            unlink.add_css_class("pill")
            unlink.connect("clicked", lambda *_: self._choose(""))
            head.add(unlink)

        # Create from trip days -------------------------------------------------------------------
        start, end = photos.trip_range(info, all_infos)
        g_new = Adw.PreferencesGroup(
            title=_('Utwórz album z dni podróży'),
            description=_('Linux iCloud Photos utworzy album w iCloud i doda do niego zdjęcia zrobione w tym czasie (pomija te, które już w nim są). Zakres do następnego lotu w dzienniku — możesz go zmienić.'))
        self.name_row = Adw.EntryRow(title=_('Nazwa albumu'))
        self.name_row.set_text(info.trip.album or photos.default_album_name(info))
        if info.trip.album:
            g_new.set_title(_('Uzupełnij album zdjęciami z dni podróży'))
            g_new.set_description(_('Doda do „{0}” zdjęcia zrobione w tym czasie (pomija te, które już w nim są). Zakres od wylotu do powrotu — możesz go zmienić.').format(info.trip.album))
        self.from_row = DateRow(_('Od'), start.date().isoformat())
        self.to_row = DateRow(_('Do'), end.date().isoformat())
        self.count_row = Adw.ActionRow(title=_('Zdjęcia w tym czasie'), subtitle=_('kliknij „Sprawdź”'))
        check = Gtk.Button(label=_('Sprawdź'), valign=Gtk.Align.CENTER)
        check.connect("clicked", self._on_check)
        self.count_row.add_suffix(check)
        for r in (self.name_row, self.from_row, self.to_row, self.count_row):
            g_new.add(r)
        self.preview = Strip(size=64)
        self.preview.set_margin_top(8)
        g_new.add(self.preview)
        self.progress = Gtk.ProgressBar(visible=False, margin_top=8, show_text=True)
        g_new.add(self.progress)
        self.create_btn = Gtk.Button(label=_('Dodaj zdjęcia do albumu') if info.trip.album else _('Utwórz album i połącz'),
                                     halign=Gtk.Align.CENTER, margin_top=10)
        self.create_btn.add_css_class("pill")
        self.create_btn.add_css_class("suggested-action")
        self.create_btn.connect("clicked", self._on_create)
        g_new.add(self.create_btn)
        page.add(g_new)

        # Existing albums ----------------------------------------------------------------------------
        self.g_list = Adw.PreferencesGroup(title=_('Albumy w iCloud'),
                                           description=_('Najpierw te, które pasują do celu podróży.'))
        self.search = Gtk.SearchEntry(placeholder_text=_('Szukaj albumu…'), margin_bottom=8)
        self.search.connect("search-changed", lambda *_: self._fill())
        self.g_list.add(self.search)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.listbox.connect("row-activated", lambda _lb, row: self._choose(row.album_name))
        self.g_list.add(self.listbox)
        self.list_status = Adw.ActionRow(title=_('Wczytuję albumy…'))
        self.listbox.append(self.list_status)
        page.add(self.g_list)

        self._load_albums()

    def _tz_range(self):
        a, b = self.from_row.get_value(), self.to_row.get_value()
        if not a or not b:
            return None, None
        start = datetime.fromisoformat(a).replace(tzinfo=ZoneInfo(self.info.origin.tz))
        end = datetime.combine(date.fromisoformat(b), datetime.max.time()).replace(
            microsecond=0, tzinfo=ZoneInfo(self.info.dest.tz))
        if end < start:
            return None, None
        return start, end

    def _error(self, result):
        login = result.get("error") == "login_required"
        self.banner.set_title(photos.error_text(result))
        self.banner.set_button_label(_('Otwórz iCloud Photos') if login else None)
        self.banner.set_revealed(True)

    # albums ---------------------------------------------------------------------------------------
    def _load_albums(self, force=False):
        self.refresh_btn.set_sensitive(False)
        self.calls.append(photos.load_albums(self._albums_loaded, force=force))

    def _albums_loaded(self, result):
        self.refresh_btn.set_sensitive(True)
        if not result.get("ok"):
            self._error(result)
        else:
            self.banner.set_revealed(False)
        self.albums = photos.suggest(result.get("albums", []), self.info)
        self._fill()
        return False

    def _fill(self):
        self.listbox.remove_all()
        q = self.search.get_text().strip().lower()
        shown = 0
        from .airports import CITY_PL, _norm
        keys = {_norm(x) for x in (self.info.dest.city, CITY_PL.get(self.info.dest.city, ""),
                                   self.info.dest.country, self.info.dest.iata) if x and len(x) >= 3}
        for a in self.albums:
            if a.get("smart") and a["name"] not in ("Favorites",):
                continue
            if q and q not in a["name"].lower():
                continue
            row = Adw.ActionRow(title=esc(({"Favorites": "Ulubione"} if IS_PL else {}).get(a["name"], a["name"])),
                                activatable=True)
            row.album_name = a["name"]
            if any(k in _norm(a["name"]) for k in keys):
                row.set_subtitle(_('pasuje do celu podróży'))
            if a["name"] == self.info.trip.album:
                row.add_suffix(Gtk.Image.new_from_icon_name("object-select-symbolic"))
            row.add_prefix(Gtk.Image.new_from_icon_name("folder-pictures-symbolic"))
            self.listbox.append(row)
            shown += 1
            if shown >= 300:
                break
        if not shown:
            self.listbox.append(Adw.ActionRow(title=_('Brak albumów') if not q else _('Nic nie pasuje')))

    def _choose(self, name):
        self.emit("chosen", name)
        self.close()

    # create -----------------------------------------------------------------------------------------
    def _on_check(self, btn):
        start, end = self._tz_range()
        if not start:
            self.toasts.add_toast(Adw.Toast(title=_('Sprawdź daty (Do nie może być przed Od)')))
            return
        btn.set_sensitive(False)
        self.count_row.set_subtitle(_('szukam zdjęć w iCloud…'))

        def done(result):
            btn.set_sensitive(True)
            if not result.get("ok"):
                self.count_row.set_subtitle("—")
                self._error(result)
                return False
            n = result.get("count", 0)
            self.count_row.set_subtitle(f"{n}{'+' if n >= 3000 else ''} {photo_word(n)}" if n else
                                        _('brak zdjęć w tym czasie'))
            self.preview.set_files(result.get("files", []), n)
            return False
        self.calls.append(photos.load_thumbs(None, start, end, done, maxn=7, force=True))

    def _on_create(self, *_a):
        name = self.name_row.get_text().strip()
        start, end = self._tz_range()
        if not name:
            self.toasts.add_toast(Adw.Toast(title=_('Podaj nazwę albumu')))
            return
        if not start:
            self.toasts.add_toast(Adw.Toast(title=_('Sprawdź daty (Do nie może być przed Od)')))
            return
        self.create_btn.set_sensitive(False)
        self.progress.set_visible(True)
        self.progress.set_fraction(0)
        self.progress.set_text(_('szukam zdjęć z tych dni…'))
        pulse = GLib.timeout_add(150, lambda: (self.progress.pulse(), True)[1])
        state = {"pulse": pulse}

        def progress(done, total):
            if state["pulse"]:
                GLib.source_remove(state["pulse"])
                state["pulse"] = 0
            self.progress.set_fraction(done / max(1, total))
            self.progress.set_text(_('dodaję do albumu: {0} / {1}').format(done, total))

        def finished(result):
            if state["pulse"]:
                GLib.source_remove(state["pulse"])
            self.create_btn.set_sensitive(True)
            if not result.get("ok"):
                self.progress.set_visible(False)
                self._error(result)
                return False
            if not result.get("found") and not planned:
                self.progress.set_visible(False)
                self.toasts.add_toast(Adw.Toast(title=_('Brak zdjęć w tym czasie — album nie powstał')))
                return False
            self.progress.set_fraction(1)
            msg = (_('{0} „{1}”: dodano {2}').format(_('Utworzono') if result.get('created') else _('Uzupełniono'), name, result.get('added', 0)))
            if result.get("already"):
                msg += _(', {0} już było').format(result['already'])
            self.progress.set_text(msg)
            photos.forget_thumbs()
            GLib.timeout_add(900, lambda: (self._choose(name), False)[1])
            return False

        planned = self.info.planned and photos.empty_albums_supported()
        self.calls.append(photos.create_album(name, start, end, finished, progress, allow_empty=planned))
