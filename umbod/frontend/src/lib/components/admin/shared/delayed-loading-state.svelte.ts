export class DelayedLoadingState {
  visible = $state(false);

  private readonly defaultDelayMs: number;
  private timeoutId: ReturnType<typeof globalThis.setTimeout> | undefined;

  constructor(defaultDelayMs: number = 300) {
    this.defaultDelayMs = defaultDelayMs;
  }

  start = (delayMs: number = this.defaultDelayMs): void => {
    this.clearTimer();
    this.visible = false;

    if (delayMs <= 0) {
      this.visible = true;
      return;
    }

    this.timeoutId = globalThis.setTimeout(() => {
      this.timeoutId = undefined;
      this.visible = true;
    }, delayMs);
  };

  stop = (): void => {
    this.clearTimer();
    this.visible = false;
  };

  dispose = (): void => {
    this.stop();
  };

  private clearTimer = (): void => {
    if (this.timeoutId === undefined) {
      return;
    }

    globalThis.clearTimeout(this.timeoutId);
    this.timeoutId = undefined;
  };
}
