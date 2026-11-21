import type { PersonalServerAdministration } from '#lib/admin/personal-mcp-servers/administration.js';
import type { PersonalOAuthSetupAdministration } from '#lib/admin/personal-mcp-servers/setup-administration.js';
import type { PersonalPolicy } from '#lib/admin/personal-mcp-servers/domain/schemas.js';
import type { SetupDiscovery, SetupStatus } from '#lib/admin/personal-mcp-servers/domain/setup.js';
import type { DownstreamMcpConnector } from '#lib/admin/downstream-mcp-connectors.js';
import { AuthenticationRequiredError, HttpError, SchemaValidationError } from '#lib/admin/infrastructure/transport.js';

type SetupSnapshot<T> = T extends readonly unknown[] ? ReadonlyArray<SetupSnapshot<T[number]>> : T extends object ? { readonly [Key in keyof T]: SetupSnapshot<T[Key]> } : T;

const compatibilityGuidance: Record<Extract<SetupStatus['state'], { status: 'failed' }>['reason'], string> = {
  resource_mismatch: 'The MCP endpoint must exactly match the server’s resource URL, including its path and trailing slash (/). Check whether a final / is required in Edit, then check again.',
  issuer_mismatch: 'The authorization provider does not match. Choose the correct provider in Edit.',
  ambiguous_issuer: 'The server lists multiple providers. Select an authorization provider in Edit.',
  pkce_s256_required: 'This provider does not support secure sign-in. Ask its administrator to update the server.',
  authorization_code_required: 'This provider does not support secure sign-in. Ask its administrator to update the server.',
  code_response_required: 'This provider does not support secure sign-in. Ask its administrator to update the server.',
  client_auth_required: 'The client authentication method is unsupported. Fix the OAuth application settings.',
  registration_unavailable: 'Automatic registration is unavailable. Use an existing client in Edit.',
  registration_contract_mismatch: 'The provider returned unsupported client settings. Review the configuration in Edit.',
  provider_rejected: 'The provider rejected this configuration. Review the settings in Edit.',
  invalid_response: 'The provider returned an unsupported response. Review the configuration in Edit.',
  unsupported: 'The provider does not support this configuration. Review the settings in Edit.',
  scope_mismatch: 'The provider returned different permissions. Review the requested permissions in settings.',
  timeout: 'The provider did not respond in time. Check its availability before checking again.',
  network_failure: 'The provider could not be reached. Check its availability before checking again.',
  unexpected_failure: 'The check could not complete. Check the provider before checking again.'
};

