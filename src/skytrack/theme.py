"""Look & feel: System (follows light/dark), Flighty (night board), Matrix (green phosphor)."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk
from .i18n import _

THEMES = {"system": _('Systemowy (jasny / ciemny)'), "flighty": "Flighty", "matrix": "Matrix"}

BASE = """
.atc-live .atc-dot { color: alpha(currentColor, .35); font-size: 9pt; }
.atc-live { font-weight: 800; letter-spacing: .04em; }
.atc-live.on { background: #e01b24; color: white; }
.atc-live.on .atc-dot { color: white; animation: atc-pulse 1.2s ease-in-out infinite; }
.atc-mini { padding: 0; box-shadow: 0 6px 24px alpha(black, .35); }
.atc-mini .atc-dot { color: #e01b24; animation: atc-pulse 1.2s ease-in-out infinite; }
.atc-mini-title { font-weight: 700; padding: 4px 8px; }
.atc-mini .atc-dot { opacity: .45; }
.atc-mini.playing .atc-dot { opacity: 1; }
.atc-state { margin-left: 2px; }
.atc-mini.collapsed { border-radius: 18px; }
@keyframes atc-pulse { 0% { opacity: 1; } 50% { opacity: .25; } 100% { opacity: 1; } }
.stat-card { padding: 14px 16px; }
.trip-icon { color: @accent_color; }
.trip-icon.planned { color: @warning_color; }
.trip-sidebar { background: @sidebar_bg_color; }

.km-counter { font-size: 34px; font-weight: 800; font-feature-settings: "tnum"; }
.period { font-size: 11px; font-weight: 800; letter-spacing: 2px; opacity: .6; }

.pass { padding: 14px 16px 14px 16px; border-radius: 16px; }
.pass-top { font-size: 12px; font-weight: 700; opacity: .75; }
.pass-code { font-size: 30px; font-weight: 800; letter-spacing: 1px; }
.pass-city { font-size: 12px; opacity: .7; }
.pass-label { font-size: 9px; font-weight: 800; letter-spacing: 1.5px; opacity: .55; }
.pass-value { font-size: 15px; font-weight: 700; font-feature-settings: "tnum"; }
.pass-sub { font-size: 10px; opacity: .6; font-feature-settings: "tnum"; }
.pass-sep { border-top: 1px dashed alpha(currentColor, .25); margin: 8px 0 6px 0; min-height: 0; background: none; }

.badge { border-radius: 99px; padding: 2px 10px; font-weight: 800; font-size: 11px;
         background: alpha(@accent_bg_color, .18); color: @accent_color; }
.badge.planned { background: alpha(@warning_color, .18); color: @warning_color; }
.badge.flown { background: alpha(@success_color, .16); color: @success_color; }
.code { font-weight: 800; letter-spacing: .5px; font-feature-settings: "tnum"; }
.numeric { font-feature-settings: "tnum"; }
.thumb { border-radius: 10px; }
.clickable-card:hover { background-image: linear-gradient(alpha(@accent_bg_color, .10), alpha(@accent_bg_color, .10)); }
.clickable-card:active { background-image: linear-gradient(alpha(@accent_bg_color, .18), alpha(@accent_bg_color, .18)); }
.thumb-more { background: alpha(black, .55); color: white; font-weight: 800; font-size: 14px; }
.album-icon { color: @accent_color; }
.section-title { font-size: 11px; font-weight: 800; letter-spacing: 1.5px; opacity: .55; }
"""

SYSTEM = """
.pass {
  background-image: linear-gradient(135deg, alpha(@accent_bg_color, .14), alpha(@accent_bg_color, .02));
  background-color: @card_bg_color;
  box-shadow: 0 1px 3px alpha(black, .12), 0 0 0 1px alpha(black, .04);
}
"""

FLIGHTY = """
@define-color accent_bg_color #4f7cff;
@define-color accent_color #8eaaff;
@define-color accent_fg_color #ffffff;
@define-color window_bg_color #07090f;
@define-color window_fg_color #f2f4ff;
@define-color view_bg_color #07090f;
@define-color view_fg_color #f2f4ff;
@define-color headerbar_bg_color #0b0e18;
@define-color headerbar_fg_color #f2f4ff;
@define-color headerbar_backdrop_color #07090f;
@define-color sidebar_bg_color #0b0e18;
@define-color sidebar_fg_color #f2f4ff;
@define-color card_bg_color #121726;
@define-color card_fg_color #f2f4ff;
@define-color popover_bg_color #141a2b;
@define-color popover_fg_color #f2f4ff;
@define-color dialog_bg_color #0e1220;
@define-color dialog_fg_color #f2f4ff;
@define-color warning_color #ffc83d;
@define-color success_color #3ddc84;

.pass {
  background-image: linear-gradient(160deg, #1d2645 0%, #121829 55%, #0d1120 100%);
  border: 1px solid alpha(white, .07);
  box-shadow: 0 10px 30px alpha(black, .5), inset 0 1px alpha(white, .05);
}
.pass-code { font-size: 34px; color: #ffffff; }
.km-counter { color: #ffffff; }
.badge.flown { background: alpha(#4f7cff, .22); color: #b4c6ff; }
.stat-card { background-image: linear-gradient(160deg, #161d33, #10141f); border: 1px solid alpha(white, .05); }
"""

MATRIX = """
@define-color accent_bg_color #00b33c;
@define-color accent_color #39ff6a;
@define-color accent_fg_color #000000;
@define-color window_bg_color #000000;
@define-color window_fg_color #8dffa9;
@define-color view_bg_color #000000;
@define-color view_fg_color #8dffa9;
@define-color headerbar_bg_color #010a03;
@define-color headerbar_fg_color #8dffa9;
@define-color headerbar_backdrop_color #000000;
@define-color sidebar_bg_color #010802;
@define-color sidebar_fg_color #8dffa9;
@define-color card_bg_color #021006;
@define-color card_fg_color #8dffa9;
@define-color popover_bg_color #021006;
@define-color popover_fg_color #8dffa9;
@define-color dialog_bg_color #010a03;
@define-color dialog_fg_color #8dffa9;
@define-color warning_color #c6ff00;
@define-color success_color #39ff6a;
@define-color destructive_bg_color #b3001e;

window, dialog, popover, .pass, label, entry, button {
  font-family: "DejaVu Sans Mono", "Ubuntu Mono", "Noto Sans Mono", monospace;
}
.pass {
  background-color: #010d04;
  background-image: repeating-linear-gradient(0deg, alpha(#00ff41, .035) 0px, alpha(#00ff41, .035) 1px,
                                              transparent 1px, transparent 3px);
  border: 1px solid alpha(#00ff41, .35);
  box-shadow: 0 0 18px alpha(#00ff41, .15), inset 0 0 24px alpha(#00ff41, .05);
}
.pass-code, .km-counter { color: #b8ffcb; text-shadow: 0 0 6px #00ff41, 0 0 14px alpha(#00ff41, .6); }
.pass-value { color: #b8ffcb; }
.card, .stat-card, .boxed-list { border: 1px solid alpha(#00ff41, .22); box-shadow: 0 0 10px alpha(#00ff41, .08); }
.title-1, .title-2 { text-shadow: 0 0 6px alpha(#00ff41, .7); }
.badge { background: alpha(#00ff41, .12); color: #39ff6a; border: 1px solid alpha(#00ff41, .4); }
.badge.planned { color: #c6ff00; border-color: alpha(#c6ff00, .4); background: alpha(#c6ff00, .08); }
"""

_providers = {}


def apply(name):
    """Install CSS + colour scheme for the theme. Safe to call repeatedly."""
    display = Gdk.Display.get_default()
    if "base" not in _providers:
        p = Gtk.CssProvider()
        p.load_from_string(BASE)
        Gtk.StyleContext.add_provider_for_display(display, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        _providers["base"] = p
        t = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, t, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        _providers["theme"] = t
    css = {"flighty": FLIGHTY, "matrix": MATRIX}.get(name, SYSTEM)
    _providers["theme"].load_from_string(css)
    sm = Adw.StyleManager.get_default()
    sm.set_color_scheme(Adw.ColorScheme.FORCE_DARK if name in ("flighty", "matrix")
                        else Adw.ColorScheme.DEFAULT)
