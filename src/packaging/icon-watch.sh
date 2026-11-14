#!/bin/sh
# Linux SkyTrack: small background helper that keeps the app icon (dock, menu) in step with the system
# light/dark theme, also while the app is closed. It does nothing else and does not start the app.
# The light or dark variant is copied to ~/.local/share/icons/hicolor/scalable/apps/linux-skytrack.svg
# (wins over /usr/share).
ID=linux-skytrack
SRC=/usr/share/icons/hicolor/scalable/apps
[ -f "$SRC/$ID-dark.svg" ] && [ -f "$SRC/$ID-light.svg" ] || exit 0
DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

is_dark() {
    case "$(gsettings get org.gnome.desktop.interface color-scheme 2>/dev/null)" in *dark*) return 0 ;; esac
    case "$(gsettings get org.gnome.desktop.interface gtk-theme 2>/dev/null)" in *-dark*|*-Dark*) return 0 ;; esac
    return 1
}

apply() {
    if is_dark; then v=dark; else v=light; fi
    cmp -s "$SRC/$ID-$v.svg" "$DIR/$ID.svg" 2>/dev/null && return 0
    mkdir -p "$DIR" && cp "$SRC/$ID-$v.svg" "$DIR/$ID.svg.tmp" && mv -f "$DIR/$ID.svg.tmp" "$DIR/$ID.svg"
    touch "$DIR" "$DIR/.." "$DIR/../.." 2>/dev/null || true  # make the shell re-read the icon theme
}

apply
gsettings monitor org.gnome.desktop.interface 2>/dev/null | while read -r line; do
    case "$line" in *color-scheme*|*gtk-theme*) apply ;; esac
done
