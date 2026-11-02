import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import { resolveWorkspaceAccess, type AdminAccess } from './admin-access';
import type { WorkspaceApi } from './api';

export class WorkspaceAccessState {
  adminAccess = $state<AdminAccess | 'checking'>('checking');
  accountIdentity = $state<HeaderAccountIdentityState>({ kind: 'hidden' });
  private disposed = false;

  constructor(private readonly api: WorkspaceApi) {}

  load = async (): Promise<void> => {
    const result = await resolveWorkspaceAccess(this.api);
    if (this.disposed) return;
    this.adminAccess = result.adminAccess;
    this.accountIdentity = result.accountIdentity;
  };

  dispose = (): void => {
    this.disposed = true;
    this.adminAccess = 'checking';
    this.accountIdentity = { kind: 'hidden' };
  };
}
