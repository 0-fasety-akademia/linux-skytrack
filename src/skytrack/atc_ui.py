"""LIVE tower radio: header control, the mini window in the corner and the feed-list check."""
import json
import os

import gi

gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gio, GLib, GObject, Gtk, WebKit  # noqa: E402

from . import atc, db  # noqa: E402
from .i18n import _  # noqa: E402

_session = None


def session():
    """One persistent web session, so LiveATC's "human" check is passed once."""
    global _session
    if _session is None:
        _session = WebKit.NetworkSession.new(os.path.join(db.data_dir(), "webkit-live"),
                                             os.path.join(db.cache_dir(), "webkit-live"))
    return _session


def _web(height, own_policy=None):
    # sound may start without a click (the person pressed LIVE); WebKit's default mutes it
    policies = WebKit.WebsitePolicies(autoplay=WebKit.AutoplayPolicy.ALLOW)
    web = WebKit.WebView(network_session=session(), website_policies=policies,
                         hexpand=True, height_request=height)
    s = web.get_settings()
    s.set_media_playback_requires_user_gesture(False)
    s.set_enable_developer_extras(bool(os.environ.get("SKYTRACK_DEVTOOLS")))
    if own_policy:
        web.connect("decide-policy", own_policy)
    web.connect("decide-policy", _policy)
    return web


def _policy(_web, decision, dtype):
    if dtype == WebKit.PolicyDecisionType.NEW_WINDOW_ACTION:
        uri = decision.get_navigation_action().get_request().get_uri()
        if uri.startswith(("http://", "https://")):
            Gio.AppInfo.launch_default_for_uri(uri, None)
        decision.ignore()
        return True
    return False


def _open(uri):
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error as e:
        print("open failed:", e)


