import type { ObservationEnvironment } from './port';

export function browserObservationEnvironment(): ObservationEnvironment {
  return {
    now: (): number => Date.now(),
    visible: (): boolean => document.visibilityState === 'visible',
    every: (milliseconds: number, callback: () => void): (() => void) => {
      const timer = window.setInterval(callback, milliseconds);
      return (): void => window.clearInterval(timer);
    }
  };
}
