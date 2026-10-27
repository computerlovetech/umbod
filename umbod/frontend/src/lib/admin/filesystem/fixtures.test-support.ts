import type { RootAccess } from './domain/schemas';
export function rootPolicy(overrides: Partial<RootAccess> = {}): RootAccess {
  return { status: 'uninitialized', revision: 'initial', groups: [], blocked_group_ids: [], ...overrides };
}
