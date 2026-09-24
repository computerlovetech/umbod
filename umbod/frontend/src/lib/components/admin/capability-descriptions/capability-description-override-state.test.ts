import { describe, expect, test } from 'vitest';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import { CapabilityDescriptionOverrideState } from './capability-description-override-state.svelte';

const system = { connector_kind: 'native' as const, connector_id: 'slack', base_description: 'System description', effective_description: 'System description', override: { state: 'system' as const, revision: 0 } };

describe('CapabilityDescriptionOverrideState', () => {
  test('validates blank, control characters, and overlength drafts', () => {
    const state = new CapabilityDescriptionOverrideState(system);
    state.updateDraft('   '); expect(state.validationMessage).toBeTruthy();
    state.updateDraft('bad\u0000text'); expect(state.validationMessage).toBeTruthy();
    state.updateDraft('x'.repeat(301)); expect(state.validationMessage).toBeTruthy();
    state.updateDraft('Agent-friendly text'); expect(state.validationMessage).toBeUndefined();
  });

  test('preserves draft on save failure', async () => {
    const state = new CapabilityDescriptionOverrideState(system);
    state.updateDraft('My draft');
    await state.save(async () => { throw new BrowserRequestError(undefined, new Error('offline')); });
    expect(state.draft).toBe('My draft');
    expect(state.message).toContain('not saved');
  });

  test('refreshes current state while preserving draft on stale conflict', async () => {
    const state = new CapabilityDescriptionOverrideState(system);
    state.updateDraft('My draft');
    await state.save(async () => ({ kind: 'conflict' as const, current: { ...system, effective_description: 'Other edit', override: { state: 'overridden' as const, description: 'Other edit', revision: 2 } } }));
    expect(state.current?.effective_description).toBe('Other edit');
    expect(state.draft).toBe('My draft');
    expect(state.message).toContain('changed');
  });
});
