#!/usr/bin/env python3
"""Launch the real bundled SwiftUI app and verify its own native window report.
This is lifecycle/window-state verification, not click or pixel-level UI automation.
"""
import json, os, pathlib, subprocess, sys, tempfile
desktop = pathlib.Path(__file__).resolve().parents[1]
version = (desktop / 'VERSION').read_text().strip()
app = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else desktop / 'dist' / f'Umbod-{version}.app').resolve()
with tempfile.TemporaryDirectory(prefix='umbod-native-smoke-') as temp:
    report = pathlib.Path(temp) / 'window.json'
    process = subprocess.Popen([str(app/'Contents/MacOS/Umbod'), '--data-dir', str(pathlib.Path(temp).resolve() / 'data'), '--smoke-report', str(report), '--smoke-close-reopen', '--smoke-exit'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        status = process.wait(timeout=20)
        assert status == 0, f'App exited with {status}'
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=8)
        raise AssertionError('Native app did not finish smoke lifecycle within 20 seconds')
    state = json.loads(report.read_text())
    assert state['backgroundSurvivedClose'] is True
    assert state['reopened'] is True
    assert state['serverCount'] == 0
    assert state['backendRunning'] is True
    assert any(w['visible'] and w['width'] >= 950 and w['height'] >= 680 for w in state['windows'])
    assert state['bundlePath'] == str(app)
    try:
        os.kill(state['backendPID'], 0)
        raise AssertionError('Bundled backend survived normal app termination')
    except ProcessLookupError:
        pass
    print(json.dumps(state, indent=2))
    print('PASS: actual bundled SwiftUI window created, backend authenticated, normal application termination')
