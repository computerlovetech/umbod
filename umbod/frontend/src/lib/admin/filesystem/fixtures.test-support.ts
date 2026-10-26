import type { RootAccess } from './domain/schemas';
export function rootPolicy(overrides: Partial<RootAccess> = {}): RootAccess {
  return { root_id: '00000000-0000-4000-8000-000000000001', status: 'uninitialized', revision: 'initial', groups: [], unmanaged_groups: [], suggested_issuer: '', group_claim: 'groups', ...overrides };
}
