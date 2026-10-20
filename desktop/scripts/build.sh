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
bash scripts/check-macos-toolchain.sh
FINAL_APP="$APP"
APP="${FINAL_APP}.building-$(python3 -c 'import uuid; print(uuid.uuid4())')"
trap 'rm -rf "$APP"' EXIT
/usr/bin/xcrun --toolchain XcodeDefault --sdk macosx swift build --package-path native -c release --product Umbod
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
scripts/bundle-python.sh "$APP/Contents/Resources"
python3 -c 'import uuid; print(uuid.uuid4())' > "$APP/Contents/Resources/runtime-id"
cat > "$APP/Contents/MacOS/umbod-desktop" <<'LAUNCHER'
#!/bin/sh
SELF="$0"
while [ -L "$SELF" ]; do
    LINK="$(readlink "$SELF")"
    case "$LINK" in /*) SELF="$LINK" ;; *) SELF="$(dirname "$SELF")/$LINK" ;; esac
done
HERE="$(CDPATH= cd -- "$(dirname -- "$SELF")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME PYTHONPATH
exec "$HERE/../Resources/python/bin/python3" -I -B -m umbod_desktop.main "$@"
LAUNCHER
chmod +x "$APP/Contents/MacOS/umbod-desktop"
# Existing agent configurations can keep the old command path; no Rust is bundled.
cp "$APP/Contents/MacOS/umbod-desktop" "$APP/Contents/MacOS/umbod-gateway"
cp native/.build/release/Umbod "$APP/Contents/MacOS/Umbod"
/usr/bin/xcrun --toolchain XcodeDefault --sdk macosx swift scripts/icon.swift "$OUTPUT/Umbod-$CHANNEL.iconset" "$CHANNEL"
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
python3 scripts/record-macos-build.py "$APP"
"$APP/Contents/Resources/python/bin/python3" -I -B scripts/audit-macos-bundle.py "$APP"
# Local/CI builds never search or use a developer's signing identity.
# Production publishing is disabled by release.py until verified signing exists.
while IFS= read -r -d '' binary; do
    if file "$binary" | grep -q 'Mach-O'; then codesign --force --sign - "$binary"; fi
done < <(find "$APP/Contents/Resources/python" -type f -print0)
codesign --force --sign - "$APP/Contents/MacOS/umbod-desktop"
codesign --force --sign - "$APP/Contents/MacOS/umbod-gateway"
codesign --force --sign - "$APP"
printf 'Ad-hoc signed; NOT notarized; UNSIGNED PRERELEASE; Gatekeeper acceptance NOT verified\n' > "$OUTPUT/SIGNING-$CHANNEL.txt"
if [[ "$CHANNEL" == "release" ]]; then cp "$OUTPUT/SIGNING-release.txt" "$OUTPUT/SIGNING.txt"; fi
codesign --verify --deep --strict "$APP"
plutil -lint "$APP/Contents/Info.plist"
scripts/verify-macos-bundle.sh "$APP"
if [[ -e "$FINAL_APP" ]]; then
    PREVIOUS="${FINAL_APP}.previous-$(python3 -c 'import uuid; print(uuid.uuid4())')"
    mv "$FINAL_APP" "$PREVIOUS"
fi
mv "$APP" "$FINAL_APP"
trap - EXIT
if [[ -n "${PREVIOUS:-}" ]]; then rm -rf "$PREVIOUS"; fi
printf 'Built %s\n' "$FINAL_APP"
