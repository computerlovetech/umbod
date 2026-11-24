import { untrack } from 'svelte';
import type { ClipboardWriter } from '#lib/admin/clipboard.js';
import type { TelemetryInstallClaims } from '#lib/telemetry-setup/api.js';
import { PluginInstallationState, type InstallationHarness, type InstallationPlatform } from './plugin-installation-state.svelte';

const installationSteps = [
  { id: 'platform', label: 'Platform', heading: 'Choose your platform' },
  { id: 'harness', label: 'Harness', heading: 'Choose your harness' },
  { id: 'telemetry', label: 'Telemetry', heading: 'Set up telemetry' },
  { id: 'review', label: 'Review and install', heading: 'Review and install' }
] as const;

type InstallationStepDefinition = typeof installationSteps[number];
type InstallationStep = InstallationStepDefinition['id'];
type TelemetryChoice = 'skip' | 'logs';

const stepsWithoutTelemetry = installationSteps.filter((step): boolean => step.id !== 'telemetry');
const claimLifetimeMs = 10 * 60_000;
const copiedFeedbackMs = 2_000;
const claimMask = '••••••••••••••••';

type ReadyCommand = {
  status: 'ready';
  command: string;
  expiresAt: number | undefined;
  copy: 'idle' | 'pending' | 'copied' | 'failed';
  revealed: boolean;
};

type CommandStage = { status: 'idle' | 'preparing' | 'error' | 'expired' } | ReadyCommand;

type CommandOperation = {
  controller: AbortController;
  source: TelemetryInstallClaims | undefined;
  baseUrl: string;
};

export class InstallationWizardState {
  readonly installation: PluginInstallationState;
  #selectedStep = $state.raw<InstallationStepDefinition>(installationSteps[0]);
  #includeLogs = $state(false);
  #operation = $state.raw<CommandOperation>();
  #command = $state.raw<CommandStage>({ status: 'idle' });
  #expirationTimer: ReturnType<typeof setTimeout> | undefined;
  #copiedTimer: ReturnType<typeof setTimeout> | undefined;

  constructor(
    private readonly installerBaseUrl: () => string,
    private readonly installClaims: () => TelemetryInstallClaims | undefined,
    private readonly clipboard: ClipboardWriter
  ) {
    this.installation = new PluginInstallationState(installerBaseUrl);
  }

  get steps(): readonly InstallationStepDefinition[] {
    return this.canIncludeLogs ? installationSteps : stepsWithoutTelemetry;
  }

