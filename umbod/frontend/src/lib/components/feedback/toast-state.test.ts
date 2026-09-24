import { afterEach, describe, expect, test, vi } from 'vitest';
import {
  SUCCESS_TOAST_DURATION_MS,
  ToastState,
  WARNING_TOAST_DURATION_MS
} from './toast-state.svelte';

describe('ToastState', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  test('adds typed notifications with stable unique identifiers', () => {
    vi.useFakeTimers();
    const state = new ToastState();

    const successId = state.success('Saved');
    const warningId = state.warning('Review changes');
    const errorId = state.error('Could not save');

    expect(state.toasts).toEqual([
      { id: successId, message: 'Saved', variant: 'success' },
      { id: warningId, message: 'Review changes', variant: 'warning' },
      { id: errorId, message: 'Could not save', variant: 'error' }
    ]);
    expect(new Set(state.toasts.map((toast) => toast.id)).size).toBe(3);
  });

  test('automatically dismisses success and warning notifications after their durations', () => {
    vi.useFakeTimers();
    const state = new ToastState();
    const successId = state.success('Saved');
    const warningId = state.warning('Review changes');

    vi.advanceTimersByTime(SUCCESS_TOAST_DURATION_MS);

    expect(state.toasts).toEqual([
      { id: warningId, message: 'Review changes', variant: 'warning' }
    ]);

    vi.advanceTimersByTime(WARNING_TOAST_DURATION_MS - SUCCESS_TOAST_DURATION_MS);

    expect(state.toasts).toEqual([]);
    expect(successId).not.toBe(warningId);
  });

  test('keeps error notifications until manually dismissed', () => {
    vi.useFakeTimers();
    const state = new ToastState();
    const errorId = state.error('Could not save');

    vi.advanceTimersByTime(WARNING_TOAST_DURATION_MS * 2);

    expect(state.toasts).toEqual([
      { id: errorId, message: 'Could not save', variant: 'error' }
    ]);
  });

  test('cancels a notification timer when manually dismissed', () => {
    vi.useFakeTimers();
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout');
    const state = new ToastState();
    const dismissedId = state.success('Dismissed');

    state.dismiss(dismissedId);

    expect(clearTimeoutSpy).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(SUCCESS_TOAST_DURATION_MS);
    expect(state.toasts).toEqual([]);
  });

  test('dismisses only the selected notification', () => {
    vi.useFakeTimers();
    const state = new ToastState();
    const retainedId = state.success('Retained');
    const dismissedId = state.error('Dismissed');

    state.dismiss(dismissedId);

    expect(state.toasts).toEqual([{ id: retainedId, message: 'Retained', variant: 'success' }]);
  });
});
