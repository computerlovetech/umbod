import type { Transport } from '../infrastructure/transport';
import type { FilesystemAdministration } from './port';
import { replaceRootAccessSchema, rootAccessSchema, type ReplaceRootAccess, type RootAccess } from './domain/schemas';

export class FilesystemRoute implements FilesystemAdministration {
  constructor(private readonly transport: Transport) {}
  getRootAccess(): Promise<RootAccess> {
    return this.transport.request({ method: 'GET', path: '/admin/filesystem/root-access', outputSchema: rootAccessSchema });
  }
  replaceRootAccess(body: ReplaceRootAccess): Promise<RootAccess> {
    return this.transport.request({ method: 'PUT', path: '/admin/filesystem/root-access', body, inputSchema: replaceRootAccessSchema, outputSchema: rootAccessSchema });
  }
}
