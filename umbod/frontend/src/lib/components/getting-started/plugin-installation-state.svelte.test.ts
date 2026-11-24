import { describe, expect, test } from 'vitest';
import { PluginInstallationState } from './plugin-installation-state.svelte';

const installerBaseUrl = 'https://site.test/api/install/v1';

describe('plugin installation choices', (): void => {
  test.each(['macos', 'linux'])('builds a single-URL Bash command for %s and both harnesses', (platform): void => {
    const state = new PluginInstallationState(() => installerBaseUrl);
    state.selectPlatform(platform);
    for (const harness of ['codex', 'claude-code']) {
      state.selectHarness(harness);
      expect(state.command).toBe(`curl -fsSL --proto-redir '=https' 'https://site.test/api/install/v1/${harness}/install.sh' | bash`);
      expect(state.scriptUrl).toBe(`https://site.test/api/install/v1/${harness}/install.sh`);
      expect(state.command.match(/https?:\/\//g)).toHaveLength(1);
    }
  });

  test.each(['codex', 'claude-code'])('builds a single-URL native PowerShell command for %s', (harness): void => {
    const state = new PluginInstallationState(() => installerBaseUrl);
    state.selectPlatform('windows');
    state.selectHarness(harness);
    expect(state.shell).toBe('PowerShell');
    expect(state.command).toBe(`irm -MaximumRedirection 0 'https://site.test/api/install/v1/${harness}/install.ps1' | iex`);
    expect(state.command.match(/https?:\/\//g)).toHaveLength(1);
    expect(state.command).not.toContain('ExecutionPolicy');
  });

  test.each(['macos', 'linux'])('runs the telemetry installer on %s without replacing interactive stdin', (platform): void => {
    const state = new PluginInstallationState(() => installerBaseUrl);
    state.selectPlatform(platform);
    const code = 'A'.repeat(43);
    for (const harness of ['codex', 'claude-code']) {
      state.selectHarness(harness);
      expect(state.telemetryCommand(code)).toBe(
        `(umbodScript=$(curl -q -fsS --location --max-redirs 0 --globoff -- '${state.scriptUrl}') && UMBOD_INSTALL_CLAIM='${code}' bash -c "$umbodScript")`
      );
    }
  });

  test.each(['codex', 'claude-code'])('runs the telemetry installer in scoped PowerShell for %s', (harness): void => {
    const state = new PluginInstallationState(() => installerBaseUrl);
    state.selectPlatform('windows');
    state.selectHarness(harness);
    const code = 'A'.repeat(43);
    expect(state.telemetryCommand(code)).toBe(
      `& { $ErrorActionPreference = 'Stop'; $umbodInstallClaim = '${code}'; & ([scriptblock]::Create((Invoke-RestMethod -MaximumRedirection 0 '${state.scriptUrl}'))) }`
    );
  });

  test('retains the harness across platforms and ignores unsupported choices', (): void => {
    const state = new PluginInstallationState(() => installerBaseUrl);
    state.selectHarness('claude-code');
    state.selectPlatform('windows');
    state.selectPlatform('unknown');
    state.selectHarness('unknown');
    expect(state.platform).toBe('windows');
    expect(state.harness).toBe('claude-code');
    expect(state.harnessLabel).toBe('Claude Code');
  });

  test('reads the latest deployment URL and quotes it for each shell', (): void => {
    let current = installerBaseUrl;
    const state = new PluginInstallationState(() => current);
    current = "https://site.test/it's/api/install/v1";
    expect(state.command).toContain("'https://site.test/it'\\''s/api/install/v1/codex/install.sh'");
    state.selectPlatform('windows');
    expect(state.command).toContain("'https://site.test/it''s/api/install/v1/codex/install.ps1'");
  });

  test.each([
    'http://remote.test/api/install/v1',
    'https://name:secret@site.test/api/install/v1',
    'https://site.test/api/install/v1?secret=value',
    'https://site.test/api/install/v1#fragment',
    'https://site.test/${value}'
  ])('rejects unsafe installer URL: %s', (base): void => {
    const state = new PluginInstallationState(() => base);
    expect(() => state.command).toThrow();
  });

  test('allows loopback HTTP development URLs', (): void => {
    const state = new PluginInstallationState(() => 'http://localhost:3010/api/install/v1');
    expect(state.command).toContain('http://localhost:3010/api/install/v1/codex/install.sh');
  });
});
