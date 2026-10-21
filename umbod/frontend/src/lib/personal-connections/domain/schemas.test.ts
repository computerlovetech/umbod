import { describe, expect, test } from 'vitest';
import { authorizationUrlSchema, emptyRequestSchema, enablementRequestSchema, selectionSchema, startAttemptSchema } from './schemas';
import { pendingAttempt, selection } from '../test-fixtures';

describe('personal connection wire contracts', () => {
  test('accepts exact backend projections', () => {
    expect(selectionSchema.parse(selection)).toEqual(selection);
    expect(startAttemptSchema.parse(pendingAttempt)).toEqual(pendingAttempt);
  });
  test.each(['http://provider.example', 'javascript:alert(1)', 'https://user:secret@provider.example', '//provider.example', 'invalid'])('rejects unsafe authorization URL %s', (url) => {
    expect(authorizationUrlSchema.safeParse(url).success).toBe(false);
  });
  test('rejects malformed projections and strict request extensions', () => {
    expect(selectionSchema.safeParse({ ...selection, enabled: 'true' }).success).toBe(false);
    expect(selectionSchema.safeParse({ ...selection, runtime_unavailable_reason: 'expired' }).success).toBe(false);
    expect(startAttemptSchema.safeParse({ ...pendingAttempt, status: 'connected' }).success).toBe(false);
    expect(startAttemptSchema.safeParse({ ...pendingAttempt, expires_at: 'tomorrow' }).success).toBe(false);
    expect(emptyRequestSchema.safeParse({ owner: 'other' }).success).toBe(false);
    expect(enablementRequestSchema.safeParse({ enabled: true, owner: 'other' }).success).toBe(false);
    expect(enablementRequestSchema.safeParse({ enabled: 1 }).success).toBe(false);
  });
});
