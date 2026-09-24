import { describe, expect, test } from 'vitest';
import { calculateSelectOverlayGeometry, SelectState, type SelectOption } from './select-state.svelte';

const options: SelectOption[] = [
  { value: 'first', label: 'First' },
  { value: 'disabled', label: 'Disabled', disabled: true },
  { value: 'last', label: 'Last' }
];

describe('SelectState', () => {
  test('opens at the selected option and closes after selection', () => {
    const state = new SelectState(options, 'first');

    state.open();
    expect(state.isOpen).toBe(true);
    expect(state.activeValue).toBe('first');

    expect(state.select('last')).toBe('last');
    expect(state.selectedValue).toBe('last');
    expect(state.isOpen).toBe(false);
  });

  test('traverses enabled options and wraps in both directions', () => {
    const state = new SelectState(options, 'first');

    state.open();
    state.moveNext();
    expect(state.activeValue).toBe('last');
    state.moveNext();
    expect(state.activeValue).toBe('first');
    state.movePrevious();
    expect(state.activeValue).toBe('last');
  });

  test('moves to boundaries and rejects disabled selection', () => {
    const state = new SelectState(options, 'first');

    state.open();
    state.moveLast();
    expect(state.activeValue).toBe('last');
    state.moveFirst();
    expect(state.activeValue).toBe('first');
    expect(state.select('disabled')).toBeUndefined();
    expect(state.selectedValue).toBe('first');
  });
});

describe('calculateSelectOverlayGeometry', () => {
  test('places the list below with the trigger width and available maximum height', () => {
    const geometry = calculateSelectOverlayGeometry({ left: 100, right: 300, top: 100, bottom: 144, width: 200 }, { width: 1000, height: 800, offsetLeft: 0, offsetTop: 0 }, 400);

    expect(geometry).toEqual({ left: 100, top: 148, width: 200, maxHeight: 288, placement: 'below' });
  });

  test('flips above when below has insufficient space', () => {
    const geometry = calculateSelectOverlayGeometry({ left: 100, right: 300, top: 650, bottom: 694, width: 200 }, { width: 1000, height: 720, offsetLeft: 0, offsetTop: 0 }, 400);

    expect(geometry.placement).toBe('above');
    expect(geometry.maxHeight).toBe(288);
    expect(geometry.top).toBe(358);
  });

  test('positions a short list directly above its trigger', () => {
    const geometry = calculateSelectOverlayGeometry({ left: 100, right: 300, top: 428, bottom: 472, width: 200 }, { width: 1000, height: 560, offsetLeft: 0, offsetTop: 0 }, 104);

    expect(geometry.placement).toBe('above');
    expect(geometry.maxHeight).toBe(104);
    expect(geometry.top).toBe(320);
  });

  test('clamps horizontally and limits height to the available viewport', () => {
    const geometry = calculateSelectOverlayGeometry({ left: 350, right: 470, top: 20, bottom: 64, width: 120 }, { width: 390, height: 180, offsetLeft: 0, offsetTop: 0 }, 400);

    expect(geometry.left).toBe(262);
    expect(geometry.width).toBe(120);
    expect(geometry.maxHeight).toBe(104);
  });
});
