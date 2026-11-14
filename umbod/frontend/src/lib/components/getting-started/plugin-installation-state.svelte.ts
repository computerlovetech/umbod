import { normalizeInstallationUrl } from './installation-url';

export const installationPlatforms = [
  { id: 'macos', label: 'macOS', shell: 'Terminal' },
  { id: 'linux', label: 'Linux', shell: 'Bash · includes WSL' },
  { id: 'windows', label: 'Windows', shell: 'PowerShell' }
] as const;

export const installationHarnesses = [
  { value: 'codex', label: 'Codex' },
  { value: 'claude-code', label: 'Claude Code' }
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

  movePlatform = (key: string): boolean => {
    const current = installationPlatforms.findIndex((platform) => platform.id === this.platform);
    const positions: Record<string, number> = {
      ArrowRight: (current + 1) % installationPlatforms.length,
      ArrowLeft: (current + installationPlatforms.length - 1) % installationPlatforms.length,
      Home: 0,
      End: installationPlatforms.length - 1
    };
    const next = positions[key];
    if (next === undefined) return false;
    this.selectPlatform(installationPlatforms[next].id);
    return true;
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

  get shell(): string {
    return installationPlatforms.find((platform) => platform.id === this.platform)!.shell;
  }

  get harnessLabel(): string {
    return installationHarnesses.find((harness) => harness.value === this.harness)!.label;
  }

  get documentationUrl(): string {
    return this.harness === 'codex'
      ? 'https://developers.openai.com/codex/plugins'
      : 'https://code.claude.com/docs/en/plugins';
  }
}
