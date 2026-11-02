import type { Transport } from '$lib/admin/infrastructure/transport';
import type { WorkspaceProfileSource } from '../api';
import { workspaceProfileSchema, type WorkspaceProfile } from '../domain/profile';

export class ProfileRoute implements WorkspaceProfileSource {
  constructor(private readonly transport: Transport) {}

  get(): Promise<WorkspaceProfile> {
    return this.transport.request({ method: 'GET', path: '/me/profile', outputSchema: workspaceProfileSchema });
  }
}
