"""Backup dialog: create a backup file, restore one, weekly automatic backups."""
import os
from datetime import date, datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from . import backup, cloud, photos
from .i18n import IS_PL, _, plural


def _when(manifest):
    try:
        dt = datetime.fromisoformat(manifest.get("created", ""))
    except ValueError:
        return "?"
    from .stats import nice_date
    return f"{nice_date(dt.date().isoformat())}, {dt:%H:%M}"


def _flights(n):
    return f"{n} {plural(n, 'lot', 'loty', 'lotów', 'flight', 'flights')}"


class BackupDialog(Adw.Dialog):
    __gsignals__ = {
        # emitted after a successful restore: (auth restored?)
        "restored": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self, store, settings):
        super().__init__(title=_('Kopia zapasowa'), content_width=560, content_height=640)
        self.store, self.settings = store, settings
        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()

        g_now = Adw.PreferencesGroup(
            title=_('Kopia teraz'),
            description=_('Jeden plik .skytrack: wszystkie podróże, ustawienia i konto (login i skrót hasła — '
                          'nie samo hasło). Trzymaj go np. na dysku w chmurze albo pendrivie.'))
        row = Adw.ActionRow(title=_('Utwórz kopię zapasową'),
                            subtitle=_('{0} w dzienniku').format(_flights(len(store.all()))))
        row.add_prefix(Gtk.Image(icon_name="document-save-symbolic"))
        btn = Gtk.Button(label=_('Zapisz…'), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        btn.connect("clicked", self._on_create)
        row.add_suffix(btn)
        g_now.add(row)
        page.add(g_now)

        g_res = Adw.PreferencesGroup(
            title=_('Przywracanie'),
            description=_('Zastępuje obecne podróże zawartością kopii. Przed przywróceniem SkyTrack '
                          'sam zapisze kopię obecnego stanu, więc nic nie przepadnie.'))
        self.auth_switch = Adw.SwitchRow(title=_('Przywróć też login i hasło z kopii'), active=True)
        g_res.add(self.auth_switch)
        row = Adw.ActionRow(title=_('Przywróć z pliku'), subtitle=_('plik .skytrack'))
        row.add_prefix(Gtk.Image(icon_name="document-open-symbolic"))
        btn = Gtk.Button(label=_('Wybierz…'), valign=Gtk.Align.CENTER)
        btn.connect("clicked", self._on_pick_restore)
        row.add_suffix(btn)
        g_res.add(row)
        page.add(g_res)

        # cloud ------------------------------------------------------------------------------------
        self.g_cloud = Adw.PreferencesGroup(
            title=_('Kopia w chmurze (opcjonalnie)'),
            description=_('Raz w tygodniu razem z kopią automatyczną (i przyciskiem „Wyślij teraz”) SkyTrack '
                          'wysyła plik .skytrack do chmury. W chmurze zostaje {0} najnowszych kopii; inne '
                          'pliki w folderze nie są ruszane.').format(int(settings["cloud_keep"] or cloud.DEFAULT_KEEP)))
        self.gd_row = Adw.ActionRow(title=_('Dysk Google albo inny folder'))
        self.gd_row.add_prefix(Gtk.Image(icon_name="folder-remote-symbolic"))
        self.gd_off = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                                 tooltip_text=_('Nie wysyłaj na Dysk Google'))
        self.gd_off.connect("clicked", self._gdrive_off)
        gd_pick = Gtk.Button(label=_('Wybierz…'), valign=Gtk.Align.CENTER)
        gd_pick.connect("clicked", self._gdrive_pick)
        self.gd_row.add_suffix(self.gd_off)
        self.gd_row.add_suffix(gd_pick)
        self.g_cloud.add(self.gd_row)
        self.ic_row = Adw.SwitchRow(title=_('iCloud Drive (przez Linux iCloud Photos)'),
                                    active=bool(settings["cloud_icloud"]))
        self.ic_row.add_prefix(Gtk.Image(icon_name="weather-overcast-symbolic"))
        self.ic_row.connect("notify::active", lambda r, _p: (settings.__setitem__("cloud_icloud", r.get_active()),
                                                             self._cloud_status()))
        self.g_cloud.add(self.ic_row)
        self.keep_row = Adw.ComboRow(title=_('Ile kopii trzymać w chmurze'),
                                     model=Gtk.StringList.new(["5", "10", "20"]))
        keep = int(settings["cloud_keep"] or cloud.DEFAULT_KEEP)
        self.keep_row.set_selected({5: 0, 10: 1, 20: 2}.get(keep, 1))
        self.keep_row.connect("notify::selected", lambda r, _p: settings.__setitem__(
            "cloud_keep", (5, 10, 20)[r.get_selected()]))
        self.g_cloud.add(self.keep_row)
        self.send_row = Adw.ActionRow(title=_('Wyślij kopię teraz'))
        self.send_btn = Gtk.Button(label=_('Wyślij'), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        self.send_btn.connect("clicked", self._cloud_send)
        self.send_spin = Gtk.Spinner(valign=Gtk.Align.CENTER)
        self.send_row.add_suffix(self.send_spin)
        self.send_row.add_suffix(self.send_btn)
        self.g_cloud.add(self.send_row)
        page.add(self.g_cloud)
        self._cloud_status()

        self.g_auto = Adw.PreferencesGroup(
            title=_('Kopie automatyczne'),
            description=_('Raz w tygodniu, przy otwarciu aplikacji. SkyTrack trzyma {0} ostatnich '
                          '(plus kopie sprzed przywracania).').format(backup.AUTO_KEEP))
        folder = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER,
                            tooltip_text=_('Otwórz folder z kopiami'), css_classes=["flat"])
        folder.connect("clicked", lambda *_a: Gio.AppInfo.launch_default_for_uri(
            GLib.filename_to_uri(backup.backups_dir(), None), None))
        self.g_auto.set_header_suffix(folder)
        self.auto_switch = Adw.SwitchRow(title=_('Automatyczna kopia co tydzień'),
                                         active=bool(settings["auto_backup"]))
        self.auto_switch.connect("notify::active",
                                 lambda r, _p: settings.__setitem__("auto_backup", r.get_active()))
        self.g_auto.add(self.auto_switch)
        page.add(self.g_auto)
        self._auto_rows = []
        self._fill_auto()

        view.set_content(page)
        self.toasts.set_child(view)
        self.set_child(self.toasts)

    # cloud ----------------------------------------------------------------------------------------
    def _last_text(self, key):
        last = (self.settings["cloud_last"] or {}).get(key)
        if not last:
            return ""
        try:
            dt = datetime.fromisoformat(last["when"])
            from .stats import nice_date
            when = f"{nice_date(dt.date().isoformat())}, {dt:%H:%M}"
        except (KeyError, ValueError):
            when = "?"
        if last.get("ok"):
            return _('ostatnio wysłano: {0}').format(when)
        return _('błąd {0}: {1}').format(when, last.get("msg") or "?")

    def _cloud_status(self):
        uri = self.settings["cloud_gdrive_uri"]
        sub = cloud.describe_uri(uri) if uri else _('wyłączone')
        lt = self._last_text("gdrive") if uri else ""
        self.gd_row.set_subtitle(GLib.markup_escape_text(sub + (f"\n{lt}" if lt else "")))
        self.gd_off.set_visible(bool(uri))
        st = cloud.icloud_state()
        if st == "missing":
            self.ic_row.set_subtitle(_('wymaga aplikacji Linux iCloud Photos 0.16.0+'))
            self.ic_row.set_sensitive(self.ic_row.get_active())
        elif st == "old":
            # never lock the switch on a version guess: say what was found, the upload reports errors
            self.ic_row.set_subtitle(GLib.markup_escape_text(
                _('zaktualizuj Linux iCloud Photos do 0.16.0 lub nowszej') + " · " +
                _('znaleziono: {0}').format(photos.version_text())))
            self.ic_row.set_sensitive(True)
        else:
            lt = self._last_text("icloud") if self.ic_row.get_active() else ""
            base = _('folder „{0}” w iCloud Drive, ta sama sesja co Linux iCloud Photos').format(cloud.FOLDER)
            self.ic_row.set_subtitle(GLib.markup_escape_text(base + (f"\n{lt}" if lt else "")))
            self.ic_row.set_sensitive(True)
        self.send_btn.set_sensitive(cloud.enabled(self.settings))

    def _gdrive_off(self, *_a):
        self.settings["cloud_gdrive_uri"] = ""
        self._cloud_status()

    def _gdrive_pick(self, *_a):
        accounts = cloud.google_accounts()
        if not accounts:
            self._pick_folder(hint=True)
            return
        alert = Adw.AlertDialog(heading=_('Gdzie wysyłać kopie?'),
                                body=_('Na Dysku Google SkyTrack utworzy folder „{0}”.').format(cloud.FOLDER))
        for n, (label, uri) in enumerate(accounts):
            alert.add_response(f"g{n}", _('Dysk Google: {0}').format(label))
        alert.add_response("folder", _('Inny folder…'))
        alert.add_response("cancel", _('Anuluj'))
        alert.set_close_response("cancel")
        alert.set_response_appearance("g0", Adw.ResponseAppearance.SUGGESTED)

        def resp(_d, r):
            if r.startswith("g"):
                self.settings["cloud_gdrive_uri"] = accounts[int(r[1:])][1]
                self._cloud_status()
            elif r == "folder":
                self._pick_folder()
        alert.connect("response", resp)
        alert.present(self)

    def _pick_folder(self, hint=False):
        if hint:
            self.toasts.add_toast(Adw.Toast(
                title=_('Dysk Google: dodaj konto Google w Ustawienia → Konta online (z włączonymi Plikami) '
                        '— pojawi się w wyborze folderu.'), timeout=10))
        dlg = Gtk.FileDialog(title=_('Folder na kopie zapasowe'))

        def done(d, res):
            try:
                f = d.select_folder_finish(res)
            except GLib.Error:
                return
            self.settings["cloud_gdrive_uri"] = f.get_uri()
            self._cloud_status()
        dlg.select_folder(self.get_root(), None, done)

    def _cloud_send(self, *_a):
        self.send_btn.set_sensitive(False)
        self.send_spin.start()
        self.send_row.set_subtitle(_('wysyłam…'))

        def done(results):
            self.send_spin.stop()
            self._cloud_status()
            if results.get("error"):
                self.send_row.set_subtitle(GLib.markup_escape_text(results["error"]))
                return
            names = {"gdrive": _('Dysk Google'), "icloud": "iCloud Drive"}
            parts = []
            for k, r in results.items():
                if r is None:
                    continue
                parts.append(f"{names[k]}: " + (_('wysłano') if r.get("ok") else (r.get("message") or _('błąd'))))
            self.send_row.set_subtitle(GLib.markup_escape_text(" · ".join(parts)))
        cloud.run(self.store, self.settings, done)

    # list of automatic / safety backups --------------------------------------------------------
    def _fill_auto(self):
        for r in self._auto_rows:
            self.g_auto.remove(r)
        self._auto_rows = []
        items = backup.list_backups()
        if not items:
            r = Adw.ActionRow(title=_('Brak zapisanych kopii'), css_classes=["dim-label"])
            self.g_auto.add(r)
            self._auto_rows.append(r)
            return
        kinds = {"auto": _('automatyczna'), "safety": _('sprzed przywracania'), "manual": _('ręczna')}
        for path, m in items[:12]:
            r = Adw.ActionRow(title=_when(m),
                              subtitle=f"{kinds.get(m.get('kind'), '')} · {_flights(m.get('trips', 0))}")
            b = Gtk.Button(label=_('Przywróć'), valign=Gtk.Align.CENTER)
            b.connect("clicked", lambda _b, p=path: self._confirm_restore(p))
            r.add_suffix(b)
            self.g_auto.add(r)
            self._auto_rows.append(r)

    # create ------------------------------------------------------------------------------------
    def _on_create(self, *_a):
        name = f"{'skytrack-kopia' if IS_PL else 'skytrack-backup'}-{date.today().isoformat()}{backup.EXT}"
        dlg = Gtk.FileDialog(title=_('Zapisz kopię zapasową'), initial_name=name)
        dlg.save(self.get_root(), None, self._on_create_file)

    def _on_create_file(self, dlg, res):
        try:
            gfile = dlg.save_finish(res)
        except GLib.Error:
            return
        path = gfile.get_path()
        if not path:
            return
        if not path.endswith(backup.EXT):
            path += backup.EXT
        try:
            m = backup.create(self.store, path)
        except Exception as e:  # disk full, permissions …
            self.toasts.add_toast(Adw.Toast(title=_('Nie udało się zapisać kopii: {0}').format(e), timeout=6))
            return
        self.toasts.add_toast(Adw.Toast(
            title=_('Zapisano kopię: {0} ({1})').format(os.path.basename(path), _flights(m["trips"])), timeout=5))

    # restore -----------------------------------------------------------------------------------
    def _on_pick_restore(self, *_a):
        dlg = Gtk.FileDialog(title=_('Przywróć kopię zapasową'))
        f = Gtk.FileFilter()
        f.set_name(_('Kopia SkyTrack (.skytrack)'))
        f.add_pattern("*.skytrack")
        f.add_pattern("*.zip")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        dlg.set_filters(filters)
        dlg.open(self.get_root(), None, self._on_pick_file)

    def _on_pick_file(self, dlg, res):
        try:
            gfile = dlg.open_finish(res)
        except GLib.Error:
            return
        if gfile.get_path():
            self._confirm_restore(gfile.get_path())

    def _confirm_restore(self, path):
        try:
            m = backup.inspect(path)
        except backup.BackupError:
            self.toasts.add_toast(Adw.Toast(title=_('To nie jest kopia zapasowa SkyTrack'), timeout=5))
            return
        now = len(self.store.all())
        body = [_('Kopia z {0} (SkyTrack {1}): {2}.').format(_when(m), m.get("version", "?"),
                                                             _flights(m.get("trips", 0))),
                _('Obecnie w dzienniku: {0} — zostaną zastąpione. Kopia obecnego stanu zapisze się '
                  'automatycznie przed przywróceniem.').format(_flights(now))]
        with_auth = self.auth_switch.get_active() and m["auth"]
        if with_auth:
            body.append(_('Login i hasło też wrócą do stanu z kopii — po przywróceniu zaloguj się nimi.'))
        alert = Adw.AlertDialog(heading=_('Przywrócić kopię?'), body="\n\n".join(body))
        alert.add_response("cancel", _('Anuluj'))
        alert.add_response("restore", _('Przywróć'))
        alert.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        alert.set_close_response("cancel")

        def on_resp(_d, r):
            if r != "restore":
                return
            try:
                backup.restore(self.store, path, self.settings, include_auth=with_auth)
            except Exception as e:
                self.toasts.add_toast(Adw.Toast(title=_('Nie udało się przywrócić: {0}').format(e), timeout=6))
                return
            self.emit("restored", bool(with_auth))
            self.close()
        alert.connect("response", on_resp)
        alert.present(self)
