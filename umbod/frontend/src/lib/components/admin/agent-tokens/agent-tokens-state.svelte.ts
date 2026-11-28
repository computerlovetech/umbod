import type { AgentTokenMetadata, IssuedAgentToken } from '#lib/admin/agent-tokens/domain/schemas.js';
import type { AgentTokens } from '#lib/admin/agent-tokens/port.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { CatalogueGroup } from '#lib/admin/groups/domain/schemas.js';
import type { SelectOption } from '#lib/components/admin/shared/select-state.svelte.js';
import { defaultTokenExpiration, isTokenExpirationChoice, timestampForTokenExpiration, tokenExpirationOptions, type TokenExpirationChoice } from '#lib/components/shared/token-expiration.js';

type TokenDialog =
  | { kind: 'closed' | 'create' }
  | { kind: 'rotate' | 'revoke'; agent: AgentTokenMetadata }
  | { kind: 'issued'; token: string; title: string };

export class AgentTokensState {
  dialog = $state.raw<TokenDialog>({ kind: 'closed' });
  agents = $state.raw<readonly AgentTokenMetadata[]>([]);
  pending = $state(false);
  error = $state('');
  selectedGroup = $state('');
  expiration = $state<TokenExpirationChoice>(defaultTokenExpiration);
  readonly expirationOptions = tokenExpirationOptions;
  readonly groupOptions: SelectOption[];
  private disposed = false;
  private observedTime = $state(0);

  constructor(
    private readonly api: AgentTokens,
    agents: readonly AgentTokenMetadata[],
    readonly groups: readonly CatalogueGroup[],
    private readonly now: () => number = Date.now
  ) {
    this.agents = agents;
    this.observedTime = this.now();
    this.groupOptions = [
      { value: '', label: 'Select a group', disabled: true },
      ...groups.map((group): SelectOption => ({
        value: group.group_id,
        label: group.label === group.group_id ? group.label : `${group.label} (${group.group_id})`
      }))
    ];
  }

  observeExpiry = (): (() => void) => {
    const timer = setInterval(() => { this.observedTime = this.now(); }, 15_000);
    return () => clearInterval(timer);
  };

  statusOf = (agent: AgentTokenMetadata): AgentTokenMetadata['status'] =>
    agent.status === 'active' && agent.expires_at !== null && Date.parse(agent.expires_at) <= this.observedTime ? 'expired' : agent.status;

  selectGroup = (groupId: string): void => { this.selectedGroup = groupId; };

  selectExpiration = (value: string): void => {
    if (isTokenExpirationChoice(value)) this.expiration = value;
  };

  openCreate = (): void => {
    if (this.groups.length) this.open({ kind: 'create' });
  };

  openRotate = (agent: AgentTokenMetadata): void => this.open({ kind: 'rotate', agent });

  openRevoke = (agent: AgentTokenMetadata): void => this.open({ kind: 'revoke', agent });

  close = (): void => {
    if (this.pending) return;
    this.dialog = { kind: 'closed' };
    this.error = '';
  };

  dispose = (): void => {
    this.disposed = true;
    this.dialog = { kind: 'closed' };
  };

  groupLabel = (groupId: string): string => this.groups.find((group) => group.group_id === groupId)?.label ?? groupId;

  save = async (fields: FormData): Promise<void> => {
    const dialog = this.dialog;
    if (dialog.kind !== 'create' && dialog.kind !== 'rotate') return;
    const expires_at = timestampForTokenExpiration(this.expiration, this.now());
    if (dialog.kind === 'rotate') {
      await this.run(async (): Promise<void> => {
        this.showIssued(await this.api.rotate(dialog.agent.agent_id, { expires_at }), 'Agent token rotated');
      });
      return;
    }
    const display_name = String(fields.get('display_name') ?? '').trim();
    const group_id = this.selectedGroup;
    if (!display_name || !this.groups.some((group) => group.group_id === group_id)) {
      this.error = 'Enter an agent name and select a group.';
      return;
    }
    await this.run(async (): Promise<void> => {
      this.showIssued(await this.api.create({ display_name, group_id, expires_at }), 'Agent token created');
    });
  };

  revoke = async (): Promise<void> => {
    const dialog = this.dialog;
    if (dialog.kind !== 'revoke') return;
    await this.run(async (): Promise<void> => {
      await this.api.revoke(dialog.agent.agent_id);
      if (this.disposed) return;
      this.agents = this.agents.map((agent): AgentTokenMetadata =>
        agent.agent_id === dialog.agent.agent_id ? { ...agent, status: 'revoked' } : agent
      );
      this.dialog = { kind: 'closed' };
    });
  };

  private open(dialog: TokenDialog): void {
    if (this.disposed || this.pending || this.dialog.kind !== 'closed') return;
    this.error = '';
    this.selectedGroup = '';
    this.expiration = defaultTokenExpiration;
    this.dialog = dialog;
  }

  private showIssued(issued: IssuedAgentToken, title: string): void {
    if (this.disposed) return;
    this.agents = [issued.metadata, ...this.agents.filter((agent) => agent.agent_id !== issued.metadata.agent_id)];
    this.dialog = { kind: 'issued', token: issued.token, title };
  }

  private async run(operation: () => Promise<void>): Promise<void> {
    if (this.disposed || this.pending) return;
    this.pending = true;
    this.error = '';
    try {
      await operation();
    } catch (failure) {
      if (this.disposed) return;
      const missingGroup = this.dialog.kind === 'create' && failure instanceof HttpError && failure.status === 404;
      this.dialog = { kind: 'closed' };
      try {
        const agents = await this.api.list();
        if (!this.disposed) {
          this.agents = agents;
          this.error = missingGroup
            ? 'The selected group no longer exists. Reload the page to update the group list.'
            : 'The token change could not be confirmed. Check the list before trying again.';
        }
      } catch {
        if (!this.disposed) this.error = 'The token change could not be confirmed. Reload the page before trying again.';
      }
    } finally {
      this.pending = false;
    }
  }
}
