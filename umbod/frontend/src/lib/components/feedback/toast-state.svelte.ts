export type ToastVariant = 'success' | 'warning' | 'error';

type AutoDismissToastVariant = Exclude<ToastVariant, 'error'>;
type ToastTimer = ReturnType<typeof globalThis.setTimeout>;

export const SUCCESS_TOAST_DURATION_MS: number = 5_000;
export const WARNING_TOAST_DURATION_MS: number = 8_000;

const AUTO_DISMISS_DURATIONS_MS: Record<AutoDismissToastVariant, number> = {
  success: SUCCESS_TOAST_DURATION_MS,
  warning: WARNING_TOAST_DURATION_MS
};

export type ToastTimerApi = {
  setTimeout: (callback: () => void, durationMs: number) => ToastTimer;
  clearTimeout: (timer: ToastTimer) => void;
};

const defaultToastTimerApi: ToastTimerApi = {
  setTimeout: (callback: () => void, durationMs: number): ToastTimer =>
    globalThis.setTimeout(callback, durationMs),
  clearTimeout: (timer: ToastTimer): void => globalThis.clearTimeout(timer)
};

export type Toast = {
  id: number;
  message: string;
  variant: ToastVariant;
};

export type ToastApi = {
  success: (message: string) => number;
  warning: (message: string) => number;
  error: (message: string) => number;
  dismiss: (id: number) => void;
};

export class ToastState implements ToastApi {
  toasts = $state<Toast[]>([]);
  private nextId = 1;
  private readonly dismissalTimers = new Map<number, ToastTimer>();
  private readonly timerApi: ToastTimerApi;

  constructor(timerApi: ToastTimerApi = defaultToastTimerApi) {
    this.timerApi = timerApi;
  }

  success = (message: string): number => this.add(message, 'success');

  warning = (message: string): number => this.add(message, 'warning');

  error = (message: string): number => this.add(message, 'error');

  dismiss = (id: number): void => {
    const timer = this.dismissalTimers.get(id);
    if (timer !== undefined) {
      this.timerApi.clearTimeout(timer);
      this.dismissalTimers.delete(id);
    }
    this.toasts = this.toasts.filter((toast) => toast.id !== id);
  };

  private add = (message: string, variant: ToastVariant): number => {
    const id = this.nextId;
    this.nextId += 1;
    this.toasts = [...this.toasts, { id, message, variant }];
    if (variant !== 'error') {
      const timer = this.timerApi.setTimeout(
        () => {
          this.dismissalTimers.delete(id);
          this.dismiss(id);
        },
        AUTO_DISMISS_DURATIONS_MS[variant]
      );
      this.dismissalTimers.set(id, timer);
    }
    return id;
  };
}
