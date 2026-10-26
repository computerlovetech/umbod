import { HttpError } from '../infrastructure/transport';
import type { FilesystemAdministration } from './port';
import { replaceRootAccessSchema, rootAccessSchema, type ReplaceRootAccess, type RootAccess } from './domain/schemas';

export class InMemoryFilesystemAdministration implements FilesystemAdministration {
  private policy: RootAccess;
  constructor(policy: RootAccess) { this.policy = rootAccessSchema.parse(policy); }
  async getRootAccess(): Promise<RootAccess> { return structuredClone(this.policy); }
  async replaceRootAccess(input: ReplaceRootAccess): Promise<RootAccess> {
    const parsed = replaceRootAccessSchema.parse(input);
    if (this.policy.status === 'conflict') throw new HttpError(409, '', { detail: { code: 'filesystem_policy_conflict' } });
    if (parsed.expected_revision !== this.policy.revision) throw new HttpError(409, '', { detail: { code: 'filesystem_policy_stale' } });
    if (parsed.groups.some((group) => this.policy.unmanaged_groups.some((unmanaged) => group.issuer === unmanaged.issuer && group.group_id === unmanaged.group_id))) throw new HttpError(409, '', { detail: { code: 'filesystem_policy_conflict' } });
    this.policy = rootAccessSchema.parse({ ...this.policy, status: 'ready', revision: crypto.randomUUID(), groups: parsed.groups });
    return this.getRootAccess();
  }
}
