"""Lock screen (login / first-run account setup) and the change-password dialog."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from . import auth
from .version import APP_NAME
from .i18n import _


class LockPage(Gtk.Box):
    __gsignals__ = {"unlocked": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        tv = Adw.ToolbarView(vexpand=True)
        tv.add_top_bar(Adw.HeaderBar(show_title=False))
        self.append(tv)
        self.throttle = auth.Throttle()
        self._tick = 0
        self.resetting = False    # after Ubuntu admin authentication: set a new password

        clamp = Adw.Clamp(maximum_size=400, valign=Gtk.Align.CENTER, vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_start=24, margin_end=24, margin_bottom=48)
        clamp.set_child(box)
        tv.set_content(clamp)
        from . import stats
        from .version import RELEASE_DATE, VERSION
        ver = Gtk.Label(label=_('Wersja {0} · wydanie z {1}').format(VERSION, stats.long_date(RELEASE_DATE)),
                        margin_bottom=14, margin_top=6, css_classes=["dim-label", "caption"])
        tv.add_bottom_bar(ver)

        icon = Gtk.Image.new_from_icon_name("linux-skytrack")
        icon.set_pixel_size(96)
        box.append(icon)
        title = Gtk.Label(label=APP_NAME)
        title.add_css_class("title-1")
        box.append(title)
        self.subtitle = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.subtitle.add_css_class("dim-label")
        box.append(self.subtitle)

        self.group = Adw.PreferencesGroup(margin_top=6)
        self.login = Adw.EntryRow(title="Login")
        self.login.add_prefix(Gtk.Image.new_from_icon_name("avatar-default-symbolic"))
        self.password = Adw.PasswordEntryRow(title=_('Hasło'))
        self.password.add_prefix(Gtk.Image.new_from_icon_name("dialog-password-symbolic"))
        self.repeat = Adw.PasswordEntryRow(title=_('Powtórz hasło'))
        self.repeat.add_prefix(Gtk.Image.new_from_icon_name("dialog-password-symbolic"))
        self.hint_row = Adw.EntryRow(title=_('Podpowiedź do hasła (opcjonalnie)'))
        self.hint_row.add_prefix(Gtk.Image.new_from_icon_name("dialog-question-symbolic"))
        for r in (self.login, self.password, self.repeat, self.hint_row):
            self.group.add(r)
        box.append(self.group)

        self.error = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, visible=False)
        self.error.add_css_class("error")
        box.append(self.error)
        self.hint_label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, visible=False,
                                    selectable=True)
        self.hint_label.add_css_class("dim-label")
        box.append(self.hint_label)

        self.button = Gtk.Button(halign=Gtk.Align.CENTER, margin_top=4)
        self.button.add_css_class("pill")
        self.button.add_css_class("suggested-action")
        self.button.connect("clicked", self._submit)
        box.append(self.button)

        self.forgot = Gtk.Button(label=_('Nie pamiętam hasła'), halign=Gtk.Align.CENTER)
        self.forgot.add_css_class("flat")
        self.forgot.connect("clicked", self._on_forgot)
        box.append(self.forgot)
        self.back = Gtk.Button(label=_('Wróć do logowania'), halign=Gtk.Align.CENTER, visible=False)
        self.back.add_css_class("flat")
        self.back.connect("clicked", lambda *_: self._end_reset())
        box.append(self.back)

        self.hint = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.hint.add_css_class("caption")
        self.hint.add_css_class("dim-label")
        box.append(self.hint)

        self.login.connect("entry-activated", lambda *_: self.password.grab_focus())
        self.password.connect("entry-activated", self._on_password_enter)
        self.repeat.connect("entry-activated", lambda *_: self.hint_row.grab_focus())
        self.hint_row.connect("entry-activated", self._submit)
        for r in (self.login, self.password, self.repeat):
            r.connect("changed", lambda *_: self.error.set_visible(False))
        self.reset()

    @property
    def setup(self):
        return self.resetting or not auth.has_account()

    def reset(self):
        """Prepare for showing: clears the password, picks login, first-run or reset mode."""
        self.password.set_text("")
        self.repeat.set_text("")
        self.error.set_visible(False)
        self.hint_label.set_visible(False)
        if self.setup:
            if self.resetting:
                self.subtitle.set_label(_('Hasło administratora Ubuntu potwierdzone.\nUstaw nowe hasło do SkyTrack — podróże zostają.'))
                self.button.set_label(_('Zapisz nowe hasło i otwórz'))
                self.login.set_text(auth.account_login())
                self.hint_row.set_text(auth.hint())
            else:
                self.subtitle.set_label(_('Ustaw login i hasło do SkyTrack.\nBędą potrzebne przy każdym otwarciu aplikacji.'))
                self.button.set_label(_('Utwórz konto i otwórz'))
            self.repeat.set_visible(True)
            self.hint_row.set_visible(True)
            self.forgot.set_visible(False)
            self.back.set_visible(self.resetting)
            self.hint.set_label(_('Hasło: co najmniej {0} znaków. Zapisywany jest tylko jego skrót (PBKDF2), nie samo hasło. Podpowiedź zobaczysz po błędnej próbie logowania — nie wpisuj w niej hasła.').format(auth.MIN_PASSWORD))
        else:
            self.subtitle.set_label(_('Zaloguj się, żeby zobaczyć swoje podróże.'))
            self.button.set_label(_('Zaloguj'))
            self.repeat.set_visible(False)
            self.hint_row.set_visible(False)
            self.forgot.set_visible(True)
            self.back.set_visible(False)
            if not self.login.get_text():
                self.login.set_text(auth.account_login())
            self.hint.set_label("")
        self.hint.set_visible(bool(self.hint.get_label()))
        self._update_wait()

    def focus_first(self):
        if self.resetting:
            target = self.password
        else:
            target = self.password if (not self.setup and self.login.get_text()) else self.login
        GLib.idle_add(lambda: (target.grab_focus(), False)[1])

    def _show_error(self, text):
        self.error.set_label(text)
        self.error.set_visible(True)

    # forgotten password ----------------------------------------------------------------------
    def _on_forgot(self, *_a):
        cmd = auth.system_auth_command()
        if not cmd:
            self._show_error(_('Brak pkexec (polkit) — reset hasłem Ubuntu jest niedostępny. Usuń ~/.config/linux-skytrack/auth.json, żeby założyć konto od nowa.'))
            return
        self.forgot.set_sensitive(False)
        self.forgot.set_label(_('Czekam na hasło administratora Ubuntu…'))
        try:
            proc = Gio.Subprocess.new(cmd, Gio.SubprocessFlags.STDOUT_SILENCE |
                                      Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error as e:
            self._forgot_done(None, e.message)
            return
        proc.wait_async(None, lambda p, res: self._forgot_done(p, res))

    def _forgot_done(self, proc, res):
        self.forgot.set_sensitive(True)
        self.forgot.set_label(_('Nie pamiętam hasła'))
        if proc is None:
            self._show_error(_('Nie udało się uruchomić pkexec: {0}').format(res))
            return
        try:
            proc.wait_finish(res)
            status = proc.get_exit_status() if proc.get_if_exited() else 127
        except GLib.Error:
            status = 127
        result = auth.system_auth_result(status)
        if result == "ok":
            self.resetting = True
            self.throttle.ok()
            self.reset()
            self.focus_first()
        elif result == "cancelled":
            self._show_error(_('Anulowano. Reset wymaga hasła administratora Ubuntu.'))
        else:
            self._show_error(_('Nie udało się potwierdzić hasła administratora Ubuntu (konto bez uprawnień administratora albo złe hasło).'))

    def _end_reset(self):
        self.resetting = False
        self.reset()
        self.focus_first()

    def _on_password_enter(self, *_a):
        if self.setup:
            self.repeat.grab_focus()
        else:
            self._submit()

    def _update_wait(self):
        left = self.throttle.wait_left()
        self.button.set_sensitive(left == 0)
        if left:
            self._show_error(_('Za dużo nieudanych prób. Spróbuj za {0} s.').format(left))
            if not self._tick:
                self._tick = GLib.timeout_add_seconds(1, self._tick_cb)
        return left

    def _tick_cb(self):
        if self._update_wait():
            return True
        self._tick = 0
        self.error.set_visible(False)
        return False

    def _submit(self, *_a):
        if self._update_wait():
            return
        login, pw = self.login.get_text(), self.password.get_text()
        if self.setup:
            hint_text = self.hint_row.get_text().strip()
            err = auth.validate_new(login, pw, self.repeat.get_text(), hint_text)
            if err:
                self._show_error(err)
                return
            auth.save(login, pw, hint_text)
            self.resetting = False
        elif not auth.verify(login, pw):
            self.throttle.failed()
            self.password.set_text("")
            if not self._update_wait():
                self._show_error(_('Nieprawidłowy login lub hasło'))
            h = auth.hint()
            if h:
                self.hint_label.set_label(_('Podpowiedź: {0}').format(h))
                self.hint_label.set_visible(True)
            self.password.grab_focus()
            return
        self.throttle.ok()
        self.hint_label.set_visible(False)
        self.password.set_text("")
        self.repeat.set_text("")
        self.emit("unlocked")


class ChangePasswordDialog(Adw.Dialog):
    def __init__(self):
        super().__init__(title=_('Login i hasło'), content_width=440)
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label=_('Anuluj'))
        cancel.connect("clicked", lambda *_: self.close())
        self.save_btn = Gtk.Button(label=_('Zapisz'))
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._save)
        hb.pack_start(cancel)
        hb.pack_end(self.save_btn)
        tv.add_top_bar(hb)
        self.toasts = Adw.ToastOverlay()
        page = Adw.PreferencesPage()
        self.toasts.set_child(page)
        tv.set_content(self.toasts)
        self.set_child(tv)

        g1 = Adw.PreferencesGroup(description=_('Najpierw obecne hasło.'))
        self.current = Adw.PasswordEntryRow(title=_('Obecne hasło'))
        g1.add(self.current)
        page.add(g1)
        g2 = Adw.PreferencesGroup(title=_('Nowe dane'),
                                  description=_('Hasło: co najmniej {0} znaków.').format(auth.MIN_PASSWORD))
        self.login = Adw.EntryRow(title="Login")
        self.login.set_text(auth.account_login())
        self.new = Adw.PasswordEntryRow(title=_('Nowe hasło'))
        self.repeat = Adw.PasswordEntryRow(title=_('Powtórz nowe hasło'))
        self.hint_row = Adw.EntryRow(title=_('Podpowiedź do hasła (opcjonalnie)'))
        self.hint_row.set_text(auth.hint())
        for r in (self.login, self.new, self.repeat, self.hint_row):
            g2.add(r)
        page.add(g2)
        self.repeat.connect("entry-activated", self._save)
        self.set_focus(self.current)
        self.saved = False

    def _save(self, *_a):
        if not auth.verify(auth.load()["login"], self.current.get_text()):
            self.toasts.add_toast(Adw.Toast(title=_('Obecne hasło jest nieprawidłowe')))
            self.current.add_css_class("error")
            return
        hint_text = self.hint_row.get_text().strip()
        err = auth.validate_new(self.login.get_text(), self.new.get_text(), self.repeat.get_text(),
                                hint_text)
        if err:
            self.toasts.add_toast(Adw.Toast(title=err))
            return
        auth.save(self.login.get_text(), self.new.get_text(), hint_text)
        self.saved = True
        self.close()
