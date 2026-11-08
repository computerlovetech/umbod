import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { PersonalAccessTokensApi } from '$lib/personal-access-tokens/api';
import type { TokenMetadata } from '$lib/personal-access-tokens/domain/schemas';
import type { ClipboardWriter } from '$lib/admin/clipboard';
import type { SelectOption } from '$lib/components/admin/shared/select-state.svelte';
import type { TelemetrySetupSource } from '$lib/telemetry-setup/api';
import type { TelemetrySetup } from '$lib/telemetry-setup/domain/schemas';
import { telemetryConfiguration, type TelemetryAgent } from './telemetry-formatters';

export class TelemetrySetupState {
  private currentAgent = $state<TelemetryAgent>('codex');
  private creationDialogOpen = $state(false);
  private setup = $state.raw<TelemetrySetup | undefined>();
  private name = $state('');
  private expiration = $state(30);
  readonly expirationOptions: readonly number[] = Object.freeze([7, 30, 60, 90]);
  private access = $state<'loading' | 'ready' | 'signin' | 'forbidden' | 'error'>('loading');
  private rows = $state.raw<readonly TokenMetadata[]>([]);
  private message = $state('');
  private operation = $state<'idle' | 'create' | 'revoke'>('idle');
  private output = $state('');
  private outputTokenId = '';
  private copying = $state(false);
  private copied = $state(false);
  private disposed = false;
  private loading = false;
  private secretRevision = 0;

  constructor(private readonly api: PersonalAccessTokensApi, private readonly source: TelemetrySetupSource, private readonly clipboard: ClipboardWriter, private readonly now: () => number = Date.now) {}

  get createDialogOpen(): boolean { return this.creationDialogOpen; }
  get agent(): TelemetryAgent { return this.currentAgent; }
  get agentOptions(): SelectOption[] {
    return [{ value: 'codex', label: 'Codex' }, { value: 'claude-code', label: 'Claude Code' }];
  }
  get expirationSelectOptions(): SelectOption[] {
    return this.expirationOptions.map((days: number): SelectOption => ({ value: String(days), label: `${days} days` }));
  }
  get tokenName(): string { return this.name; }
  get expirationDays(): number { return this.expiration; }
  get canGenerate(): boolean { return this.access === 'ready' && this.setup?.status === 'available'; }
  get availabilityMessage(): string {
    if (!this.setup) return 'Could not load telemetry setup. Contact your operator if the problem persists.';
    if (this.setup.status === 'available') return '';
    return this.setup.reason === 'disabled'
      ? 'Telemetry collection is disabled on this instance. Contact your operator to enable it.'
      : 'The telemetry collector endpoint is not configured on this instance. Contact your operator to configure it.';
  }
  get status(): string { return this.access; }
  get tokens(): readonly TokenMetadata[] { return this.rows; }
  get error(): string { return this.message; }
  get pending(): boolean { return this.operation !== 'idle'; }
  get creating(): boolean { return this.operation === 'create'; }
  get configuration(): string { return this.output; }
  get copyPending(): boolean { return this.copying; }
  get copySucceeded(): boolean { return this.copied; }

  openCreate = (): void => {
    if (this.disposed || this.pending || !this.canGenerate) return;
    this.dismiss();
    this.name = '';
    this.expiration = 30;
    this.currentAgent = 'codex';
    this.message = '';
    this.creationDialogOpen = true;
  };

  closeCreate = (): void => {
    if (this.creating) return;
    this.creationDialogOpen = false;
    this.dismiss();
  };

  setAgent = (value: string): void => {
    if (value !== 'codex' && value !== 'claude-code') return;
    this.currentAgent = value;
    this.dismiss();
  };
  setTokenName = (value: string): void => { this.name = value; };
  setExpirationDays = (value: number): void => {
    if (this.expirationOptions.includes(value)) this.expiration = value;
    else this.message = 'Choose a supported expiration duration.';
  };

