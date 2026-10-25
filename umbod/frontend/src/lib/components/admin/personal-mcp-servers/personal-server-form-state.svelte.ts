import { downstreamMcpProxySlugSchema, type DownstreamMcpConnector } from '$lib/admin/downstream-mcp-connectors';
import { suggestedConnectorId, suggestedToolNamePrefix } from '../shared/connector-name-suggestions';
import type { PersonalServerAdministration } from '$lib/admin/personal-mcp-servers/administration';
import { createPersonalServerSchema, type PersonalServerCreate, type PersonalSettings, type PersonalPolicy } from '$lib/admin/personal-mcp-servers/domain/schemas';
import { AuthenticationRequiredError, HttpError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { PolicyForm } from './policy-form.svelte';
import type { InstanceConfigurationRoute } from '$lib/admin/instance-configuration-api';
import { personalServerAvailability, type PersonalServerAvailability } from '$lib/admin/personal-mcp-servers/domain/availability';

export type Confirmation = 'policy';
export class PersonalServerFormState {
  selected = $state.raw<DownstreamMcpConnector | null>(null);
  policy = $state.raw<PersonalPolicy | null>(null);
  loading = $state(false);
  busy = $state(false);
  blocked = $state(false);
  authenticationLost = $state(false);
  unavailable = $state(false);
  availability = $state.raw<PersonalServerAvailability>({ registration: 'unknown', authorization: 'unknown' });
  message = $state('');
  creating = $state(false);
  confirmation = $state<Confirmation | null>(null);
  metadata = $state({ name: '', prefix: '', description: '', path: '', endpoint: '' });
  readonly form = new PolicyForm();
  private prefixEdited = false;
  private pathEdited = false;
  private epoch = 0;
  private disposed = false;
  constructor(private readonly api: PersonalServerAdministration, private readonly configuration: InstanceConfigurationRoute, private readonly targetId: string | null, private readonly completed: (id: string) => Promise<void> = async () => {}, private readonly accessLost: () => void = () => {}, private readonly lockChanged: (locked: boolean) => void = () => {}) {}
  get canRegister(): boolean { return !this.targetId && !this.disposed && !this.locked && this.availability.registration === 'enabled'; }
  private async readAvailability(token: number): Promise<PersonalServerAvailability> {
    try { return personalServerAvailability(await this.configuration.get()); }
    catch (error) {
      if (this.current(token) && (error instanceof AuthenticationRequiredError || error instanceof HttpError && (error.status === 401 || error.status === 403))) this.fail(error, false);
      return { registration: 'unknown', authorization: 'unknown' };
    }
  }
  get locked(): boolean { return this.busy || this.loading || this.blocked || this.authenticationLost || this.unavailable; }
  private current(token: number): boolean { return !this.disposed && token === this.epoch; }
  private clear(): void {
    this.availability = { registration: 'unknown', authorization: 'unknown' };
    this.selected = null;
    this.policy = null;
    this.creating = false;
    this.confirmation = null;
    this.resetMetadata();
    this.form.reset();
  }
  private fail(error: unknown, mutation: boolean): void {
    this.form.clearSecret();
    if (error instanceof AuthenticationRequiredError || error instanceof HttpError && (error.status === 401 || error.status === 403)) {
      this.epoch++;
      this.clear();
      this.authenticationLost = true;
      this.accessLost();
      this.message = 'Administration access was lost. Sign in again before reloading this page.';
      return;
    }
    const code = error instanceof HttpError && typeof error.body === 'object' && error.body !== null && 'detail' in error.body && typeof error.body.detail === 'object' && error.body.detail !== null && 'code' in error.body.detail ? error.body.detail.code : null;
    if (error instanceof HttpError && error.status === 404) {
      this.unavailable = code === 'personal_connections_unavailable' || this.creating;
      this.blocked = true;
      if (code === 'personal_connections_unavailable') {
        this.availability = { registration: 'disabled', authorization: 'unknown' };
        this.message = 'Personal connections are unavailable in this deployment. An operator must enable personal connections and configure a stable identity namespace. Startup settings cannot be edited here. Reload after the deployment is configured.';
      } else {
        this.availability = { registration: 'unknown', authorization: 'unknown' };
        this.message = 'This server or its personal OAuth policy is unavailable. Reload to reconcile the inventory and check registration availability.';
      }
    } else if (code === 'personal_oauth_configuration_conflict') {
      this.blocked = true;
      this.message = 'OAuth settings changed elsewhere. Reload authoritative settings before saving again. Your change was not replayed.';
    } else if (mutation && !(error instanceof HttpError && error.status >= 400 && error.status < 500) && !(error instanceof SchemaValidationError && error.direction === 'outbound')) {
      this.blocked = true;
      this.message = 'The outcome is unknown. Reload authoritative server state before any further changes. Nothing will be replayed.';
    } else {
      this.message = mutation ? 'The change was rejected. Check the values and permissions before trying again; confidential saves require a fresh secret.' : 'Personal MCP servers could not be loaded. Reload to try again.';
    }
  }
  reload = async (): Promise<void> => {
    if (this.busy || this.disposed || this.authenticationLost || !this.targetId && this.blocked) return;
    const token = ++this.epoch;
    this.loading = true;
    this.lockChanged(true);
    this.form.reset();
    this.confirmation = null;
    this.selected = null;
    this.policy = null;
    try {
      if (this.targetId) {
        const selected = await this.api.get(this.targetId);
        const policy = await this.api.policy(this.targetId);
        if (!this.current(token)) return;
        if (selected.connector_id !== this.targetId || policy.connector_id !== this.targetId) throw new SchemaValidationError('inbound', []);
        this.selected = selected;
        this.policy = policy;
        this.form.reset(policy);
      } else {
        const availability = await this.readAvailability(token);
        if (!this.current(token)) return;
        this.availability = availability;
      }
      this.blocked = false;
      this.unavailable = false;
      this.message = '';
    } catch (error) { if (this.current(token)) { this.blocked = true; this.fail(error, false); } }
    finally { if (this.current(token) || this.authenticationLost) { this.loading = false; this.lockChanged(this.locked); } }
  };
  openCreate = (): void => {
    if (!this.canRegister) return;
    this.form.reset();
    this.resetMetadata();
    this.creating = true;
    this.message = '';
  };
  close = (): void => {
    if (this.busy) return;
    this.creating = false;
    this.confirmation = null;
    this.form.reset(this.policy ?? undefined);
  };
  handleNativeInvalid = (): void => {
    this.form.clearSecret();
    this.message = 'Complete all required fields before continuing. The client secret was cleared; enter a fresh secret before submitting again.';
  };
  private resetMetadata(): void {
    this.metadata = { name: '', prefix: '', description: '', path: '', endpoint: '' };
    this.prefixEdited = false;
    this.pathEdited = false;
  }
  setMetadata = (field: keyof PersonalServerFormState['metadata'], value: string): void => {
    if (this.locked || this.disposed) return;
    this.metadata[field] = value;
    if (field === 'prefix') this.prefixEdited = true;
    if (field === 'path') this.pathEdited = true;
    if (field !== 'name') return;
    if (!this.prefixEdited) this.metadata.prefix = value.trim() ? suggestedToolNamePrefix(value) : '';
    if (!this.pathEdited) {
      const slug = suggestedConnectorId(value).slice(0, 63);
      this.metadata.path = !slug || downstreamMcpProxySlugSchema.safeParse(slug).success ? slug : `${slug}-server`;
    }
  };
  requestConfirmation = (action: Confirmation): void => {
    if (this.locked || !this.selected || !this.policy) return;
    this.confirmation = action;
  };
  create = async (): Promise<void> => {
    if (!this.canRegister || !this.creating) { this.form.clearSecret(); return; }
    let input: PersonalServerCreate;
    try {
      input = createPersonalServerSchema.parse({ metadata: { display_name: this.metadata.name, tool_name_prefix: this.metadata.prefix, capability_description: this.metadata.description, public_path: `/mcp/proxies/${this.metadata.path}` }, configuration: { endpoint_url: this.metadata.endpoint, oauth_configuration: this.form.settings() } });
    } catch {
      this.form.clearSecret();
      this.message = 'Check all server and OAuth settings. Scopes must be unique ASCII tokens separated by ordinary spaces; confidential writes require a fresh secret.';
      return;
    }
    this.form.clearSecret();
    await this.mutate(async () => {
      const server = await this.api.create(input);
      return server.connector_id;
    });
  };
  confirm = async (): Promise<void> => {
    if (this.locked || !this.confirmation || !this.selected || !this.policy) return;
    const id = this.selected.connector_id;
    const revision = this.policy.revision;
    this.confirmation = null;
    let settings: PersonalSettings;
    try { settings = this.form.settings(); }
    catch {
      this.form.clearSecret();
      this.message = 'Check OAuth settings. Scopes must be unique ASCII tokens separated by ordinary spaces; confidential writes require a fresh secret.';
      return;
    }
    this.form.clearSecret();
    await this.mutate(async () => {
      await this.api.replacePolicy(id, { expected_revision: revision, settings });
      return id;
    });
  };
  private async mutate(operation: () => Promise<string | null>): Promise<void> {
    const token = this.epoch;
    this.busy = true;
    this.lockChanged(true);
    this.message = '';
    let completed = false;
    let selectedId: string | null = null;
    try {
      selectedId = await operation();
      completed = true;
    } catch (error) { if (this.current(token)) this.fail(error, true); }
    finally { if (!this.disposed) { this.busy = completed && !this.targetId; this.lockChanged(this.locked); } }
    if (completed && this.current(token)) {
      this.creating = false;
      this.form.reset();
      if (selectedId && !this.targetId) {
        try { await this.completed(selectedId); }
        catch { if (this.current(token)) { this.blocked = true; this.message = 'Registration completed, but inventory could not be reconciled. Reload before making further changes.'; } }
      } else await this.reload();
      if (!this.selected && this.blocked) this.message = 'The change completed, but state could not be reconciled. Reload before making further changes.';
    }
    if (this.current(token)) {
      this.busy = false;
      this.lockChanged(this.locked);
    }
  }
  dispose = (): void => {
    this.disposed = true;
    this.epoch++;
    this.clear();
    this.lockChanged(false);
  };
}
