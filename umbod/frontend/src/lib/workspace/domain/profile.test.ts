import { describe, expect, test } from 'vitest';
import { workspaceProfileSchema } from './profile';

const user = { id: 'user-1', name: 'Alex', email: null, picture: null };

describe('workspace profile schema', () => {
  test.each([{}, { identity_key: null }, { identity_key: '' }, { identity_key: 1 }])('rejects absent or invalid trusted identity keys %j without falling back to the raw subject', (fields): void => {
    expect(workspaceProfileSchema.safeParse({ ...fields, user, capabilities: { administration: false } }).success).toBe(false);
  });

  test.each([true, false])('accepts explicit administration capability %s and nullable identity', (administration): void => {
    expect(workspaceProfileSchema.parse({ identity_key: 'opaque-account-key', user, capabilities: { administration } })).toEqual({ identity_key: 'opaque-account-key', user, capabilities: { administration } });
  });

  test.each([
    {},
    { capabilities: {} },
    { capabilities: null },
    { capabilities: { administration: null } },
    { capabilities: { administration: 'true' } },
    { capabilities: { administration: 1 } }
  ])('rejects missing or invalid capabilities %j', (capabilityFields): void => {
    expect(workspaceProfileSchema.safeParse({ identity_key: 'opaque-account-key', user, ...capabilityFields }).success).toBe(false);
  });

  test.each([
    { id: 'user-1', name: 'Alex', email: null },
    { id: 'user-1', name: 'Alex', picture: null },
    { ...user, id: 1 },
    { ...user, email: 1 },
    { ...user, picture: 1 }
  ])('rejects incomplete or invalid identity %j', (identity): void => {
    expect(workspaceProfileSchema.safeParse({ identity_key: 'opaque-account-key', user: identity, capabilities: { administration: false } }).success).toBe(false);
  });
});