  load = async (): Promise<void> => {
    if (this.disposed || this.loading || this.pending) return;
    this.loading = true;
    this.access = 'loading';
    this.message = '';
    try {
      const [tokens, setup] = await Promise.allSettled([this.api.tokens.list(), this.source.get()]);
      if (this.disposed) return;
      const previousEndpoint = this.setup?.status === 'available' ? this.setup.logs_endpoint : undefined;
      this.setup = setup.status === 'fulfilled' ? setup.value : undefined;
      if (this.setup?.status !== 'available' || this.setup.logs_endpoint !== previousEndpoint) this.dismiss();
      if (tokens.status === 'rejected') throw tokens.reason;
      this.rows = tokens.value;
      if (this.outputTokenId && !this.rows.some((row: TokenMetadata): boolean => row.token_id === this.outputTokenId && row.status === 'active' && Date.parse(row.expires_at) > this.now())) this.dismiss();
      this.access = 'ready';
      if (setup.status === 'rejected' && (setup.reason instanceof AuthenticationRequiredError || (setup.reason instanceof HttpError && [401, 403].includes(setup.reason.status)))) {
        this.failure(setup.reason, 'Could not load telemetry setup. Contact your operator if the problem persists.');
      }
    } catch (error: unknown) {
      if (!this.disposed) this.failure(error, 'Could not load personal access tokens. Contact your operator if the problem persists.');
    } finally {
      this.loading = false;
    }
  };

  create = async (): Promise<void> => {
    if (this.disposed || this.pending || !this.canGenerate || this.setup?.status !== 'available') return;
    this.message = '';
    if (!this.name.trim() || this.name.trim().length > 256 || !this.expirationOptions.includes(this.expiration)) {
      this.message = 'Enter a token name of 1–256 characters and choose a supported expiration duration.';
      return;
    }
    const endpoint = this.setup.logs_endpoint;
    const expiresAt = new Date(this.now() + this.expiration * 86_400_000).toISOString();
    this.dismiss();
    const revision = this.secretRevision;
    const agent = this.currentAgent;
    this.operation = 'create';
    try {
      const issued = await this.api.tokens.create({ name: this.name.trim(), expires_at: expiresAt, permissions: { telemetry: 'write' } });
      if (this.disposed) return;
      this.rows = [issued.metadata, ...this.rows.filter((row: TokenMetadata): boolean => row.token_id !== issued.metadata.token_id)];
      if (revision === this.secretRevision) {
        this.output = telemetryConfiguration(agent, endpoint, issued.token);
        this.outputTokenId = issued.metadata.token_id;
      }
    } catch (error: unknown) {
      if (!this.disposed) await this.reconcileFailure(error, 'Token creation was not confirmed. Check the token list before creating another; a token may have been created.');
    } finally {
      this.operation = 'idle';
    }
  };

  revoke = async (tokenId: string): Promise<void> => {
    if (this.disposed || this.pending || this.access !== 'ready' || !this.rows.some((row: TokenMetadata): boolean => row.token_id === tokenId)) return;
    this.operation = 'revoke';
    this.message = '';
    try {
      await this.api.tokens.revoke(tokenId);
      if (this.disposed) return;
      this.rows = this.rows.filter((row: TokenMetadata): boolean => row.token_id !== tokenId);
      if (this.outputTokenId === tokenId) this.dismiss();
    } catch (error: unknown) {
      if (!this.disposed) await this.reconcileFailure(error, 'Deletion was not confirmed. Check the token list before trying again.');
    } finally {
      this.operation = 'idle';
    }
  };

  copy = async (): Promise<void> => {
    if (this.disposed || !this.output || this.copying) return;
    const revision = this.secretRevision;
    this.copying = true;
    this.copied = false;
    try {
      await this.clipboard.writeText(this.output);
      if (!this.disposed && revision === this.secretRevision) this.copied = true;
    } catch {
      if (!this.disposed && revision === this.secretRevision) this.message = 'Could not copy configuration. Select and copy it manually.';
    } finally {
      this.copying = false;
    }
  };

  dismiss = (): void => {
    this.secretRevision += 1;
    this.output = '';
    this.outputTokenId = '';
    this.copied = false;
  };

  dispose = (): void => {
    this.disposed = true;
    this.creationDialogOpen = false;
    this.dismiss();
    this.rows = [];
  };

  private async reconcileFailure(error: unknown, message: string): Promise<void> {
    this.creationDialogOpen = false;
    this.dismiss();
    this.failure(error, message);
    if (this.access !== 'error') return;
    try {
      const rows = await this.api.tokens.list();
      if (this.disposed) return;
      this.rows = rows;
      this.access = 'ready';
    } catch (readError: unknown) {
      if (!this.disposed) this.failure(readError, message);
    }
  }

  private failure(error: unknown, message: string): void {
    this.message = message;
    if (error instanceof AuthenticationRequiredError || (error instanceof HttpError && error.status === 401)) {
      this.access = 'signin';
      this.creationDialogOpen = false;
      this.dismiss();
      this.rows = [];
    } else if (error instanceof HttpError && error.status === 403) {
      this.access = 'forbidden';
      this.creationDialogOpen = false;
      this.dismiss();
      this.rows = [];
    } else {
      this.access = 'error';
    }
  }
}
