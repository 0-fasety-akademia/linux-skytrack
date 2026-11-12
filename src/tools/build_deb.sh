#!/bin/bash
# Build linux-skytrack_<version>_all.deb into ./dist
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "import re;print(re.search(r'VERSION = \"(.+?)\"', open('skytrack/version.py').read()).group(1))")
PKG=linux-skytrack
ROOT=$(mktemp -d)/${PKG}_${VERSION}_all
SHARE=$ROOT/usr/share/$PKG

mkdir -p "$ROOT/DEBIAN" "$ROOT/usr/bin" "$SHARE" "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/icons/hicolor/scalable/apps" "$ROOT/usr/share/icons/hicolor/symbolic/apps" \
         "$ROOT/usr/share/doc/$PKG"

cp -r skytrack web data icons templates "$SHARE/"
rm -f "$SHARE/templates/"*.xlsx
rm -rf "$SHARE/data/src"
find "$SHARE" -name "__pycache__" -prune -exec rm -rf {} +
install -m 755 linux-skytrack "$ROOT/usr/bin/linux-skytrack"
install -d "$ROOT/usr/lib/$PKG" "$ROOT/usr/share/polkit-1/actions"
install -m 755 packaging/confirm-admin "$ROOT/usr/lib/$PKG/confirm-admin"
install -m 644 packaging/com.jgu.LinuxSkyTrack.policy "$ROOT/usr/share/polkit-1/actions/"
install -m 644 packaging/com.jgu.LinuxSkyTrack.desktop "$ROOT/usr/share/applications/"
install -m 644 icons/hicolor/scalable/apps/*.svg "$ROOT/usr/share/icons/hicolor/scalable/apps/"
install -m 644 icons/hicolor/symbolic/apps/*.svg "$ROOT/usr/share/icons/hicolor/symbolic/apps/"
install -m 644 README.md "$ROOT/usr/share/doc/$PKG/README.md"
install -m 644 packaging/copyright "$ROOT/usr/share/doc/$PKG/copyright"
install -m 644 LICENSE "$ROOT/usr/share/doc/$PKG/LICENSE"

SIZE=$(du -sk "$ROOT/usr" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, python3-cairo, gir1.2-pango-1.0, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.5), gir1.2-webkit-6.0, librsvg2-common, tzdata, pkexec | policykit-1
Recommends: python3-openpyxl, gstreamer1.0-plugins-good, gstreamer1.0-libav
Suggests: linux-icloud-photos (>= 0.16.0), libreoffice-calc, gvfs-backends, gnome-online-accounts
Maintainer: JGu <noreply@github.com>
Homepage: https://github.com/jgu-linux-apps/linux-skytrack
Description: SkyTrack - flight log, live tracking and maps for Ubuntu
 Log your flights (from, to, exact dates and times), see them as great-circle
 arcs with pins on visited airports (map, satellite or an offline outline
 map), and get kilometres flown with statistics per year, month and day and a
 yearly summary poster. See all aircraft in view with from/to routes and
 track flights live by flight number (adsb.lol, airplanes.live, adsb.fi,
 OpenSky), with notifications on take-off, delay and landing. One-click and
 weekly automatic backups. Polish and English interface. With Linux iCloud
 Photos 0.15.1+ a trip can be linked to an iCloud album.
 Created by: JGu. Supported by Claude.
EOF

cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
cp "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"
chmod 755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"

mkdir -p dist
dpkg-deb --root-owner-group --build "$ROOT" "dist/${PKG}_${VERSION}_all.deb"
echo "Built dist/${PKG}_${VERSION}_all.deb"
