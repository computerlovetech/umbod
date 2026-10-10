#!/bin/bash
set -euo pipefail
APP="${1:-dist/Umbod.app}"
test -x "$APP/Contents/MacOS/Umbod"
test -x "$APP/Contents/MacOS/umbod-gateway"
/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP/Contents/Info.plist"
