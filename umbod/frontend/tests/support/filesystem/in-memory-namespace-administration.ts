import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { NamespaceAdministration } from '#lib/admin/filesystem/namespaces-port.js';
import { createNamespaceSchema, updateNamespaceSchema, sharedNamespaceSchema, type CreateNamespace, type SharedNamespace, type UpdateNamespace } from '#lib/admin/filesystem/domain/namespaces.js';

export class InMemoryNamespaceAdministration implements NamespaceAdministration {
  private readonly entries = new Map<string, SharedNamespace>();

  constructor(entries: SharedNamespace[], private readonly groupIds: readonly string[]) {
    for (const entry of entries) this.entries.set(entry.id, sharedNamespaceSchema.parse(entry));
  }

  list = async (): Promise<SharedNamespace[]> => structuredClone([...this.entries.values()]);

  create = async (input: CreateNamespace): Promise<SharedNamespace> => {
    const parsed = createNamespaceSchema.parse(input);
    this.validate(parsed);
    const entry = sharedNamespaceSchema.parse({ ...parsed, id: crypto.randomUUID(), root_node_id: crypto.randomUUID(), revision: 1, root_revision: 1, description: parsed.description ?? '' });
    this.entries.set(entry.id, entry);
    return structuredClone(entry);
  };

  update = async (id: string, input: UpdateNamespace): Promise<SharedNamespace> => {
    const parsed = updateNamespaceSchema.parse(input);
    const entry = this.entries.get(id);
    if (!entry) throw new HttpError(404, 'Not found', {});
    if (entry.revision !== parsed.expected_revision || parsed.description !== undefined && entry.root_revision !== parsed.expected_root_revision) throw new HttpError(409, 'Stale revision', {});
    this.validate(parsed, id);
    const updated = sharedNamespaceSchema.parse({ ...entry, name: parsed.name, groups: parsed.groups, revision: entry.revision + 1, description: parsed.description ?? entry.description, root_revision: entry.root_revision + (parsed.description !== undefined && parsed.description !== entry.description ? 1 : 0) });
    this.entries.set(id, updated);
    return structuredClone(updated);
  };

  private validate(input: CreateNamespace, id?: string): void {
    if (input.groups.some((group) => !this.groupIds.includes(group.group_id))) throw new HttpError(422, 'Unknown group', {});
    if ([...this.entries.values()].some((entry) => entry.id !== id && entry.name === input.name)) throw new HttpError(409, 'Duplicate name', {});
  }
}
