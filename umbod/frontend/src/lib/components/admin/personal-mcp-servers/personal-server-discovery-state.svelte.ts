import type { PersonalServerDiscovery } from '#lib/admin/personal-mcp-servers/discovery-administration.js';
import { EndpointResourceMismatchError, discoveryEndpointSchema, type AutomaticClient, type EndpointDiscoveryResult } from '#lib/admin/personal-mcp-servers/domain/discovery.js';
import { parseScopeText, scopesSchema, type ClientKind } from '#lib/admin/personal-mcp-servers/domain/schemas.js';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import type { PolicyProposal } from './policy-form.svelte';

type Discovered = Extract<EndpointDiscoveryResult, { kind: 'discovered' }>;
export class PersonalServerDiscoveryState {
  endpoint = $state('');
  pending = $state(false);
  attempted = $state(false);
  failed = $state(false);
  manual = $state(false);
  acknowledged = $state(false);
  approved = $state(false);
  result = $state.raw<Discovered | null>(null);
  issuers = $state.raw<readonly string[]>([]);
  selectedIssuer = $state('');
  selectedScopes = $state.raw<readonly string[]>([]);
  customScopes = $state('');
  automaticRegistrationUnavailable = $state(false);
  private resourceMismatch = $state(false);
  private generation = 0;
  private active = false;
  constructor(private readonly api: PersonalServerDiscovery | null, private readonly accessLost: (error: unknown) => void, private readonly automaticClientChanged: (client: AutomaticClient | null) => void = (): void => {}) {}
  reset = (active: boolean): void => {
    this.generation++;
    this.active = active;
    this.endpoint = '';
    this.automaticRegistrationUnavailable = false;
    this.pending = false;
    this.attempted = false;
    this.failed = false;
    this.resourceMismatch = false;
    this.manual = false;
    this.acknowledged = false;
    this.result = null;
    this.automaticClientChanged(null);
    this.issuers = [];
    this.selectedIssuer = '';
    this.selectedScopes = [];
    this.customScopes = '';
    this.approved = false;
  };
  setEndpoint = (endpoint: string): void => {
    if (endpoint === this.endpoint) return;
    this.reset(this.active);
    this.endpoint = endpoint;
  };
  invalidateApproval = (): void => { this.approved = false; this.acknowledged = false; };
  blur = async (): Promise<void> => { if (!this.attempted) await this.discover(); };
  retry = async (): Promise<void> => { await this.discover(); };
  selectIssuer = async (issuer: string): Promise<void> => {
    if (!this.issuers.includes(issuer)) return;
    this.generation++;
    this.pending = false;
    this.selectedIssuer = issuer;
    await this.discover();
  };
  private async discover(): Promise<void> {
    if (!this.active || this.pending) return;
    if (!discoveryEndpointSchema.safeParse(this.endpoint).success) { this.attempted = true; this.failed = true; return; }
    const generation = ++this.generation;
    this.attempted = true;
    this.pending = true;
    this.failed = false;
    this.resourceMismatch = false;
    this.manual = false;
    this.invalidateApproval();
    this.result = null;
    this.selectedScopes = [];
    this.customScopes = '';
    try {
      if (!this.api) throw new Error('Discovery unavailable');
      const result = await this.api.discover({ endpoint_url: this.endpoint, issuer_selection: this.selectedIssuer ? { kind: 'selected', issuer_url: this.selectedIssuer } : { kind: 'automatic' } });
      if (!this.active || generation !== this.generation) return;
      if (result.endpoint_url !== this.endpoint) throw new Error('Endpoint mismatch');
      if (result.kind === 'issuer_selection_required') {
        this.issuers = result.issuer_urls;
        this.selectedIssuer = '';
      } else {
        this.result = result;
        this.automaticRegistrationUnavailable = result.automatic_client.kind === 'unavailable';
        this.automaticClientChanged(result.automatic_client);
        this.selectedIssuer = result.issuer_url;
      }
    } catch (error) {
      if (!this.active || generation !== this.generation) return;
      if (error instanceof AuthenticationRequiredError || error instanceof HttpError && (error.status === 401 || error.status === 403)) {
        this.reset(false);
        this.accessLost(error);
      } else {
        this.failed = true;
        this.resourceMismatch = error instanceof EndpointResourceMismatchError;
      }
    } finally { if (generation === this.generation) this.pending = false; }
  }
  configureManually = (): void => { if (this.failed && !this.pending) { this.manual = true; this.invalidateApproval(); } };
  acknowledge = (value: boolean): void => { this.acknowledged = this.manual && value; };
  toggleScope = (scope: string, checked: boolean): void => {
    if (!this.result?.available_scopes.includes(scope)) return;
    this.selectedScopes = checked ? [...this.selectedScopes.filter((value) => value !== scope), scope] : this.selectedScopes.filter((value) => value !== scope);
    this.invalidateApproval();
  };
  setCustomScopes = (value: string): void => { this.customScopes = value; this.invalidateApproval(); };
  get scopes(): readonly string[] { return scopesSchema.parse([...this.selectedScopes, ...parseScopeText(this.customScopes)]); }
  get scopeError(): string { try { this.scopes; return ''; } catch { return 'Use unique ASCII scope tokens separated by spaces (up to 64 scopes).'; } }
  get scopeSummary(): string { return this.scopeError || this.scopes.join(' ') || 'No explicit scopes'; }
  get failureMessage(): string {
    if (!discoveryEndpointSchema.safeParse(this.endpoint).success) return 'Use an HTTPS endpoint without a query, fragment or credentials, or configure manually.';
    if (this.resourceMismatch) return 'The MCP endpoint must exactly match the server’s resource URL, including its path and trailing slash (/). Check whether a final / is required, then retry discovery.';
    return 'Discovery failed. Scopes unavailable.';
  }
  get issuerOptions(): { value: string; label: string }[] { return [{ value: '', label: 'Choose an issuer' }, ...this.issuers.map((issuer) => ({ value: issuer, label: issuer }))]; }
  get scopeSource(): string { return { resource: 'MCP permissions', authorization_server: 'Provider permissions', unavailable: 'Scopes' }[this.result?.scope_source ?? 'unavailable']; }
  approve = (value: boolean): void => { this.approved = value && !!this.result && !this.scopeError; };
  creationBlocker = (kind: ClientKind): string => {
    if (this.pending) return 'Wait for OAuth discovery to finish.';
    if (this.failed) {
      if (!this.manual) return 'Retry discovery or choose Configure manually.';
      if ((kind === 'dynamic_public' || kind === 'dynamic_confidential') && this.automaticRegistrationUnavailable) return 'Automatic setup is unsupported. Choose an existing client option to continue.';
      return this.acknowledged ? '' : 'Review manual settings and acknowledge saving without discovery.';
    }
    if (!this.result) return this.issuers.length ? 'Choose an OAuth issuer to continue discovery.' : 'Enter an HTTPS MCP endpoint and leave the field to discover OAuth settings.';
    if ((kind === 'dynamic_public' || kind === 'dynamic_confidential') && this.automaticRegistrationUnavailable) return 'Automatic setup is unsupported. You can use a manually configured client instead.';
    if (this.scopeError) return this.scopeError;
    return this.approved ? '' : 'Review permissions and OAuth application settings, then approve the issuer and scopes.';
  };
  canSave = (kind: ClientKind): boolean => {
    if (!this.active || this.pending || (kind === 'dynamic_public' || kind === 'dynamic_confidential') && this.automaticRegistrationUnavailable) return false;
    if (this.result) return this.approved && !this.scopeError && (!(kind === 'dynamic_public' || kind === 'dynamic_confidential') || this.result.automatic_client.kind === kind);
    return this.failed && this.manual && this.acknowledged;
  };
  get proposal(): PolicyProposal | undefined { return this.result && this.approved ? { issuer: this.result.issuer_url, scopes: this.scopes } : undefined; }
}
