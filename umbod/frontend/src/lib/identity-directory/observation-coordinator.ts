import type { IdentityObservation, ObservationEnvironment } from './port';

export class ObservationCoordinator {
  private started = false;
  private pending = false;
  private lastSuccess = -Infinity;
  private stopTimer: (() => void) | undefined;
  constructor(private readonly observation: IdentityObservation, private readonly environment: ObservationEnvironment) {}
  start = (): void => {
    if (this.started) return;
    this.started = true;
    this.stopTimer = this.environment.every(300_000, this.trigger);
    this.trigger();
  };
  trigger = (): void => {
    if (!this.started || this.pending || !this.environment.visible() || this.environment.now() - this.lastSuccess < 60_000) return;
    this.pending = true;
    void this.attempt();
  };
  private async attempt(): Promise<void> {
    try {
      await this.observation.observe();
      this.lastSuccess = this.environment.now();
    } catch {
    } finally {
      this.pending = false;
    }
  }
  dispose = (): void => {
    this.started = false;
    this.stopTimer?.();
    this.stopTimer = undefined;
  };
}
