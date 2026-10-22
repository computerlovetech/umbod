import { adminApi } from '$lib/admin/infrastructure/admin-api';
import { AuthenticationRequiredError, HttpError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import type { DownstreamMcpConnectorsRoute } from '$lib/admin/downstream-mcp-connectors-api';

export type CommonMcpAction = 'publish' | 'unpublish' | 'delete';
export class DownstreamMcpMutationState {
  pending = $state<{ action: CommonMcpAction; id: string; name: string } | null>(null);
  busy = $state(false);
  formLocked = $state(false);
  registrationLocked = $state(false);
  blocked = $state(false);
  authenticationLost = $state(false);
  message = $state('');
  private disposed = false;
  constructor(private readonly api: Pick<DownstreamMcpConnectorsRoute, 'publish' | 'unpublish' | 'delete' | 'list'> = adminApi().downstreamMcpConnectors, private readonly navigate: (id?: string) => void = (id) => { window.location.assign(`/admin/downstream-mcp-connectors${id ? `?connector=${encodeURIComponent(id)}` : ''}`); }) {}
  get locked(): boolean { return this.registrationLocked || this.formLocked || this.busy || this.blocked || this.authenticationLost || this.disposed; }
  setRegistrationLocked = (locked: boolean): void => { this.registrationLocked = locked; };
  setFormLocked = (locked: boolean): void => { this.formLocked = locked; };
  request = (action: CommonMcpAction, id: string, name: string): void => {
    if (!this.locked) this.pending = { action, id, name };
  };
  cancel = (): void => { if (!this.busy) this.pending = null; };
  loseAccess = (): void => {
    this.authenticationLost = true;
    this.pending = null;
    this.message = 'Administration access was lost. Sign in again before reloading this page.';
  };
  reload = (): void => { if (!this.busy && !this.authenticationLost) this.navigate(); };
  confirm = async (): Promise<void> => {
    if (this.locked || !this.pending) return;
    const { action, id } = this.pending;
    this.pending = null;
    this.busy = true;
    this.message = '';
    try {
      await this.api[action](id);
      if (this.disposed || this.authenticationLost) return;
      const records = await this.api.list();
      if (this.disposed || this.authenticationLost) return;
      const selected = action === 'delete' ? records.connectors[0]?.connector_id : id;
      this.blocked = true;
      this.navigate(selected);
    } catch (error) {
      if (this.disposed) return;
      if (error instanceof AuthenticationRequiredError || error instanceof HttpError && [401, 403].includes(error.status)) this.loseAccess();
      else if (error instanceof HttpError && error.status === 409) {
        this.message = 'Remove connector and tool grants in Group permissions before deleting this server. Deletion was not retried.';
      } else if (error instanceof HttpError && error.status >= 400 && error.status < 500 || error instanceof SchemaValidationError && error.direction === 'outbound') {
        this.message = 'The change was rejected. Reload authoritative state before trying again.';
        this.blocked = true;
      } else {
        this.blocked = true;
        this.message = 'The outcome is unknown. Reload authoritative server state before any further changes. Nothing will be replayed.';
      }
    } finally { if (!this.disposed) this.busy = false; }
  };
  dispose = (): void => { this.disposed = true; this.pending = null; };
}
