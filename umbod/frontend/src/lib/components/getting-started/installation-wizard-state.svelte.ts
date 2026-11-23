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

type ClaimStage =
  | { status: 'idle' | 'pending' | 'error' | 'expired' }
  | { status: 'ready'; command: string; expiresAt: number; copy: 'pending' | 'copied' | 'failed' };

type ClaimOperation = {
  controller: AbortController;
  source: TelemetryInstallClaims;
  baseUrl: string;
};

export class InstallationWizardState {
  readonly installation: PluginInstallationState;
  #selectedStep = $state.raw<InstallationStepDefinition>(installationSteps[0]);
  #includeLogs = $state(false);
  #operation = $state.raw<ClaimOperation>();
  #claim = $state.raw<ClaimStage>({ status: 'idle' });
  #expirationTimer: ReturnType<typeof setTimeout> | undefined;

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

  get claim(): ClaimStage {
    if (!this.#operation || !this.isCurrent(this.#operation)) return { status: 'idle' };
    if (this.#claim.status === 'ready' && this.#claim.expiresAt <= Date.now()) return { status: 'expired' };
    return this.#claim;
  }

  selectPlatform(platform: InstallationPlatform): void {
    if (platform === this.installation.platform) return;
    this.installation.selectPlatform(platform);
    this.clearClaim();
  }

  selectHarness(harness: InstallationHarness): void {
    if (harness === this.installation.harness) return;
    this.installation.selectHarness(harness);
    this.#includeLogs = false;
    this.clearClaim();
  }

  selectTelemetry(choice: TelemetryChoice): void {
    const includeLogs = choice === 'logs' && this.canIncludeLogs;
    if (this.#includeLogs === includeLogs) return;
    this.#includeLogs = includeLogs;
    this.clearClaim();
  }

  goTo(step: InstallationStep): void {
    const next = this.steps.find((candidate): boolean => candidate.id === step);
    if (!next || next === this.#selectedStep) return;
    this.clearClaim();
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

  async prepareAndCopy(): Promise<void> {
    const source = this.installClaims();
    if (!source || !this.includesLogs || this.step.id !== 'review' || this.claim.status === 'pending') return;

    this.clearClaim();
    const operation = { controller: new AbortController(), source, baseUrl: this.installerBaseUrl() };
    this.#operation = operation;
    this.#claim = { status: 'pending' };
    const expiresAt = Date.now() + claimLifetimeMs;
    try {
      const { code } = await source.create({ harness: this.installation.harness }, operation.controller.signal);
      if (!this.isCurrent(operation)) return;
      if (expiresAt <= Date.now()) {
        this.#claim = { status: 'expired' };
        return;
      }
      const command = this.installation.telemetryCommand(code);
      this.#expirationTimer = setTimeout((): void => {
        if (this.#operation === operation) this.#claim = { status: 'expired' };
      }, expiresAt - Date.now());
      await this.writeCommand(operation, { status: 'ready', command, expiresAt, copy: 'pending' });
    } catch {
      if (this.isCurrent(operation)) this.#claim = { status: 'error' };
    }
  }

  async copyPreparedCommand(): Promise<void> {
    const prepared = this.claim;
    if (this.#operation && prepared.status === 'ready' && prepared.copy !== 'pending') {
      await this.writeCommand(this.#operation, prepared);
    }
  }

  clearClaim(): void {
    this.#operation?.controller.abort();
    this.#operation = undefined;
    this.#claim = { status: 'idle' };
    clearTimeout(this.#expirationTimer);
    this.#expirationTimer = undefined;
  }

  private async writeCommand(operation: ClaimOperation, prepared: Extract<ClaimStage, { status: 'ready' }>): Promise<void> {
    this.#claim = { ...prepared, copy: 'pending' };
    const copy = await this.clipboard.writeText(prepared.command).then(
      (): 'copied' => 'copied',
      (): 'failed' => 'failed'
    );
    if (this.isCurrent(operation) && this.claim.status === 'ready') this.#claim = { ...prepared, copy };
  }

  private isCurrent(operation: ClaimOperation): boolean {
    return this.#operation === operation && this.includesLogs && this.step.id === 'review' &&
      this.installClaims() === operation.source && this.installerBaseUrl() === operation.baseUrl;
  }
}
