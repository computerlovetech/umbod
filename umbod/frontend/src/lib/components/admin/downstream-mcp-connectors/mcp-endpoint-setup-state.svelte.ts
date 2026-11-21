import {
  mcpRegistrySearchSchema,
  mcpEndpointAccessRequestSchema,
  type McpEndpointAccessResult,
  type McpRegistryPage,
  type McpRegistrySearch,
  type McpRegistryServer
} from '#lib/admin/mcp-endpoint-setup.js';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import type { EndpointDiscoveryResult } from '#lib/admin/personal-mcp-servers/domain/discovery.js';

export interface McpEndpointSetupApi {
  search(query: McpRegistrySearch): Promise<McpRegistryPage>;
  checkAccess(endpointUrl: string): Promise<McpEndpointAccessResult>;
}

export type McpSetupMode = 'none' | 'static_bearer' | 'personal';
export type McpSetupDraft = { endpointUrl: string; displayName: string; description: string; oauthMetadata?: EndpointDiscoveryResult };

type WizardStep = 'source' | 'search' | 'review' | 'manual' | 'access';
type AccessCheck = { kind: 'checking' | 'unavailable' | 'unsupported' } | { kind: 'result'; result: McpEndpointAccessResult };
type Endpoint = { readonly url: string; readonly required_headers: readonly string[] };
type Server = Omit<Readonly<McpRegistryServer>, 'endpoints'> & { readonly endpoints: readonly Endpoint[] };
type WizardInputs = {
  api: () => McpEndpointSetupApi;
  personalAvailable: () => boolean;
  accessLost: () => void;
  complete: (mode: McpSetupMode, draft: McpSetupDraft) => void;
};

const PAGE_SIZE = 20;
export const registryServerKey = (server: Server): string => JSON.stringify([server.name, server.version]);
export const registryEndpointKey = (endpoint: Endpoint): string => JSON.stringify([endpoint.url, endpoint.required_headers]);

