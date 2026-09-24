import { describe, expect, test } from 'vitest';
import { presentSaveFailureWithReconciliation } from './tool-activation-reconciliation';

const authoritative = { connector_id: 'connector-1', tools: [] };
const presentedAuthoritative = {
  authoritativeActivationResponse: authoritative,
  authoritativePolicyResponse: { connector_kind: 'native', connector_id: 'connector-1', tools: [] }
};

describe('presentSaveFailureWithReconciliation', () => {
  test('preserves a conflict status and body when the authoritative refetch rejects', async () => {
    const original = { status: 409, data: { status: 'conflict', policyConflicts: [{ tool_id: 'tool-1' }] } };
    const result = await presentSaveFailureWithReconciliation({
      originalError: new Error('conflict'),
      presentOriginal: () => original,
      loadAuthoritative: async () => { throw new Error('unavailable'); },
      presentAuthoritative: () => presentedAuthoritative
    });
    expect(result).toEqual(original);
    expect(result.data).not.toHaveProperty('authoritativeActivationResponse');
    expect(result.data).not.toHaveProperty('authoritativePolicyResponse');
  });

  test('preserves the presented operational status and body when the authoritative refetch rejects', async () => {
    const original = { status: 502, data: { status: 'failed', message: 'Downstream request failed' } };
    const result = await presentSaveFailureWithReconciliation({
      originalError: new Error('operational'),
      presentOriginal: () => original,
      loadAuthoritative: async () => Promise.reject(new Error('unavailable')),
      presentAuthoritative: () => presentedAuthoritative
    });
    expect(result).toEqual(original);
  });

  test('preserves the original failure when authoritative presentation rejects malformed data', async () => {
    const original = { status: 503, data: { status: 'failed', message: 'Save unavailable' } };
    const result = await presentSaveFailureWithReconciliation({
      originalError: new Error('save unavailable'),
      presentOriginal: () => original,
      loadAuthoritative: async () => ({ malformed: true }),
      presentAuthoritative: () => { throw new Error('malformed authoritative response'); }
    });
    expect(result).toEqual(original);
  });

  test('adds both authoritative views without changing the original presentation', async () => {
    const original = { status: 409, data: { status: 'conflict', policyConflicts: [] } };
    const result = await presentSaveFailureWithReconciliation({
      originalError: new Error('conflict'),
      presentOriginal: () => original,
      loadAuthoritative: async () => authoritative,
      presentAuthoritative: () => presentedAuthoritative
    });
    expect(result).toEqual({ status: 409, data: { ...original.data, ...presentedAuthoritative } });
  });
});
