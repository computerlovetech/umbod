import { PluginInstallationState, type InstallationHarness, type InstallationPlatform } from './plugin-installation-state.svelte';
import type { TelemetryInstaller } from './telemetry-installer';

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

type PackageStage =
  | { status: 'idle' | 'pending' | 'error' }
  | { status: 'ready'; blob: Blob };

export class InstallationWizardState {
  readonly installation: PluginInstallationState;
  #selectedStep = $state.raw<InstallationStepDefinition>(installationSteps[0]);
  #includeLogs = $state(false);
  #installer = $state.raw<TelemetryInstaller>();
  #package = $state.raw<PackageStage>({ status: 'idle' });
  #controller: AbortController | undefined;

  constructor(
    installerBaseUrl: () => string,
    private readonly telemetryInstaller: () => TelemetryInstaller | undefined
  ) {
    this.installation = new PluginInstallationState(installerBaseUrl);
  }

  get steps(): readonly InstallationStepDefinition[] {
    return this.telemetryInstaller() ? installationSteps : stepsWithoutTelemetry;
  }

  get step(): InstallationStepDefinition {
    return this.steps.includes(this.#selectedStep) ? this.#selectedStep : installationSteps[1];
  }

  get stepNumber(): number {
    return this.steps.indexOf(this.step) + 1;
  }

  get canIncludeLogs(): boolean {
    return this.installation.harness === 'claude-code' && this.telemetryInstaller() !== undefined;
  }

  get includesLogs(): boolean {
    return this.canIncludeLogs && this.#includeLogs;
  }

  get summary(): Readonly<Partial<Record<InstallationStep, string>>> {
    return {
      platform: this.installation.selectedPlatform.label,
      harness: this.installation.harnessLabel,
      ...(this.telemetryInstaller() ? { telemetry: this.includesLogs ? 'Logs only' : 'Skip telemetry' } : {})
    };
  }

  get packageStatus(): PackageStage['status'] {
    return this.#currentPackage.status;
  }

  get scriptName(): string {
    return this.installation.platform === 'windows' ? 'umbod-install.ps1' : 'umbod-install.sh';
  }

  get #currentPackage(): PackageStage {
    return this.includesLogs && this.#installer === this.telemetryInstaller()
      ? this.#package
      : { status: 'idle' };
  }

  selectPlatform(platform: InstallationPlatform): void {
    if (platform === this.installation.platform) return;
    this.installation.selectPlatform(platform);
    this.invalidatePackage();
  }

  selectHarness(harness: InstallationHarness): void {
    if (harness === this.installation.harness) return;
    this.installation.selectHarness(harness);
    if (!this.canIncludeLogs) this.#includeLogs = false;
    this.invalidatePackage();
  }

  selectTelemetry(choice: TelemetryChoice): void {
    const includeLogs = choice === 'logs' && this.canIncludeLogs;
    if (this.#includeLogs === includeLogs) return;
    this.#includeLogs = includeLogs;
    this.invalidatePackage();
  }

  goTo(step: InstallationStep): void {
    const next = this.steps.find((candidate): boolean => candidate.id === step);
    if (!next) return;
    this.#selectedStep = next;
    if (step === 'review' && this.packageStatus === 'idle') void this.preparePackage();
  }

  continue(): void {
    const next = this.steps[this.stepNumber];
    if (next) this.goTo(next.id);
  }

  back(): void {
    const previous = this.steps[this.stepNumber - 2];
    if (previous) this.goTo(previous.id);
  }

  async preparePackage(): Promise<void> {
    const installer = this.telemetryInstaller();
    if (!installer || !this.includesLogs || this.step.id !== 'review') return;
    if (this.packageStatus === 'pending' || this.packageStatus === 'ready') return;

    this.invalidatePackage();
    const controller = new AbortController();
    this.#controller = controller;
    this.#installer = installer;
    this.#package = { status: 'pending' };
    try {
      const blob = await installer.prepare(this.installation.platform, this.installation.harness, controller.signal);
      if (this.isCurrentRequest(controller, installer)) this.#package = { status: 'ready', blob };
    } catch {
      if (this.isCurrentRequest(controller, installer)) this.#package = { status: 'error' };
    } finally {
      if (this.#controller === controller) this.#controller = undefined;
    }
  }

  download(consume: (blob: Blob, filename: string) => void): void {
    const prepared = this.#currentPackage;
    if (this.step.id === 'review' && prepared.status === 'ready') consume(prepared.blob, 'umbod-installer.zip');
  }

  invalidatePackage(): void {
    this.#controller?.abort();
    this.#controller = undefined;
    this.#package = { status: 'idle' };
    this.#installer = undefined;
  }

  private isCurrentRequest(controller: AbortController, installer: TelemetryInstaller): boolean {
    return !controller.signal.aborted && installer === this.telemetryInstaller();
  }
}
