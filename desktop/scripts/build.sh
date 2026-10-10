#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
CHANNEL="${1:-dev}"
VERSION="$(python3 scripts/release.py version)"
OUTPUT="${UMBOD_DIST_DIR:-$PWD/dist}"
case "$CHANNEL" in
  dev) APP_NAME="Umbod Dev"; BUNDLE_ID="app.umbod.desktop.dev"; APP="$OUTPUT/Umbod Dev.app" ;;
  release) APP_NAME="Umbod"; BUNDLE_ID="app.umbod.desktop"; APP="$OUTPUT/Umbod-$VERSION.app" ;;
  *) echo "Usage: scripts/build.sh [dev|release]" >&2; exit 1 ;;
esac
export PATH="$HOME/.cargo/bin:$PATH"
cargo build --locked --release
swift build --package-path native -c release --product Umbod
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp target/release/umbod-gateway "$APP/Contents/MacOS/umbod-gateway"
cp native/.build/release/Umbod "$APP/Contents/MacOS/Umbod"
swift scripts/icon.swift "$OUTPUT/Umbod-$CHANNEL.iconset" "$CHANNEL"
iconutil -c icns "$OUTPUT/Umbod-$CHANNEL.iconset" -o "$APP/Contents/Resources/UmbodBrand.icns"
rm -f "$APP/Contents/MacOS/umbod-profile"
printf '%s\n' "$CHANNEL" > "$APP/Contents/Resources/umbod-profile"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>Umbod</string>
<key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
<key>UmbodChannel</key><string>$CHANNEL</string>
<key>CFBundleIconFile</key><string>UmbodBrand</string>
<key>CFBundleName</key><string>$APP_NAME</string>
<key>CFBundleDisplayName</key><string>$APP_NAME</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$VERSION</string>
<key>CFBundleVersion</key><string>$VERSION</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSPrincipalClass</key><string>NSApplication</string>
</dict></plist>
PLIST
# Local/CI builds never search or use a developer's signing identity.
# Production publishing is disabled by release.py until verified signing exists.
codesign --force --sign - "$APP/Contents/MacOS/umbod-gateway"
codesign --force --sign - "$APP"
printf 'Ad-hoc signed; NOT notarized; UNSIGNED PRERELEASE; Gatekeeper acceptance NOT verified\n' > "$OUTPUT/SIGNING-$CHANNEL.txt"
if [[ "$CHANNEL" == "release" ]]; then cp "$OUTPUT/SIGNING-release.txt" "$OUTPUT/SIGNING.txt"; fi
codesign --verify --deep --strict "$APP"
plutil -lint "$APP/Contents/Info.plist"
scripts/ui-smoke.sh "$APP"
printf 'Built %s\n' "$APP"
