import type { PersonalServerAdministration } from './administration';
import { HttpError } from '../infrastructure/transport';
import type { PersonalOAuthSetupAdministration } from './setup-administration';
import { setupRequestSchema, setupStatusSchema, type SetupDiscovery, type SetupRequest, type SetupStatus } from './domain/setup';

export function discoveryFixture(): SetupDiscovery {
  return { issuer_url: 'https://issuer.test', redirect_uri: 'https://umbod.test/oauth/callback', available_scopes: ['records:read', 'records:write'], registration_mode: 'dynamic_public' };
}

export function setupFixture(state: SetupStatus['state'] = { status: 'required' }): SetupStatus {
  return setupStatusSchema.parse({ connector_id: 'personal', revision: 'setup-1', policy_revision: 'r1', redirect_uri: 'https://umbod.test/oauth/callback', state });
}

export class InMemoryPersonalOAuthSetup implements PersonalOAuthSetupAdministration {
  private policies: Pick<PersonalServerAdministration, 'policy'> | null = null;
  bindPolicies(policies: Pick<PersonalServerAdministration, 'policy'>): void { this.policies = policies; }
  readonly calls: { operation: 'status' | 'discovery' | 'validation'; id: string; input?: SetupRequest }[] = [];
  current: SetupStatus = setupFixture();
  discovery: SetupStatus = setupFixture({ status: 'discovered', checked_at: '2026-01-01T00:00:00Z', discovery: discoveryFixture() });
  validation: SetupStatus = setupFixture({ status: 'validated', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'validated', discovery: discoveryFixture(), returned_scopes: [], scope_source: 'not_checked' } });
  async status(id: string): Promise<SetupStatus> {
    this.calls.push({ operation: 'status', id });
    if (this.policies) {
      const policy = await this.policies.policy(id);
      if (policy.revision !== this.current.policy_revision) this.current = { ...setupFixture(), connector_id: id, revision: crypto.randomUUID(), policy_revision: policy.revision };
    }
    return setupStatusSchema.parse(this.current);
  }
  private complete(response: SetupStatus, input: SetupRequest): SetupStatus {
    if (input.expected_revision !== this.current.revision) throw new HttpError(409, '', null);
    this.current = setupStatusSchema.parse({ ...response, revision: crypto.randomUUID(), policy_revision: this.current.policy_revision });
    return this.current;
  }
  async discover(id: string, input: SetupRequest): Promise<SetupStatus> {
    this.calls.push({ operation: 'discovery', id, input: setupRequestSchema.parse(input) });
    return this.complete(this.discovery, input);
  }
  async validate(id: string, input: SetupRequest): Promise<SetupStatus> {
    this.calls.push({ operation: 'validation', id, input: setupRequestSchema.parse(input) });
    return this.complete(this.validation, input);
  }
}
