import { normalizeInstallationUrl } from './installation-url';

export const installationPlatforms = [
  { id: 'macos', label: 'macOS', shell: 'Terminal', icon: '/icons/apple.svg' },
  { id: 'linux', label: 'Linux', shell: 'Bash · includes WSL', icon: '/icons/linux.svg' },
  { id: 'windows', label: 'Windows', shell: 'PowerShell', icon: '/icons/windows.svg' }
] as const;

export const installationHarnesses = [
  { value: 'codex', label: 'Codex', icon: '/icons/codex.png' },
  { value: 'claude-code', label: 'Claude Code', icon: '/icons/claude-code.svg' }
] as const;

export type InstallationPlatform = typeof installationPlatforms[number]['id'];
export type InstallationHarness = typeof installationHarnesses[number]['value'];
function quoteBash(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function quotePowerShell(value: string): string {
  return `'${value.replaceAll("'", "''")}'`;
}

export class PluginInstallationState {
  platform = $state<InstallationPlatform>('macos');
  harness = $state<InstallationHarness>('codex');

  constructor(private readonly installerBaseUrl: () => string) {}

  selectPlatform = (value: string): void => {
    const selected = installationPlatforms.find((platform) => platform.id === value);
    if (selected) this.platform = selected.id;
  };

  selectHarness = (value: string): void => {
    const selected = installationHarnesses.find((harness) => harness.value === value);
    if (selected) this.harness = selected.value;
  };

  get scriptUrl(): string {
    const extension = this.platform === 'windows' ? 'ps1' : 'sh';
    return `${normalizeInstallationUrl(this.installerBaseUrl())}/${this.harness}/install.${extension}`;
  }

  get command(): string {
    if (this.platform === 'windows') {
      return `irm -MaximumRedirection 0 ${quotePowerShell(this.scriptUrl)} | iex`;
    }
    return `curl -fsSL --proto-redir '=https' ${quoteBash(this.scriptUrl)} | bash`;
  }

  telemetryCommand(code: string): string {
    if (this.platform === 'windows') {
      return `& { $ErrorActionPreference = 'Stop'; $umbodInstallClaim = ${quotePowerShell(code)}; & ([scriptblock]::Create((Invoke-RestMethod -MaximumRedirection 0 ${quotePowerShell(this.scriptUrl)}))) }`;
    }
    return `(umbodScript=$(curl -q -fsS --location --max-redirs 0 --globoff -- ${quoteBash(this.scriptUrl)}) && UMBOD_INSTALL_CLAIM=${quoteBash(code)} bash -c "$umbodScript")`;
  }

  get selectedPlatform(): typeof installationPlatforms[number] {
    return installationPlatforms.find((platform) => platform.id === this.platform)!;
  }

  get shell(): string {
    return this.selectedPlatform.shell;
  }

  get harnessLabel(): string {
    return installationHarnesses.find((harness) => harness.value === this.harness)!.label;
  }
}