class MiniPlayer(Gtk.Box):
    """Small card in the window's corner with the listening page."""

    __gsignals__ = {"closed": (GObject.SignalFlags.RUN_FIRST, None, ()),
                    "to-browser": (GObject.SignalFlags.RUN_FIRST, None, ()),
                    "mount-found": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
                    "collapsed-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,))}

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=["card", "atc-mini"],
                         halign=Gtk.Align.END, valign=Gtk.Align.END,
                         margin_end=14, margin_bottom=14, visible=False)
        bar = Gtk.Box(spacing=4, margin_start=4, margin_end=4, margin_top=4, margin_bottom=2)
        self.title = Gtk.Button(css_classes=["flat", "atc-mini-title"], hexpand=True,
                                tooltip_text=_('Otwórz w przeglądarce'))
        tbox = Gtk.Box(spacing=6)
        tbox.append(Gtk.Label(label="●", css_classes=["atc-dot"]))
        self.label = Gtk.Label(xalign=0, ellipsize=3, hexpand=True)
        tbox.append(self.label)
        self.state_label = Gtk.Label(css_classes=["caption", "dim-label", "atc-state"])
        tbox.append(self.state_label)
        tbox.append(Gtk.Image(icon_name="adw-external-link-symbolic"))
        self.title.set_child(tbox)
        self.title.connect("clicked", lambda *_a: self.emit("to-browser"))
        bar.append(self.title)
        self.fold = Gtk.Button(icon_name="go-down-symbolic", css_classes=["flat", "circular"],
                               tooltip_text=_('Zwiń do paska (dźwięk gra dalej)'))
        self.fold.connect("clicked", lambda *_a: self.set_collapsed(not self.collapsed))
        bar.append(self.fold)
        close = Gtk.Button(icon_name="window-close-symbolic", css_classes=["flat", "circular"],
                           tooltip_text=_('Wyłącz nasłuch'))
        close.connect("clicked", lambda *_a: self.emit("closed"))
        bar.append(close)
        self.append(bar)
        self.web = _web(230, self._on_policy)
        self.web.set_zoom_level(0.8)
        self.web.connect("load-changed", self._on_load)
        self.web.connect("web-process-terminated", self._on_web_crash)
        # the page lives in a clip box: collapsing shrinks the box, the page itself keeps
        # its size and keeps playing
        self.holder = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                         vscrollbar_policy=Gtk.PolicyType.EXTERNAL,
                                         child=self.web, width_request=360, height_request=230)
        self.append(self.holder)
        self.uri = None
        self.feed = ""
        self.collapsed = False
        self._poll_id = 0
        self._tries = 0
        self._buffering = 0
        self._state = ""

    def set_collapsed(self, on):
        """Shrink to the title bar. The page stays loaded (just 1 px tall), so it keeps playing."""
        self.collapsed = bool(on)
        self.holder.set_size_request(260 if on else 360, 1 if on else 230)
        self.holder.set_opacity(0 if on else 1)
        self.holder.set_can_target(not on)
        self.fold.set_icon_name("go-up-symbolic" if on else "go-down-symbolic")
        self.fold.set_tooltip_text(_('Rozwiń okienko') if on else _('Zwiń do paska (dźwięk gra dalej)'))
        if on:
            self.add_css_class("collapsed")
        else:
            self.remove_css_class("collapsed")
        self.emit("collapsed-changed", self.collapsed)

    def play(self, name, uri, feed=""):
        self.uri = uri
        self._reloaded = False
        self._tries = 0
        self._buffering = 0
        self._state = ""
        self.state_label.set_label(_('łączenie…'))
        self.feed = feed
        self.label.set_label(name)
        self.set_visible(True)
        self.web.load_uri(uri)

    def stop(self):
        self.uri = None
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = 0
        self._state = ""
        self.state_label.set_label("")
        self.remove_css_class("playing")
        self.web.load_uri("about:blank")
        self.set_visible(False)

    def _on_policy(self, web, decision, dtype):
        # LiveATC opens its player in a pop-up: keep it in the mini window instead
        if dtype == WebKit.PolicyDecisionType.NEW_WINDOW_ACTION and self.uri:
            uri = decision.get_navigation_action().get_request().get_uri()
            if "liveatc.net" in uri and "listen" in uri:
                decision.ignore()
                self.web.load_uri(uri)
                return True
        return False

    def _on_load(self, web, event):
        if event != WebKit.LoadEvent.FINISHED or not self.uri:
            return
        cur = web.get_uri() or ""
        if "/search/" in cur:
            # airport page (player address not known yet): find the feed and open its player
            for delay in (600, 2500):
                GLib.timeout_add(delay, self._pick)
            return
        self._tries = 0
        self._buffering = 0
        if not self._poll_id:
            self._poll_id = GLib.timeout_add(2000, self._player_poll)

    def _pick(self):
        if self.uri and "/search/" in (self.web.get_uri() or ""):
            self.web.evaluate_javascript(atc.pick_js(self.feed), -1, None, None, None, self._on_pick)
        return False

    def _on_pick(self, web, res):
        try:
            f = json.loads(web.evaluate_javascript_finish(res).to_string())
        except (GLib.Error, ValueError, TypeError):
            return
        if not f or not f.get("mount") or "/search/" not in (web.get_uri() or ""):
            return
        icao = (f.get("icao") or "").lower() or self.feed[:4].lower()
        self.emit("mount-found", self.feed, f["mount"])
        self.web.load_uri(f"{atc.LIVEATC}/hlisten.php?mount={f['mount']}&icao={icao}")

    def _on_web_crash(self, web, reason):
        """The page's web process died (it runs apart from SkyTrack): reload it once."""
        print("LIVE page process ended:", reason)
        if self.uri and not getattr(self, "_reloaded", False):
            self._reloaded = True
            GLib.timeout_add(1000, lambda: (self.uri and self.web.load_uri(self.uri), False)[1])

    def _player_poll(self):
        """Start the page's player, then keep showing its state in the title bar."""
        if not self.uri or self.web.get_uri() in (None, "about:blank"):
            self._poll_id = 0
            return False
        if self._tries >= 6:
            mode = "check"
        elif self._buffering >= 4:
            mode = "force"
            self._buffering = 0
        else:
            mode = "start"
        js = atc.PLAYER_JS % mode
        self.web.evaluate_javascript(js, -1, None, None, None, self._on_player)
        return True

    def _on_player(self, web, res):
        try:
            state = web.evaluate_javascript_finish(res).to_string()
        except (GLib.Error, TypeError):
            return
        if state == "clicked":
            self._tries += 1
            self._buffering = 0
        elif state == "buffering":
            self._buffering += 1              # 4 polls (~8 s) stuck: press Play again
        elif state == "playing":
            self._buffering = 0
        self._set_state(state)

    def _set_state(self, state):
        verify = state == "verify"
        if verify != getattr(self, "_verify", False):
            # LiveATC's "are you human" check: show the whole page until it is passed
            self._verify = verify
            if verify:
                self.holder.set_size_request(480, 440)
                self.holder.set_opacity(1)
                self.holder.set_can_target(True)
                self.web.set_size_request(-1, 440)
                self.web.set_zoom_level(0.75)
            else:
                self.web.set_size_request(-1, 230)
                self.web.set_zoom_level(0.8)
                self.set_collapsed(self.collapsed)
        if verify:
            self._tries = 0
            self.state_label.set_label(_('potwierdzenie LiveATC…'))
            return
        self._state = state
        txt = {"playing": _('gra'), "buffering": _('łączenie…'), "clicked": _('łączenie…')}.get(
            state, _('wciśnij Play w okienku') if self._tries >= 6 else _('łączenie…'))
        self.state_label.set_label(txt)
        if state == "playing":
            self.add_css_class("playing")
        else:
            self.remove_css_class("playing")


