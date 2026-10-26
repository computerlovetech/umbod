import type { AttemptScheduler } from '../attempt-scheduler';

export class InMemoryAttemptScheduler implements AttemptScheduler {
  private time = 0;
  now = (): number => this.time;
  private tasks = new Map<() => Promise<void>, number>();

  get pending(): number { return this.tasks.size; }

  schedule = (task: () => Promise<void>, delayMs: number): (() => void) => {
    this.tasks.set(task, this.time + delayMs);
    return (): void => { this.tasks.delete(task); };
  };

  advance = async (elapsedMs = 2000): Promise<void> => {
    this.time += elapsedMs;
    const tasks = [...this.tasks].filter(([, deadline]) => deadline <= this.time);
    for (const [task] of tasks) {
      this.tasks.delete(task);
      await task();
    }
  };
}
