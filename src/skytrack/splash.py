"""Start-up splash screen (shown while airports, the map and the main window load)."""
import os
import time

from gi.repository import Gdk, Gtk

from .i18n import _
from .version import APP_NAME, VERSION

W, H = 720, 420

CSS = """
window.splash, window.splash > * { background: transparent; box-shadow: none; }
.splash-version { color: #e8eefc; font-weight: 700; font-size: 10.5pt; }
.splash-credit { color: #b9cdf5; font-size: 9.5pt; }
.splash-status { color: #b9cdf5; font-size: 9pt; }
progressbar.splash-progress trough { min-height: 4px; background: alpha(white, .15); border-radius: 2px; }
progressbar.splash-progress progress { min-height: 4px; background: #ff9f43; border-radius: 2px; }
"""

_css_done = False


class Splash(Gtk.Window):
    def __init__(self, app, image):
        super().__init__(application=app, title=APP_NAME, decorated=False, resizable=False,
                         default_width=W, default_height=H, css_classes=["splash"])
        global _css_done
        if not _css_done:
            p = Gtk.CssProvider()
            p.load_from_string(CSS)
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
            _css_done = True
        self.shown_at = time.monotonic()
        over = Gtk.Overlay()
        pic = Gtk.Picture(content_fit=Gtk.ContentFit.FILL, width_request=W, height_request=H,
                          can_shrink=True)
        if os.path.exists(image):
            pic.set_filename(image)
        over.set_child(pic)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.START,
                      valign=Gtk.Align.START, margin_start=44, margin_top=206, width_request=220)
        box.append(Gtk.Label(label=_('Wersja {0}').format(VERSION), xalign=0,
                             css_classes=["splash-version"]))
        box.append(Gtk.Label(label="Created by: JGu · Supported by Claude", xalign=0,
                             css_classes=["splash-credit"]))
        self.bar = Gtk.ProgressBar(fraction=0.05, margin_top=14, css_classes=["splash-progress"])
        box.append(self.bar)
        self.status = Gtk.Label(label=_('Uruchamianie…'), xalign=0, margin_top=4,
                                css_classes=["splash-status"])
        box.append(self.status)
        over.add_overlay(box)
        self.set_child(over)

    def step(self, fraction, text):
        self.bar.set_fraction(fraction)
        self.status.set_label(text)