class ScanDialog(Adw.Dialog):
    """Opens LiveATC's feed list and reads it once the page is there."""

    __gsignals__ = {"found": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    TIMEOUT = 120

    def __init__(self):
        super().__init__(title=_('Sprawdzanie nowych wież'), content_width=820, content_height=680)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_start=12, margin_end=12, margin_bottom=12)
        self.status = Gtk.Label(
            label=_('Wczytuję listę kanałów LiveATC… Jeśli pojawi się „Potwierdź, że jesteś '
                    'człowiekiem”, zaznacz to pole.'), wrap=True, xalign=0)
        box.append(self.status)
        self.web = _web(400)
        self.web.set_zoom_level(0.8)
        self.web.set_vexpand(True)
        frame = Gtk.Frame(child=self.web)
        box.append(frame)
        tv.set_content(box)
        self.set_child(tv)
        self._ticks = 0
        self._busy = False
        self._done = False
        self.web.load_uri(atc.INDEX_URL)
        self._timer = GLib.timeout_add(1500, self._poll)
        self.connect("closed", self._on_closed)

    def _on_closed(self, *_a):
        self._done = True
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _poll(self):
        if self._done:
            return False
        self._ticks += 1
        if self._ticks * 1.5 > self.TIMEOUT:
            self._timer = 0
            self.status.set_label(_('Nie udało się wczytać listy. Spróbuj ponownie później.'))
            return False
        if not self._busy:
            self._busy = True
            self.web.evaluate_javascript(atc.SCAN_JS, -1, None, None, None, self._on_js)
        return True

    def _on_js(self, web, res):
        self._busy = False
        try:
            data = json.loads(web.evaluate_javascript_finish(res).to_string())
        except (GLib.Error, ValueError, TypeError):
            return
        if self._done or not data.get("ready"):
            return
        feeds = data.get("feeds") or []
        if not feeds:
            return
        self._done = True
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self.emit("found", json.dumps(feeds))
        self.close()


