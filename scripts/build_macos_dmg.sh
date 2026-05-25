#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="${1:-dev}"
APP_NAME="Bead Grid Marker"
BUNDLE_NAME="${APP_NAME}.app"
DIST_DIR="$ROOT_DIR/dist"
MACOS_BUILD_DIR="$ROOT_DIR/build/macos"
ICONSET_DIR="$MACOS_BUILD_DIR/bead_grid_marker.iconset"
ICNS_PATH="$MACOS_BUILD_DIR/bead_grid_marker.icns"
DMG_STAGING_DIR="$MACOS_BUILD_DIR/dmg"
DMG_NAME="bead-grid-marker-${VERSION}-macos-apple-silicon.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"

rm -rf "$MACOS_BUILD_DIR" "$DIST_DIR/$BUNDLE_NAME" "$DMG_PATH"
mkdir -p "$ICONSET_DIR" "$DIST_DIR"

for size in 16 32 128 256 512; do
  sips -z "$size" "$size" assets/icon.png --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
  sips -z "$((size * 2))" "$((size * 2))" assets/icon.png --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --argv-emulation \
  --name "$APP_NAME" \
  --icon "$ICNS_PATH" \
  main.py

codesign --force --deep --sign - "$DIST_DIR/$BUNDLE_NAME"

mkdir -p "$DMG_STAGING_DIR"
cp -R "$DIST_DIR/$BUNDLE_NAME" "$DMG_STAGING_DIR/"
ln -s /Applications "$DMG_STAGING_DIR/Applications"

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$DMG_STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

shasum -a 256 "$DMG_PATH"
