import { describe, expect, test } from 'vitest';
import { workspaceProfileSchema } from './profile';

const user = { id: 'user-1', name: 'Alex', email: null, picture: null };

describe('workspace profile schema', () => {
  test.each([true, false])('accepts explicit administration capability %s and nullable identity', (administration): void => {
    expect(workspaceProfileSchema.parse({ user, capabilities: { administration } })).toEqual({ user, capabilities: { administration } });
  });

  test.each([
    {},
    { capabilities: {} },
    { capabilities: null },
    { capabilities: { administration: null } },
    { capabilities: { administration: 'true' } },
    { capabilities: { administration: 1 } }
  ])('rejects missing or invalid capabilities %j', (capabilityFields): void => {
    expect(workspaceProfileSchema.safeParse({ user, ...capabilityFields }).success).toBe(false);
  });

  test.each([
    { id: 'user-1', name: 'Alex', email: null },
    { id: 'user-1', name: 'Alex', picture: null },
    { ...user, id: 1 },
    { ...user, email: 1 },
    { ...user, picture: 1 }
  ])('rejects incomplete or invalid identity %j', (identity): void => {
    expect(workspaceProfileSchema.safeParse({ user: identity, capabilities: { administration: false } }).success).toBe(false);
  });
});
