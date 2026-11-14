import { z } from 'zod';
import type { Transport } from '../infrastructure/transport';
import type { NamespaceAdministration } from './namespaces-port';
import { createNamespaceSchema, updateNamespaceSchema, sharedNamespaceSchema, sharedNamespacesSchema, type CreateNamespace, type UpdateNamespace, type SharedNamespace } from './domain/namespaces';

export class NamespacesRoute implements NamespaceAdministration {
  constructor(private readonly transport: Transport) {}
  list = async (): Promise<SharedNamespace[]> => {
    const result = await this.transport.request({ method: 'GET', path: '/admin/filesystem/namespaces', outputSchema: sharedNamespacesSchema });
    return result.namespaces;
  };
  create = (body: CreateNamespace): Promise<SharedNamespace> => this.transport.request({
    method: 'POST', path: '/admin/filesystem/namespaces', body, inputSchema: createNamespaceSchema, outputSchema: sharedNamespaceSchema
  });
  update = (id: string, body: UpdateNamespace): Promise<SharedNamespace> => this.transport.request({
    method: 'PUT', path: '/admin/filesystem/namespaces/' + z.uuid().parse(id), body, inputSchema: updateNamespaceSchema, outputSchema: sharedNamespaceSchema
  });
}