function isConnectorUrl(value: string): boolean {
  const authority = /^(?:https?):\/\/([^/?#\\]+)(?=[/?#]|$)/i.exec(value)?.[1];
  const url = URL.parse(value);
  if (!authority || !url || /[@\s]/.test(authority) || value.includes('#') || /[\u0000-\u001f\u007f]/.test(value) || url.port === '0') return false;
  if (url.protocol === 'https:') return true;
  if (url.hostname === '[::1]') return true;
  const host = authority.split(':')[0].toLowerCase();
  return host === 'localhost' || (url.hostname === host && /^127\.\d+\.\d+\.\d+$/.test(host));
}

export class McpEndpointSetupState {
  #step = $state<WizardStep>('source');
  #term = $state('');
  #servers = $state.raw<readonly Server[]>([]);
  #cursor = $state('');
  #hasSearched = $state(false);
  #searchStatus = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  #retry = $state<'search' | 'more'>('search');
  #selected = $state.raw<Server | undefined>();
  #registryEndpoint = $state.raw<Endpoint | undefined>();
  #manualUrl = $state('');
  #origin: 'review' | 'manual' = 'manual';
  #access = $state.raw<AccessCheck | undefined>();
  #override = $state(false);
  #selectedMode = $state<McpSetupMode | undefined>();
  #closed = false;
  #generation = 0;

  constructor(private readonly inputs: WizardInputs) {}

  get step(): WizardStep { return this.#step; }
  get progress(): number { return this.#step === 'source' ? 1 : this.#step === 'access' ? 3 : 2; }
  get term(): string { return this.#term; }
  get servers(): readonly Server[] { return this.#servers; }
  get hasSearched(): boolean { return this.#hasSearched; }
  get searchStatus(): 'idle' | 'loading' | 'ready' | 'error' { return this.#searchStatus; }
  get canSearch(): boolean { return mcpRegistrySearchSchema.safeParse({ term: this.#term }).success; }
  get hasMore(): boolean { return Boolean(this.#cursor); }
  get selected(): Server | undefined { return this.#selected; }
  get registryEndpoint(): Endpoint | undefined { return this.#registryEndpoint; }
  get manualUrl(): string { return this.#manualUrl; }
  get canCheckManual(): boolean { return isConnectorUrl(this.#manualUrl.trim()); }
  get endpointUrl(): string { return this.#origin === 'review' ? this.#registryEndpoint?.url ?? '' : this.#manualUrl.trim(); }
  get canProbeEndpoint(): boolean { return mcpEndpointAccessRequestSchema.safeParse({ endpoint_url: this.endpointUrl }).success; }
  get access(): AccessCheck | undefined { return this.#access; }
  get anonymousResult(): McpEndpointAccessResult['anonymous_initialization']['kind'] | undefined {
    return this.#access?.kind === 'result' ? this.#access.result.anonymous_initialization.kind : undefined;
  }
  get oauthConfirmed(): boolean {
    return this.#access?.kind === 'result' && this.#access.result.oauth.kind === 'oauth_discovered';
  }
  get uncertainAccess(): boolean { return this.#access?.kind === 'unavailable' || this.#access?.kind === 'unsupported' || this.anonymousResult === 'inconclusive'; }
  get selectedMode(): McpSetupMode | undefined { return this.#selectedMode; }
  get overrideEnabled(): boolean { return this.#override; }
  private get canChooseAccess(): boolean {
    return this.#step === 'access' && !this.#closed && !!this.#access && this.#access.kind !== 'checking';
  }
  private get canChoosePersonal(): boolean { return this.canProbeEndpoint && this.inputs.personalAvailable(); }
  get unverifiedModes(): readonly McpSetupMode[] {
    if (!this.canChooseAccess) return [];
    const modes: McpSetupMode[] = [];
    if (this.uncertainAccess) modes.push('none');
    const oauthUnconfirmed = this.#access?.kind === 'result' && this.#access.result.oauth.kind === 'oauth_not_confirmed';
    if (this.canChoosePersonal && !this.oauthConfirmed && (this.uncertainAccess || oauthUnconfirmed)) modes.push('personal');
    return modes;
  }
  get standardModes(): readonly McpSetupMode[] {
    if (!this.canChooseAccess) return [];
    const modes: McpSetupMode[] = [];
    if (this.anonymousResult === 'anonymous_initialization_succeeded') modes.push('none');
    if (this.canChoosePersonal && this.oauthConfirmed) modes.push('personal');
    modes.push('static_bearer');
    return modes;
  }
  get modes(): readonly McpSetupMode[] {
    const available = [...this.standardModes, ...(this.#override ? this.unverifiedModes : [])];
    return (['none', 'personal', 'static_bearer'] as const).filter((mode) => available.includes(mode));
  }

  openSearch = (): void => {
    if (this.#closed || this.#step !== 'source') return;
    this.#step = 'search';
  };

  openManual = (): void => {
    if (this.#closed || this.#step !== 'source') return;
    this.#step = 'manual';
  };

  back = (): void => {
    if (this.#closed) return;
    this.leavePending();
    if (this.#step === 'access') this.#step = this.#origin;
    else if (this.#step === 'review') this.#step = 'search';
    else this.#step = 'source';
  };

  changeTerm = (value: string): void => {
    if (this.#closed || this.#step !== 'search' || value === this.#term) return;
    this.leavePending();
    this.#term = value;
    this.#selected = undefined;
    this.#servers = [];
    this.#cursor = '';
    this.#searchStatus = 'idle';
  };

  search = (): Promise<void> => this.fetchPage('search');
  loadMore = (): Promise<void> => this.fetchPage('more');
  retrySearch = (): Promise<void> => this.fetchPage(this.#retry);

  selectServer = (server: Server): void => {
    if (this.#closed || this.#step !== 'search' || !this.#servers.includes(server) || this.#selected === server) return;
    this.#selected = server;
    this.#registryEndpoint = server.endpoints.length === 1 ? server.endpoints[0] : undefined;
  };

  review = (): void => {
    if (this.#closed || this.#step !== 'search' || !this.#selected) return;
    this.leavePending();
    this.#step = 'review';
  };

  selectEndpoint = (endpoint: Endpoint): void => {
    if (!this.#closed && this.#step === 'review' && this.#selected?.endpoints.includes(endpoint)) this.#registryEndpoint = endpoint;
  };

  changeManualUrl = (url: string): void => {
    if (!this.#closed && this.#step === 'manual') this.#manualUrl = url;
  };

  checkAccess = async (): Promise<void> => {
    if (this.#closed || !this.prepareCheck()) return;
    this.#step = 'access';
    this.#override = false;
    this.#selectedMode = undefined;
    if (!this.canProbeEndpoint) {
      this.#access = { kind: 'unsupported' };
      return;
    }
    this.#access = { kind: 'checking' };
    const generation = ++this.#generation;
    try {
      const result = await this.inputs.api().checkAccess(this.endpointUrl);
      if (this.isCurrent(generation)) this.#access = { kind: 'result', result };
    } catch (error) {
      if (this.isCurrent(generation) && !this.handleAccessLoss(error)) this.#access = { kind: 'unavailable' };
    }
  };

  setOverride = (open: boolean): void => {
    if (!this.canChooseAccess) return;
    this.#override = open && this.unverifiedModes.length > 0;
    if (!this.#override && this.#selectedMode && !this.standardModes.includes(this.#selectedMode)) this.#selectedMode = undefined;
  };

  selectMode = (mode: McpSetupMode): void => {
    if (this.modes.includes(mode)) this.#selectedMode = mode;
  };

  configure = (): void => {
    if (this.#selectedMode) this.finish(this.#selectedMode);
  };

  finish = (mode: McpSetupMode): void => {
    if (!this.modes.includes(mode)) return;
    const server = this.#origin === 'review' ? this.#selected : undefined;
    const draft: McpSetupDraft = { endpointUrl: this.endpointUrl, displayName: server?.title ?? '', description: server?.description ?? '' };
    const oauth = this.#access?.kind === 'result' ? this.#access.result.oauth : undefined;
    if (mode === 'personal' && oauth?.kind === 'oauth_discovered' && oauth.metadata.endpoint_url === draft.endpointUrl) {
      draft.oauthMetadata = oauth.metadata;
    }
    this.inputs.complete(mode, draft);
  };

  dispose = (): void => {
    this.#closed = true;
    this.leavePending();
  };

  private prepareCheck(): boolean {
    if (this.#step === 'review' && this.#registryEndpoint) { this.#origin = 'review'; return true; }
    if (this.#step === 'manual' && this.canCheckManual) { this.#origin = 'manual'; return true; }
    return this.#step === 'access' && this.uncertainAccess;
  }

  private async fetchPage(kind: 'search' | 'more'): Promise<void> {
    if (this.#closed || this.#step !== 'search' || this.#searchStatus === 'loading' || !this.canSearch || (kind === 'more' && !this.#cursor)) return;
    const cursor = kind === 'more' ? this.#cursor : undefined;
    const generation = ++this.#generation;
    this.#retry = kind;
    if (kind === 'search') { this.#servers = []; this.#cursor = ''; this.#selected = undefined; }
    this.#hasSearched = true;
    this.#searchStatus = 'loading';
    try {
      const page = await this.inputs.api().search({ term: this.#term.trim(), limit: PAGE_SIZE, cursor });
      if (!this.isCurrent(generation)) return;
      const byKey = new Map(this.#servers.map((server) => [registryServerKey(server), server]));
      for (const server of page.servers) {
        const key = registryServerKey(server);
        if (!byKey.has(key)) byKey.set(key, server);
      }
      this.#servers = [...byKey.values()];
      this.#cursor = page.next_cursor === cursor ? '' : page.next_cursor;
      this.#searchStatus = 'ready';
    } catch (error) {
      if (this.isCurrent(generation) && !this.handleAccessLoss(error)) this.#searchStatus = 'error';
    }
  }

  private leavePending(): void {
    ++this.#generation;
    if (this.#searchStatus === 'loading') this.#searchStatus = this.#servers.length ? 'ready' : 'idle';
    this.#access = undefined;
    this.#override = false;
  }

  private isCurrent(generation: number): boolean { return !this.#closed && generation === this.#generation; }

  private handleAccessLoss(error: unknown): boolean {
    if (!(error instanceof AuthenticationRequiredError || (error instanceof HttpError && (error.status === 401 || error.status === 403)))) return false;
    this.dispose();
    this.inputs.accessLost();
    return true;
  }
}
