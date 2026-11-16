import type { PersonalServerAdministration } from '$lib/admin/personal-mcp-servers/administration';
import type { PersonalOAuthSetupAdministration } from '$lib/admin/personal-mcp-servers/setup-administration';
import type { PersonalPolicy, PersonalSettings } from '$lib/admin/personal-mcp-servers/domain/schemas';
import type { SetupDiscovery, SetupStatus } from '$lib/admin/personal-mcp-servers/domain/setup';
import type { DownstreamMcpConnector } from '$lib/admin/downstream-mcp-connectors';
import { AuthenticationRequiredError, HttpError, SchemaValidationError } from '$lib/admin/infrastructure/transport';

type SetupSnapshot<T> = T extends readonly unknown[] ? ReadonlyArray<SetupSnapshot<T[number]>> : T extends object ? { readonly [Key in keyof T]: SetupSnapshot<T[Key]> } : T;

const compatibilityGuidance: Partial<Record<Extract<SetupStatus['state'], { status: 'failed' }>['reason'], string>> = {
  resource_mismatch: 'The provider metadata identifies a different MCP resource. Check the saved MCP endpoint.',
  issuer_mismatch: 'The configured issuer does not match provider metadata. Discover settings and explicitly approve the correct issuer.',
  ambiguous_issuer: 'The provider advertises multiple authorization servers. Configure an existing client with an explicit issuer.',
  pkce_s256_required: 'The authorization server must support PKCE S256.',
  authorization_code_required: 'The authorization server must support the authorization code grant.',
  code_response_required: 'The authorization server must support the code response type.',
  client_auth_required: 'The selected OAuth client authentication method is not supported. Update the OAuth application settings.',
  registration_unavailable: 'Automatic client registration is unavailable. Configure an existing client ID instead.',
  registration_contract_mismatch: 'The registration response changed the requested client settings or returned an unsupported client secret.',
  scope_mismatch: 'The provider returned different scopes. Review and explicitly approve the requested permissions.'
};

