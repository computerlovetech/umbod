import type { CreateNamespace, SharedNamespace, UpdateNamespace } from './domain/namespaces';

export interface NamespaceAdministration {
  list(): Promise<SharedNamespace[]>;
  create(input: CreateNamespace): Promise<SharedNamespace>;
  update(id: string, input: UpdateNamespace): Promise<SharedNamespace>;
}
