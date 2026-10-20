import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "desktop/scripts/check-macos-toolchain.sh"
HARNESS = r'''
source "$1"
host_tool() {
    case "$1" in
        -s) printf '%s\n' "$HOST_SYSTEM" ;;
        -m) printf '%s\n' "$HOST_ARCH" ;;
    esac
}
apple_tool() {
    printf '%s\n' "$DEVELOPER_DIR" "$@" >> "$CALL_LOG"
    local tool="$1"
    shift
    if [[ "$tool" == xcodebuild ]]; then
        if [[ "$SCENARIO" == clt ]]; then
            printf 'requires Xcode, active developer directory is CommandLineTools\n' >&2
            return 1
        fi
        if [[ "$SCENARIO" == license ]]; then
            printf 'license agreement not accepted\n' >&2
            return 1
        fi
        if [[ "$1" == -checkFirstLaunchStatus ]]; then
            [[ "$SCENARIO" != setup ]]
            return
        fi
        printf 'Xcode 26.0\nBuild version 17A\n'
        return
    fi
    case "$*" in
        *'--find swiftc')
            [[ "$SCENARIO" != missing-swiftc ]] || return 1
            printf '%s/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc\n' "$DEVELOPER_DIR" ;;
        *'--find swift')
            [[ "$SCENARIO" != missing-swift ]] || return 1
            if [[ "$SCENARIO" == nix-compiler ]]; then
                printf '/nix/store/swift/bin/swift\n'
            else
                printf '%s/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift\n' "$DEVELOPER_DIR"
            fi ;;
        *'--show-sdk-path')
            [[ "$SCENARIO" != missing-sdk ]] || return 1
            if [[ "$SCENARIO" == clt-sdk ]]; then
                printf '/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk\n'
            else
                printf '%s/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk\n' "$DEVELOPER_DIR"
            fi ;;
        *'swift --version')
            if [[ "$SCENARIO" == old ]]; then
                printf 'Apple Swift version 5.10\n'
            else
                printf 'Apple Swift version 6.2\n'
            fi ;;
        *'swiftc '*)
            cp "${@: -1}" "$PROBE_COPY"
            printf '%s\n' "${@: -1}" > "$PROBE_PATH"
            if [[ "$SCENARIO" == probe ]]; then
                printf 'SwiftUIMacros plugin unavailable\n' >&2
                return 1
            fi ;;
        *) return 1 ;;
    esac
}
check_macos_toolchain
'''


class MacOSToolchainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="umbod-toolchain-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.script = self.directory / "standalone toolchain.sh"
        self.script.write_text(SCRIPT.read_text())
        self.calls = self.directory / "calls"
        self.probe_copy = self.directory / "probe-copy"
        self.probe_path = self.directory / "probe-path"
        self.developer = "/Applications/Xcode Stable.app/Contents/Developer"

    def run_preflight(
        self, scenario: str = "valid", system: str = "Darwin", architecture: str = "arm64"
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "SCENARIO": scenario,
            "HOST_SYSTEM": system,
            "HOST_ARCH": architecture,
            "DEVELOPER_DIR": self.developer,
            "CALL_LOG": str(self.calls),
            "PROBE_COPY": str(self.probe_copy),
            "PROBE_PATH": str(self.probe_path),
            "TMPDIR": str(self.directory),
        }
        return subprocess.run(
            ["/bin/bash", "-c", HARNESS, "toolchain-test", str(self.script)],
            cwd=self.directory,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_rejects_unsupported_hosts_before_apple_tools(self) -> None:
        for system, architecture, diagnostic in [
            ("Linux", "arm64", "Darwin is required"),
            ("Darwin", "x86_64", "arm64"),
        ]:
            with self.subTest(system=system, architecture=architecture):
                result = self.run_preflight(system=system, architecture=architecture)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)
                self.assertFalse(self.calls.exists())

    def test_reports_selection_license_and_setup_failures(self) -> None:
        for scenario, diagnostic in [
            ("clt", "Command Line Tools are selected"),
            ("license", "license agreement not accepted"),
            ("setup", "first-launch setup is incomplete"),
        ]:
            with self.subTest(scenario=scenario):
                result = self.run_preflight(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)
                self.assertIn("DEVELOPER_DIR", result.stderr)
                self.assertFalse(self.probe_path.exists())

    def test_rejects_old_swift_and_missing_or_foreign_toolchain_inputs(self) -> None:
        for scenario, diagnostic in [
            ("old", "Swift 6 or newer"),
            ("missing-swift", "Cannot locate XcodeDefault swift"),
            ("missing-swiftc", "Cannot locate XcodeDefault swiftc"),
            ("missing-sdk", "Cannot locate the macOS SDK"),
            ("nix-compiler", "Swift must come from full Xcode"),
            ("clt-sdk", "SDK must come from full Xcode"),
        ]:
            with self.subTest(scenario=scenario):
                result = self.run_preflight(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)
                self.assertFalse(self.probe_path.exists())

    def test_valid_xcode_preserves_selection_and_probes_macros_with_exact_flags(self) -> None:
        result = self.run_preflight()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text().splitlines()
        self.assertEqual(calls.count(self.developer), 7)
        self.assertIn("-checkFirstLaunchStatus", calls)
        probe = Path(self.probe_path.read_text().strip())
        expected = [
            "xcrun", "--toolchain", "XcodeDefault", "--sdk", "macosx", "swiftc",
            "-swift-version", "6", "-sdk",
            self.developer + "/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk",
            "-target", "arm64-apple-macosx14.0", "-module-cache-path",
            str(probe.parent / "modules"), "-parse-as-library", "-typecheck", str(probe),
        ]
        self.assertEqual(calls[-len(expected):], expected)
        self.assertIn("@MainActor struct ToolchainProbe: View", self.probe_copy.read_text())
        self.assertIn("@State private var value = false", self.probe_copy.read_text())
        self.assertIn('Text(value ? "on" : "off")', self.probe_copy.read_text())
        self.assertFalse(probe.parent.exists())

    def test_probe_failure_retains_diagnostics_and_removes_temporary_files(self) -> None:
        result = self.run_preflight("probe")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SwiftUIMacros plugin unavailable", result.stderr)
        self.assertIn("SwiftUI @State macro typecheck failed", result.stderr)
        probe = Path(self.probe_path.read_text().strip())
        self.assertFalse(probe.parent.exists())

    def test_nix_wiring_keeps_default_shell_and_limits_desktop_to_arm_darwin(self) -> None:
        flake = (ROOT / "flake.nix").read_text()
        self.assertIn("default = pkgs.mkShell shellInputs;", flake)
        self.assertIn('optionalAttrs (system == "aarch64-darwin")', flake)
        self.assertIn("desktop = pkgs.mkShellNoCC (shellInputs // {", flake)
        self.assertIn("${pkgs.bash}/bin/bash ${./desktop/scripts/check-macos-toolchain.sh} || exit $?", flake)
        self.assertIn('UV_PYTHON = "${pkgs.python314}/bin/python3.14";', flake)
        self.assertIn('UV_PYTHON_DOWNLOADS = "never";', flake)
        for package in ["swift", "clang", "apple-sdk"]:
            self.assertNotIn("pkgs." + package, flake)


if __name__ == "__main__":
    unittest.main()
