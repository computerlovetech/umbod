#!/bin/bash
set -euo pipefail

host_tool() {
    /usr/bin/uname "$@"
}

apple_tool() {
    local tool="$1"
    shift
    "/usr/bin/$tool" "$@"
}

toolchain_error() {
    printf 'macOS desktop toolchain: %s\n' "$1" >&2
    printf 'Install full Xcode (not only Command Line Tools), open it to complete first launch and license setup, then select it with DEVELOPER_DIR or sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer.\n' >&2
    return 1
}

check_macos_toolchain() (
    local xcode_version swift swiftc sdk swift_version major
    [[ "$(host_tool -s)" == Darwin ]] || { toolchain_error 'Darwin is required.'; return 1; }
    [[ "$(host_tool -m)" == arm64 ]] || { toolchain_error 'Apple Silicon (arm64) is required.'; return 1; }
    if ! xcode_version="$(apple_tool xcodebuild -version 2>&1)"; then
        printf '%s\n' "$xcode_version" >&2
        case "$xcode_version" in
            *[Cc]ommand[Ll]ine[Tt]ools*|*command\ line\ tools*) toolchain_error 'Command Line Tools are selected; full Xcode is required.' ;;
            *) toolchain_error 'Selected Xcode is unavailable or requires license/first-launch setup.' ;;
        esac
        return 1
    fi
    [[ "$xcode_version" == Xcode\ * ]] || { toolchain_error 'Full Xcode must be selected.'; return 1; }
    if ! apple_tool xcodebuild -checkFirstLaunchStatus; then
        toolchain_error 'Full Xcode first-launch setup is incomplete; open Xcode to finish setup.'
        return 1
    fi
    swift="$(apple_tool xcrun --toolchain XcodeDefault --sdk macosx --find swift)" || { toolchain_error 'Cannot locate XcodeDefault swift.'; return 1; }
    swiftc="$(apple_tool xcrun --toolchain XcodeDefault --sdk macosx --find swiftc)" || { toolchain_error 'Cannot locate XcodeDefault swiftc.'; return 1; }
    sdk="$(apple_tool xcrun --sdk macosx --show-sdk-path)" || { toolchain_error 'Cannot locate the macOS SDK.'; return 1; }
    case "$swift" in
        /nix/store/*) toolchain_error 'Swift must come from full Xcode.'; return 1 ;;
        /*.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift) ;;
        *) toolchain_error 'Swift must come from full Xcode.'; return 1 ;;
    esac
    [[ "$swiftc" == "${swift}c" ]] || { toolchain_error 'swiftc must use the same XcodeDefault toolchain as swift.'; return 1; }
    case "$sdk" in
        /nix/store/*) toolchain_error 'SDK must come from full Xcode.'; return 1 ;;
        /*.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX*.sdk) ;;
        *) toolchain_error 'SDK must come from full Xcode.'; return 1 ;;
    esac
    swift_version="$(apple_tool xcrun --toolchain XcodeDefault --sdk macosx swift --version)" || { toolchain_error 'Cannot run Swift.'; return 1; }
    if [[ "$swift_version" =~ Swift\ version\ ([0-9]+)\. ]]; then
        major="${BASH_REMATCH[1]}"
    else
        toolchain_error 'Cannot determine Swift version.'
        return 1
    fi
    (( major >= 6 )) || { toolchain_error 'Swift 6 or newer is required.'; return 1; }
    temporary="$(mktemp -d "${TMPDIR:-/tmp}/umbod-toolchain.XXXXXX")"
    trap 'rm -rf "$temporary"' EXIT
    mkdir -p "$temporary/modules"
    printf '%s\n' 'import SwiftUI' '@MainActor struct ToolchainProbe: View {' '    @State private var value = false' '    var body: some View { Text(value ? "on" : "off") }' '}' > "$temporary/Probe.swift"
    if ! apple_tool xcrun --toolchain XcodeDefault --sdk macosx swiftc -swift-version 6 -sdk "$sdk" -target arm64-apple-macosx14.0 -module-cache-path "$temporary/modules" -parse-as-library -typecheck "$temporary/Probe.swift"; then
        toolchain_error 'SwiftUI @State macro typecheck failed with the selected Xcode SDK.'
        return 1
    fi
    printf 'macOS desktop toolchain: Xcode Swift %s, SwiftUI ready.\n' "$major"
)

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    check_macos_toolchain
fi