class AtcControl(Gtk.Box):
    """LIVE toggle + source menu in the header bar."""

    __gsignals__ = {"message": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self, settings, airports):
        super().__init__(css_classes=["linked", "atc-control"])
        self.settings = settings
        self.airports = airports
        self.data = atc.load()
        self.items = []
        self._syncing = False
        self.mini = MiniPlayer()
        self.mini.connect("closed", lambda *_a: self.turn_off())
        self.mini.connect("to-browser", self._to_browser)
        self.mini.connect("mount-found", self._on_mount)
        self.mini.set_collapsed(bool(self.settings["atc_collapsed"]))
        self.mini.connect("collapsed-changed", lambda _m, on: self.settings.__setitem__("atc_collapsed", on))

        self.live = Gtk.ToggleButton(css_classes=["atc-live"], tooltip_text=_('Nasłuch wieży na żywo'))
        inner = Gtk.Box(spacing=6)
        inner.append(Gtk.Label(label="●", css_classes=["atc-dot"]))
        inner.append(Gtk.Label(label="LIVE"))
        self.live.set_child(inner)
        self.live.connect("toggled", self._on_toggle)
        self.append(self.live)

        self.menu = Gtk.MenuButton(icon_name="pan-down-symbolic", tooltip_text=_('Wybierz wieżę'))
        self.menu.set_popover(self._build_popover())
        self.append(self.menu)
        self._fill()

    # Popover -----------------------------------------------------------------------------------
    def _build_popover(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, width_request=360,
                      margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        box.append(Gtk.Label(label=_('Nasłuch wieży na żywo'), xalign=0, css_classes=["heading"]))

        self.model = Gtk.StringList()
        self.source = Gtk.DropDown(model=self.model)
        self.source.set_enable_search(True)
        exp = Gtk.PropertyExpression.new(Gtk.StringObject, None, "string")
        self.source.set_expression(exp)
        self.source.connect("notify::selected", self._on_source)
        box.append(self.source)

        self.info = Gtk.Label(xalign=0, wrap=True, max_width_chars=44, css_classes=["dim-label", "caption"])
        box.append(self.info)

        eu = Gtk.Box(spacing=8)
        eu.append(Gtk.Label(label=_('Także inne kraje Europy'), xalign=0, hexpand=True))
        self.eu = Gtk.Switch(active=bool(self.settings["atc_all_eu"]), valign=Gtk.Align.CENTER)
        self.eu.connect("notify::active", self._on_eu)
        eu.append(self.eu)
        box.append(eu)

        check = Gtk.Button(label=_('Sprawdź nowe wieże'))
        check.connect("clicked", lambda *_a: self.check_new())
        box.append(check)

        box.append(Gtk.Separator())
        box.append(Gtk.Label(label=_('Dodaj własne źródło (URL)'), xalign=0, css_classes=["heading"]))
        self.c_name = Gtk.Entry(placeholder_text=_('Nazwa, np. Gdańsk – kamera'))
        self.c_url = Gtk.Entry(placeholder_text="https://…", input_purpose=Gtk.InputPurpose.URL)
        self.c_url.connect("activate", self._add_custom)
        box.append(self.c_name)
        row = Gtk.Box(spacing=6)
        self.c_url.set_hexpand(True)
        row.append(self.c_url)
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text=_('Dodaj'))
        add.connect("clicked", self._add_custom)
        row.append(add)
        box.append(row)
        self.remove = Gtk.Button(label=_('Usuń wybrane własne źródło'), css_classes=["destructive-action"])
        self.remove.connect("clicked", self._remove_custom)
        box.append(self.remove)

        box.append(Gtk.Label(
            label=_('Odsłuch pochodzi z oficjalnej strony LiveATC.net (lub z dodanej przez Ciebie '
                    'strony) i działa jak w przeglądarce. SkyTrack niczego nie nagrywa ani nie '
                    'zapisuje. Po zminimalizowaniu okna nasłuch się wyłącza.'),
            xalign=0, wrap=True, max_width_chars=44, css_classes=["caption", "dim-label"]))
        return Gtk.Popover(child=box)

    # Data ----------------------------------------------------------------------------------------
    def _label(self, st):
        if st.get("url"):
            return "★ " + st["name"]
        ap = self.airports.get(st["icao"])
        city = ""
        if ap:
            from .wrapped import city as city_name
            city = city_name(ap) + " · "
        off = "" if st.get("status") == "UP" else "  — " + _('offline')
        return f"{city}{st['name']}{off}"

    def _fill(self):
        all_eu = bool(self.settings["atc_all_eu"])
        towers = [s for s in self.data["stations"]
                  if all_eu or s["icao"].startswith(atc.HOME_PREFIX)]
        towers.sort(key=lambda s: (s.get("status") != "UP" and not all_eu,
                                   not s["icao"].startswith(atc.HOME_PREFIX), s["icao"], s["name"]))
        custom = [dict(c, icao="") for c in (self.settings["atc_custom"] or [])
                  if isinstance(c, dict) and c.get("url")]
        self.items = custom + towers
        self._syncing = True
        self.model.splice(0, self.model.get_n_items(), [self._label(s) for s in self.items])
        want = self.settings["atc_source"]
        idx = next((i for i, s in enumerate(self.items) if atc.key(s) == want), None)
        if idx is None:   # default: first working Polish tower, Gdańsk if it is up
            idx = next((i for i, s in enumerate(self.items)
                        if s.get("icao") == "EPGD" and s.get("status") == "UP"), None)
        if idx is None:
            idx = next((i for i, s in enumerate(self.items) if s.get("status") == "UP"), 0)
        if self.items:
            self.source.set_selected(idx)
        self._syncing = False
        self._update_info()

    def current(self):
        i = self.source.get_selected()
        return self.items[i] if 0 <= i < len(self.items) else None

    def _update_info(self):
        st = self.current()
        checked = self.data.get("checked", "")
        lines = []
        if st and not st.get("url"):
            lines.append(_('Stan kanału przy ostatnim sprawdzeniu: {0}').format(
                _('działa') if st.get("status") == "UP" else _('offline')))
        if checked:
            lines.append(_('Lista wież sprawdzona: {0}').format(checked))
        self.info.set_label("\n".join(lines))
        self.remove.set_visible(bool(st and st.get("url")))

    # Handlers ----------------------------------------------------------------------------------
    def _on_toggle(self, btn):
        if self._syncing:
            return
        if btn.get_active():
            self._play()
        else:
            self.turn_off()

    def _play(self):
        st = self.current()
        if not st:
            self._set_live(False)
            return
        self.mini.play(self._label(st), atc.listen_url(st), "" if st.get("url") else st["name"])
        self.live.add_css_class("on")

    def _set_live(self, on):
        self._syncing = True
        self.live.set_active(on)
        self._syncing = False
        (self.live.add_css_class if on else self.live.remove_css_class)("on")

    def _on_source(self, *_a):
        if self._syncing:
            return
        st = self.current()
        if st:
            self.settings["atc_source"] = atc.key(st)
        self._update_info()
        if self.live.get_active():
            self._play()

    def _on_eu(self, sw, *_a):
        self.settings["atc_all_eu"] = sw.get_active()
        self._fill()

    def _add_custom(self, *_a):
        url = self.c_url.get_text().strip()
        if not url.startswith(("https://", "http://")):
            self.emit("message", _('Podaj pełny adres zaczynający się od https://'))
            return
        name = self.c_name.get_text().strip() or url.split("/")[2]
        custom = [c for c in (self.settings["atc_custom"] or []) if c.get("url") != url]
        custom.append({"name": name[:60], "url": url})
        self.settings["atc_custom"] = custom
        self.settings["atc_source"] = url
        self.c_name.set_text("")
        self.c_url.set_text("")
        self._fill()
        self.emit("message", _('Dodano źródło: {0}').format(name))

    def _remove_custom(self, *_a):
        st = self.current()
        if not st or not st.get("url"):
            return
        self.settings["atc_custom"] = [c for c in (self.settings["atc_custom"] or [])
                                       if c.get("url") != st["url"]]
        if self.live.get_active():
            self.turn_off()
        self._fill()

    def _on_mount(self, _mini, name, mount):
        """Remember the player address found on an airport page."""
        for s in self.data["stations"]:
            if s["name"] == name and s.get("mount") != mount:
                s["mount"] = mount
                s["status"] = "UP"
                try:
                    atc.save(self.data)
                except OSError as e:
                    print("stations save failed:", e)
                break

    def _to_browser(self, *_a):
        uri = self.mini.uri
        self.turn_off()          # no double sound: the browser takes over
        if uri:
            _open(uri)

    # Public ------------------------------------------------------------------------------------
    def turn_off(self):
        self.mini.stop()
        self._set_live(False)

    def check_new(self):
        self.menu.popdown()
        dlg = ScanDialog()
        dlg.connect("found", self._on_found)
        dlg.present(self.get_root())

    def _on_found(self, _dlg, payload):
        try:
            found = json.loads(payload)
        except ValueError:
            return
        data, new = atc.merge_scan(self.data, found)
        if data is self.data:
            self.emit("message", _('Nie znaleziono kanałów na liście LiveATC.'))
            return
        self.data = data
        try:
            atc.save(data)
        except OSError as e:
            print("stations save failed:", e)
        self._fill()
        home_new = [n for n in new if n[:2] == atc.HOME_PREFIX]
        if new:
            shown = home_new or new
            self.emit("message", _('Nowe wieże: {0}').format(", ".join(shown[:4])
                                                             + ("…" if len(shown) > 4 else "")))
        else:
            self.emit("message", _('Brak nowych wież. Stan kanałów zaktualizowany.'))
