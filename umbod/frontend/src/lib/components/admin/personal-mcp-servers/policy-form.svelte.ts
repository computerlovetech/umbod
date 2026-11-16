import { parseScopeText, settingsSchema, type ClientKind, type PersonalPolicy, type PersonalSettings } from '$lib/admin/personal-mcp-servers/domain/schemas';

export interface PolicyProposal {
  issuer: string;
  scopes: readonly string[];
}

export class PolicyForm {
  scopes = $state('');
  kind = $state<ClientKind>('dynamic_public');
  issuer = $state('');
  clientId = $state('');
  secret = $state('');
  method = $state<'client_secret_basic' | 'client_secret_post'>('client_secret_basic');
  configured = $state(false);
  constructor(private readonly changed: () => void = () => {}) {}
  set = (field: 'scopes' | 'issuer' | 'clientId' | 'secret', value: string): void => { if (this[field] !== value) this.changed(); this[field] = value; };
  setKind = (value: string): void => {
    if (value !== 'dynamic_public' && value !== 'preconfigured_public' && value !== 'preconfigured_confidential') return;
    this.secret = '';
    this.changed();
    this.kind = value;
  };
  setMethod = (value: string): void => { if (value === 'client_secret_basic' || value === 'client_secret_post') { this.changed(); this.method = value; } };
  clearSecret = (): void => { if (this.secret) this.changed(); this.secret = ''; };
  reset = (policy?: PersonalPolicy): void => {
    this.changed();
    this.secret = '';
    this.scopes = policy?.requested_scopes.join(' ') ?? '';
    this.kind = policy?.client.kind ?? 'dynamic_public';
    this.issuer = policy ? policy.client.kind === 'dynamic_public' ? policy.client.approved_issuers?.[0] ?? '' : policy.client.issuer_url : '';
    this.clientId = policy?.client.kind !== 'dynamic_public' && policy ? policy.client.client_id : '';
    this.method = policy?.client.kind === 'preconfigured_confidential' ? policy.client.token_endpoint_auth_method : 'client_secret_basic';
    this.configured = policy?.client.kind === 'preconfigured_confidential';
  };
  settings = (proposal?: PolicyProposal): PersonalSettings => {
    const issuer = proposal?.issuer ?? this.issuer;
    const client = this.kind === 'dynamic_public' ? { kind: this.kind, ...(issuer ? { approved_issuers: [issuer] } : {}) } : this.kind === 'preconfigured_public'
      ? { kind: this.kind, issuer_url: issuer, client_id: this.clientId }
      : { kind: this.kind, issuer_url: issuer, client_id: this.clientId, token_endpoint_auth_method: this.method, client_secret: this.secret };
    return settingsSchema.parse({ requested_scopes: proposal ? [...proposal.scopes] : parseScopeText(this.scopes), client });
  };
}
