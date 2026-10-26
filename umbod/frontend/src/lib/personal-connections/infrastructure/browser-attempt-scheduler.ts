import type { AttemptScheduler } from '../attempt-scheduler';

export const browserAttemptScheduler: AttemptScheduler = {
  now: (): number => Date.now(),
  schedule: (task, delayMs): (() => void) => {
    const timer = setTimeout((): void => { void task(); }, delayMs);
    return (): void => clearTimeout(timer);
  }
};