  get step(): InstallationStepDefinition {
    return this.steps.includes(this.#selectedStep) ? this.#selectedStep : installationSteps[1];
  }

  get stepNumber(): number {
    return this.steps.indexOf(this.step) + 1;
  }

  get canIncludeLogs(): boolean {
    return this.installClaims() !== undefined;
  }

  get includesLogs(): boolean {
    return this.canIncludeLogs && this.#includeLogs;
  }

  get summary(): Readonly<Partial<Record<InstallationStep, string>>> {
    return {
      platform: this.installation.selectedPlatform.label,
      harness: this.installation.harnessLabel,
      ...(this.canIncludeLogs ? { telemetry: this.includesLogs ? 'Logs only' : 'Without telemetry' } : {})
    };
  }

  private get commandStage(): CommandStage {
    if (!this.#operation || !this.isCurrent(this.#operation)) return { status: 'idle' };
    if (this.#command.status === 'ready' && this.#command.expiresAt !== undefined && this.#command.expiresAt <= Date.now()) {
      return { status: 'expired' };
    }
    return this.#command;
  }

  get commandPreview(): string {
    if (!this.includesLogs) return this.installation.command;
    const stage = this.commandStage;
    return stage.status === 'ready' && stage.revealed ? stage.command : this.installation.telemetryCommand(claimMask);
  }

  get commandShell(): string {
    return this.includesLogs && this.installation.platform === 'macos' ? 'Terminal · Bash or zsh' : this.installation.shell;
  }

  get canRevealCommand(): boolean {
    const stage = this.commandStage;
    return this.includesLogs && stage.status === 'ready' && stage.copy !== 'pending';
  }

  get isCommandRevealed(): boolean {
    const stage = this.commandStage;
    return this.includesLogs && stage.status === 'ready' && stage.revealed;
  }

  get isCopyPending(): boolean {
    const stage = this.commandStage;
    return stage.status === 'preparing' || (stage.status === 'ready' && stage.copy === 'pending');
  }

  get copyLabel(): string {
    const stage = this.commandStage;
    if (stage.status === 'expired') return 'Generate new command';
    if (stage.status === 'ready' && stage.copy === 'copied') return 'Copied';
    return 'Copy command';
  }

  get commandError(): boolean {
    return this.commandStage.status === 'error';
  }

  get commandStatus(): string {
    const stage = this.commandStage;
    if (stage.status === 'preparing') return 'Preparing your install command…';
    if (stage.status === 'expired') return 'Your install command has expired.';
    if (stage.status === 'ready' && stage.copy === 'failed' && stage.revealed) return 'Clipboard unavailable. Select the command to copy it manually.';
    return '';
  }

  toggleCommandVisibility(): void {
    const stage = this.commandStage;
    if (this.canRevealCommand && stage.status === 'ready') this.#command = { ...stage, revealed: !stage.revealed };
  }

  selectPlatform(platform: InstallationPlatform): void {
    if (platform === this.installation.platform) return;
    this.installation.selectPlatform(platform);
    this.resetCommand();
  }

  selectHarness(harness: InstallationHarness): void {
    if (harness === this.installation.harness) return;
    this.installation.selectHarness(harness);
    this.#includeLogs = false;
    this.resetCommand();
  }

  selectTelemetry(choice: TelemetryChoice): void {
    const includeLogs = choice === 'logs' && this.canIncludeLogs;
    if (this.#includeLogs === includeLogs) return;
    this.#includeLogs = includeLogs;
    this.resetCommand();
  }

  goTo(step: InstallationStep): void {
    const next = this.steps.find((candidate): boolean => candidate.id === step);
    if (!next || next === this.#selectedStep) return;
    this.resetCommand();
    this.#selectedStep = next;
  }

  continue(): void {
    const next = this.steps[this.stepNumber];
    if (next) this.goTo(next.id);
  }

  back(): void {
    const previous = this.steps[this.stepNumber - 2];
    if (previous) this.goTo(previous.id);
  }

  async copyCommand(): Promise<void> {
    if (this.step.id !== 'review' || this.isCopyPending) return;
    const stage = this.commandStage;
    if (this.#operation && stage.status === 'ready') {
      await this.writeCommand(this.#operation, stage);
      return;
    }

    this.resetCommand();
    const operation = {
      controller: new AbortController(),
      source: this.includesLogs ? this.installClaims() : undefined,
      baseUrl: this.installerBaseUrl()
    };
    this.#operation = operation;
    if (operation.source) {
      await this.prepareTelemetryCommand(operation, operation.source);
      return;
    }
    await this.writeCommand(operation, {
      status: 'ready', command: this.installation.command, expiresAt: undefined, copy: 'idle', revealed: false
    });
  }

  discardObsoleteCommand(): void {
    const source = this.includesLogs ? this.installClaims() : undefined;
    const baseUrl = this.installerBaseUrl();
    untrack((): void => {
      const operation = this.#operation;
      if (operation && (operation.source !== source || operation.baseUrl !== baseUrl)) this.resetCommand();
    });
  }

  resetCommand(): void {
    this.#operation?.controller.abort();
    this.#operation = undefined;
    this.#command = { status: 'idle' };
    clearTimeout(this.#expirationTimer);
    clearTimeout(this.#copiedTimer);
  }

  private async prepareTelemetryCommand(operation: CommandOperation, source: TelemetryInstallClaims): Promise<void> {
    this.#command = { status: 'preparing' };
    const expiresAt = Date.now() + claimLifetimeMs;
    this.#expirationTimer = setTimeout((): void => {
      if (!this.isCurrent(operation)) return;
      this.#command = { status: 'expired' };
      operation.controller.abort();
    }, claimLifetimeMs);
    try {
      const { code } = await source.create({ harness: this.installation.harness }, operation.controller.signal);
      if (!this.isCurrent(operation) || operation.controller.signal.aborted) return;
      if (expiresAt <= Date.now()) {
        this.#command = { status: 'expired' };
        return;
      }
      const command = this.installation.telemetryCommand(code);
      await this.writeCommand(operation, { status: 'ready', command, expiresAt, copy: 'idle', revealed: false });
    } catch {
      if (this.isCurrent(operation) && !operation.controller.signal.aborted) {
        clearTimeout(this.#expirationTimer);
        this.#command = { status: 'error' };
      }
    }
  }

  private async writeCommand(operation: CommandOperation, prepared: ReadyCommand): Promise<void> {
    clearTimeout(this.#copiedTimer);
    this.#command = { ...prepared, copy: 'pending', revealed: false };
    let copy: 'copied' | 'failed' = 'copied';
    try {
      await this.clipboard.writeText(prepared.command);
    } catch {
      copy = 'failed';
    }
    if (!this.isCurrent(operation) || this.commandStage.status !== 'ready') return;
    this.#command = { ...prepared, copy, revealed: copy === 'failed' };
    if (copy === 'copied') this.#copiedTimer = setTimeout((): void => this.clearCopiedFeedback(operation), copiedFeedbackMs);
  }

  private clearCopiedFeedback(operation: CommandOperation): void {
    const stage = this.commandStage;
    if (this.isCurrent(operation) && stage.status === 'ready') this.#command = { ...stage, copy: 'idle' };
  }

  private isCurrent(operation: CommandOperation): boolean {
    const source = this.includesLogs ? this.installClaims() : undefined;
    return this.#operation === operation && this.step.id === 'review' &&
      source === operation.source && this.installerBaseUrl() === operation.baseUrl;
  }
}
