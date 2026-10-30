import { describe, expect, it, vi } from 'vitest';
import { ObservationCoordinator } from './observation-coordinator';

function setup(): {
  coordinator: ObservationCoordinator;
  observe: ReturnType<typeof vi.fn<() => Promise<void>>>;
  advance: (milliseconds: number) => void;
  setVisible: (value: boolean) => void;
  timer: () => void;
  stop: ReturnType<typeof vi.fn>;
} {
  let now = 0;
  let visible = true;
  let timer = (): void => {};
  const stop = vi.fn();
  const observe = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
  const coordinator = new ObservationCoordinator({ observe }, {
    now: (): number => now,
    visible: (): boolean => visible,
    every: (milliseconds: number, callback: () => void): (() => void) => {
      expect(milliseconds).toBe(300_000);
      timer = callback;
      return stop;
    }
  });
  return { coordinator, observe, advance: (milliseconds: number): void => { now += milliseconds; }, setVisible: (value: boolean): void => { visible = value; }, timer: (): void => timer(), stop };
}

describe('best-effort observation lifetime', () => {
  it('starts without waiting, deduplicates pending requests and throttles successful attempts', async (): Promise<void> => {
    const test = setup();
    let finish!: () => void;
    test.observe.mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve; }));
    expect(test.coordinator.start()).toBeUndefined();
    test.coordinator.start();
    test.coordinator.trigger();
    test.advance(300_000);
    test.timer();
    expect(test.observe).toHaveBeenCalledTimes(1);
    finish();
    await Promise.resolve();
    test.coordinator.trigger();
    expect(test.observe).toHaveBeenCalledTimes(1);
    test.advance(60_000);
    test.coordinator.trigger();
    expect(test.observe).toHaveBeenCalledTimes(2);
    test.coordinator.dispose();
  });
  it('swallows failures and retries on a subsequent trigger without hiding or timer leaks', async (): Promise<void> => {
    const test = setup();
    test.observe.mockRejectedValueOnce(new Error('private token'));
    test.coordinator.start();
    await Promise.resolve();
    test.coordinator.trigger();
    expect(test.observe).toHaveBeenCalledTimes(2);
    await Promise.resolve();
    test.setVisible(false);
    test.advance(300_000);
    test.timer();
    test.coordinator.trigger();
    expect(test.observe).toHaveBeenCalledTimes(2);
    test.setVisible(true);
    test.coordinator.trigger();
    expect(test.observe).toHaveBeenCalledTimes(3);
    test.coordinator.dispose();
    expect(test.stop).toHaveBeenCalledTimes(1);
    test.advance(300_000);
    test.timer();
    test.coordinator.trigger();
    expect(test.observe).toHaveBeenCalledTimes(3);
  });
});