export class PersonalOAuthSetupState {
  private currentStatus = $state.raw<SetupStatus | null>(null);
  private currentPolicy = $state.raw<PersonalPolicy | null>(null);
  private selectedScopes = $state.raw<string[]>([]);
  private pendingOperation = $state<'loading' | 'discovery' | 'validation' | 'saving' | null>(null);
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
    private readonly lockChanged: (locked: boolean) => void,
    private readonly available: () => boolean = () => true
  ) {}
  get status(): SetupSnapshot<SetupStatus> | null { return this.currentStatus; }
  get policy(): SetupSnapshot<PersonalPolicy> | null { return this.currentPolicy; }
  get scopes(): readonly string[] { return this.selectedScopes; }
  get pending(): string | null { return this.pendingOperation; }
  get message(): string { return this.feedback; }
  get accessDenied(): boolean { return this.denied; }
  get requiresRefresh(): boolean { return this.blocked || this.currentStatus?.state.status === 'in_progress'; }
  get locked(): boolean { return this.disposed || this.denied || this.blocked || this.pendingOperation !== null || !this.available() || this.currentStatus?.state.status === 'in_progress'; }
  get validated(): boolean { return this.currentStatus?.state.status === 'validated' && this.currentStatus.policy_revision === this.currentPolicy?.revision; }
  get discovery(): SetupSnapshot<SetupDiscovery> | null {
    const state = this.currentStatus?.state;
    return state?.status === 'discovered' ? state.discovery : state?.status === 'validated' || state?.status === 'scope_mismatch' ? state.result.discovery : null;
  }
  get returnedScopes(): readonly string[] | null {
    return this.currentStatus?.state.status === 'scope_mismatch' ? this.currentStatus.state.result.returned_scopes : null;
  }
  get canApprove(): boolean { return !this.locked && this.currentPolicy !== null && this.currentPolicy.client.kind !== 'preconfigured_confidential'; }
  private current(token: number): boolean { return !this.disposed && !this.denied && this.epoch === token; }
  private invalidate(): void {
    if (this.id) this.validationChanged(this.id, false);
    this.currentStatus = null;
    this.selectedScopes = [];
  }
  private accept(status: SetupStatus): void {
    if (!this.currentPolicy || status.connector_id !== this.id || status.policy_revision !== this.currentPolicy.revision) throw new SchemaValidationError('inbound', []);
    this.currentStatus = status;
    this.selectedScopes = [...this.currentPolicy.requested_scopes];
    this.validationChanged(status.connector_id, this.validated);
    this.blocked = false;
    if (status.state.status === 'failed') {
      const guidance = compatibilityGuidance[status.state.reason] ?? 'Check the provider settings and supported OAuth registration mode before explicitly trying again.';
      this.feedback = `Setup validation did not complete. ${guidance} Nothing was retried automatically. Sign-in was not tested.`;
    }
  }
  load = async (id: string): Promise<void> => {
    if (this.disposed || this.denied || this.pendingOperation && id === this.id) return;
    this.invalidate();
    this.id = id;
    this.currentPolicy = null;
    const token = ++this.epoch;
    this.pendingOperation = 'loading';
    this.lockChanged(true);
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
  toggleScope = (scope: string, selected: boolean): void => {
    if (this.locked || !this.discovery?.available_scopes.includes(scope)) return;
    this.selectedScopes = selected ? [...new Set([...this.selectedScopes, scope])].sort() : this.selectedScopes.filter((value) => value !== scope);
  };
  discover = async (): Promise<void> => { await this.run('discovery'); };
  validate = async (): Promise<void> => { await this.run('validation'); };
  private async run(operation: 'discovery' | 'validation'): Promise<void> {
    if (this.locked || !this.id || !this.currentPolicy || !this.currentStatus) return;
    const id = this.id;
    const revision = this.currentStatus.revision;
    const token = this.epoch;
    this.invalidate();
    this.pendingOperation = operation;
    this.lockChanged(true);
    this.feedback = '';
    try {
      const status = await (operation === 'discovery' ? this.setup.discover(id, { expected_revision: revision }) : this.setup.validate(id, { expected_revision: revision }));
      if (this.current(token)) this.accept(status);
    } catch (error) { if (this.current(token)) this.fail(error, true); }
    finally { if (this.current(token)) this.finish(); }
  }
  approveSelectedScopes = async (): Promise<void> => { if (this.discovery && this.selectedScopes.length > 0) await this.save(this.selectedScopes); };
  approveSuggestedScopes = async (): Promise<void> => { if (this.returnedScopes) await this.save([...this.returnedScopes]); };
  acceptIssuer = async (): Promise<void> => {
    if (this.currentPolicy?.client.kind !== 'preconfigured_public' || !this.discovery) return;
    await this.save(this.currentPolicy.requested_scopes, this.discovery.issuer_url);
  };
  private async save(scopes: readonly string[], issuer?: string): Promise<void> {
    if (!this.canApprove || !this.id || !this.currentPolicy || this.currentPolicy.client.kind === 'preconfigured_confidential') return;
    const id = this.id;
    const token = this.epoch;
    const client = this.currentPolicy.client;
    const settings: PersonalSettings = { requested_scopes: [...scopes], client: client.kind === 'preconfigured_public' && issuer ? { ...client, issuer_url: issuer } : client };
    const revision = this.currentPolicy.revision;
    this.invalidate();
    this.pendingOperation = 'saving';
    this.lockChanged(true);
    this.feedback = '';
    try {
      const policy = await this.servers.replacePolicy(id, { expected_revision: revision, settings });
      if (!this.current(token)) return;
      this.currentPolicy = policy;
      const [connector, status] = await Promise.all([this.servers.get(id), this.setup.status(id)]);
      if (!this.current(token)) return;
      if (connector.connector_id !== id) throw new SchemaValidationError('inbound', []);
      this.publicationChanged(id, connector.publication_status);
      this.accept(status);
      this.feedback = this.validated ? 'OAuth settings are unchanged. Configuration validation remains current.' : 'OAuth settings saved. Validate setup again before publishing. Existing users may need to sign in again.';
    } catch (error) { if (this.current(token)) this.fail(error, true); }
    finally { if (this.current(token)) this.finish(); }
  }
  private fail(error: unknown, mutation: boolean): void {
    this.invalidate();
    if (error instanceof AuthenticationRequiredError || error instanceof HttpError && [401, 403].includes(error.status)) {
      this.denied = true;
      this.currentPolicy = null;
      this.pendingOperation = null;
      this.epoch++;
      this.lockChanged(false);
      this.accessLost();
      this.feedback = 'Administration access was lost. Sign in again before reloading this page.';
      return;
    }
    this.blocked = true;
    this.feedback = mutation && !(error instanceof HttpError && error.status >= 400 && error.status < 500) && !(error instanceof SchemaValidationError && error.direction === 'outbound')
      ? 'The outcome is unknown. Refresh setup status before making another request. Registration may have occurred at the provider. Nothing was retried.'
      : error instanceof HttpError && error.status === 409
        ? 'OAuth settings or setup activity changed elsewhere. Refresh setup status before continuing. Nothing was retried.'
        : 'Setup settings could not be checked or saved. Check the provider configuration and permissions, then refresh setup status. Nothing was retried.';
  }
  private finish(): void { this.pendingOperation = null; this.lockChanged(false); }
  policyChanged = (connector: DownstreamMcpConnector): void => {
    if (this.id !== connector.connector_id || this.disposed) return;
    this.epoch++;
    this.pendingOperation = null;
    this.invalidate();
    this.publicationChanged(connector.connector_id, connector.publication_status);
    void this.load(connector.connector_id);
  };
  detach = (): void => {
    this.epoch++;
    this.invalidate();
    this.currentPolicy = null;
    this.id = null;
    this.pendingOperation = null;
    this.lockChanged(false);
  };
  dispose = (): void => { this.detach(); this.disposed = true; };
}