export class PersonalOAuthSetupState {
  private currentStatus = $state.raw<SetupStatus | null>(null);
  private currentPolicy = $state.raw<PersonalPolicy | null>(null);
  private pendingOperation = $state<'loading' | 'discovery' | 'validation' | null>(null);
  private feedback = $state('');
  private blocked = $state(false);
  private denied = $state(false);
  private id: string | null = null;
  private epoch = 0;
  private disposed = false;
  constructor(
    private readonly setup: PersonalOAuthSetupAdministration,
    private readonly servers: PersonalServerAdministration,
    private readonly validationChanged: (id: string, validated: boolean) => void,
    private readonly publicationChanged: (id: string, status: DownstreamMcpConnector['publication_status']) => void,
    private readonly accessLost: () => void,
    private readonly mutationLockChanged: (locked: boolean) => void,
    private readonly available: () => boolean = () => true
  ) {}
  get status(): SetupSnapshot<SetupStatus> | null { return this.currentStatus; }
  get policy(): SetupSnapshot<PersonalPolicy> | null { return this.currentPolicy; }
  get pending(): string | null { return this.pendingOperation; }
  get message(): string { return this.feedback; }
  get accessDenied(): boolean { return this.denied; }
  get requiresRefresh(): boolean { return this.blocked || this.currentStatus?.state.status === 'in_progress'; }
  get locked(): boolean { return this.disposed || this.denied || this.blocked || this.pendingOperation !== null || !this.available() || this.currentStatus?.state.status === 'in_progress'; }
  get canCheck(): boolean { return !this.locked && this.id !== null && this.currentPolicy !== null && this.currentStatus !== null; }
  sidebarLabel(connectorId: string): string {
    if (this.id !== connectorId || this.disposed || this.denied || this.blocked) return 'Check unavailable';
    if (this.pendingOperation === 'loading') return 'Loading check';
    if (this.pendingOperation === 'validation' || this.pendingOperation === 'discovery' || this.currentStatus?.state.status === 'in_progress') return 'Checking configuration';
    if (!this.currentPolicy || !this.currentStatus) return 'Check unavailable';
    switch (this.currentStatus.state.status) {
      case 'validated': return this.validated ? 'Configuration ready' : 'Check required';
      case 'discovered':
      case 'scope_mismatch': return 'Changes required';
      case 'failed': return this.outcome === 'changes_required' ? 'Changes required' : 'Check failed';
      default: return 'Check required';
    }
  }
  get validated(): boolean { return this.currentStatus?.state.status === 'validated' && this.currentStatus.policy_revision === this.currentPolicy?.revision; }
  get discovery(): SetupSnapshot<SetupDiscovery> | null {
    const state = this.currentStatus?.state;
    return state?.status === 'discovered' ? state.discovery : state?.status === 'validated' || state?.status === 'scope_mismatch' ? state.result.discovery : null;
  }
  get returnedScopes(): readonly string[] | null {
    return this.currentStatus?.state.status === 'scope_mismatch' ? this.currentStatus.state.result.returned_scopes : null;
  }
  get editProposal(): { issuer: string; scopes: readonly string[] } | undefined {
    const state = this.currentStatus?.state;
    if (!this.currentPolicy || !(state?.status === 'discovered' || state?.status === 'scope_mismatch')) return undefined;
    const discovery = state.status === 'discovered' ? state.discovery : state.result.discovery;
    return { issuer: discovery.issuer_url, scopes: this.currentPolicy.requested_scopes };
  }
  get outcome(): 'loading' | 'checking' | 'ready' | 'changes_required' | 'failed' | 'required' | 'unknown' | 'denied' {
    if (this.denied) return 'denied';
    if (this.pendingOperation === 'loading') return 'loading';
    if (this.pendingOperation !== null) return 'checking';
    if (this.requiresRefresh) return 'unknown';
    if (this.validated) return 'ready';
    const state = this.currentStatus?.state;
    if (state?.status === 'discovered' || state?.status === 'scope_mismatch') return 'changes_required';
    if (state?.status === 'failed') return ['timeout', 'network_failure', 'unexpected_failure'].includes(state.reason) ? 'failed' : 'changes_required';
    return 'required';
  }
  private current(token: number): boolean { return !this.disposed && !this.denied && this.epoch === token; }
  private invalidate(): void {
    if (this.id) this.validationChanged(this.id, false);
    this.currentStatus = null;
  }
  private accept(status: SetupStatus): void {
    if (!this.currentPolicy || status.connector_id !== this.id || status.policy_revision !== this.currentPolicy.revision) throw new SchemaValidationError('inbound', []);
    this.currentStatus = status;
    this.validationChanged(status.connector_id, this.validated);
    this.blocked = false;
    if (status.state.status === 'failed') this.feedback = compatibilityGuidance[status.state.reason];
    if (status.state.status === 'scope_mismatch') this.feedback = compatibilityGuidance.scope_mismatch;
  }
  load = async (id: string): Promise<void> => {
    if (this.disposed || this.denied || this.pendingOperation && id === this.id) return;
    this.finish();
    this.invalidate();
    this.id = id;
    this.currentPolicy = null;
    const token = ++this.epoch;
    this.pendingOperation = 'loading';
    this.feedback = '';
    try {
      const [policy, status, connector] = await Promise.all([this.servers.policy(id), this.setup.status(id), this.servers.get(id)]);
      if (!this.current(token)) return;
      if (policy.connector_id !== id || connector.connector_id !== id) throw new SchemaValidationError('inbound', []);
      this.publicationChanged(id, connector.publication_status);
      this.currentPolicy = policy;
      this.accept(status);
    } catch (error) { if (this.current(token)) this.fail(error, false); }
    finally { if (this.current(token)) this.finish(); }
  };
  refresh = async (): Promise<void> => { if (this.id) await this.load(this.id); };
  check = async (): Promise<void> => {
    if (!this.canCheck || !this.id || !this.currentPolicy || !this.currentStatus) return;
    const id = this.id;
    const revision = this.currentStatus.revision;
    const token = this.epoch;
    this.invalidate();
    this.pendingOperation = 'validation';
    this.mutationLockChanged(true);
    this.feedback = '';
    try {
      const status = await this.setup.validate(id, { expected_revision: revision });
      if (!this.current(token) || this.id !== id) return;
      this.accept(status);
      if (!this.current(token) || this.id !== id) return;
      if (status.state.status !== 'failed' || status.state.stage !== 'discovery' || status.state.reason !== 'issuer_mismatch' || !(this.currentPolicy?.client.kind === 'preconfigured_public' || this.currentPolicy?.client.kind === 'preconfigured_confidential')) return;
      this.pendingOperation = 'discovery';
      const discovered = await this.setup.discover(id, { expected_revision: status.revision });
      if (!this.current(token) || this.id !== id) return;
      this.accept(discovered);
      if (discovered.state.status === 'discovered') this.feedback = 'The server requires a different authorization provider. Review the issuer in settings.';
    } catch (error) { if (this.current(token)) this.fail(error, true); }
    finally { if (this.current(token)) this.finish(); }
  };
  private fail(error: unknown, mutation: boolean): void {
    this.invalidate();
    if (error instanceof AuthenticationRequiredError || error instanceof HttpError && [401, 403].includes(error.status)) {
      this.denied = true;
      this.currentPolicy = null;
      this.epoch++;
      this.finish();
      this.accessLost();
      this.feedback = 'Administration access was lost. Sign in again before reloading this page.';
      return;
    }
    this.blocked = true;
    this.feedback = mutation && !(error instanceof HttpError && error.status >= 400 && error.status < 500) && !(error instanceof SchemaValidationError && error.direction === 'outbound')
      ? 'The check may have completed. Refresh status before starting another.'
      : error instanceof HttpError && error.status === 409
        ? 'Settings changed elsewhere. Refresh status before continuing.'
        : 'The configuration could not be checked. Refresh status before continuing.';
  }
  private finish(): void {
    const operation = this.pendingOperation;
    this.pendingOperation = null;
    if (operation === 'validation' || operation === 'discovery') this.mutationLockChanged(false);
  }
  policyChanged = (connector: DownstreamMcpConnector): void => {
    if (this.id !== connector.connector_id || this.disposed) return;
    this.epoch++;
    this.finish();
    this.invalidate();
    this.publicationChanged(connector.connector_id, connector.publication_status);
    void this.load(connector.connector_id);
  };
  detach = (): void => {
    this.epoch++;
    this.invalidate();
    this.currentPolicy = null;
    this.id = null;
    this.finish();
  };
  dispose = (): void => { this.detach(); this.disposed = true; };
}
