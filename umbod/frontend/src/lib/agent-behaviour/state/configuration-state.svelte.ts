import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { ConfigurationPort } from '../api';
import { configurationFeedback } from '../domain/editing';
import { conflictSchema, identifierSchema, publishSchema, type Configuration, type BehaviourPattern, type DiagnosticPlaybook } from '../domain/schemas';

type ReadonlyPattern = Readonly<Omit<BehaviourPattern, 'categories'>> & { readonly categories: readonly string[] };
type ReadonlySettings = Readonly<Omit<DiagnosticPlaybook, 'pattern_ids'>> & { readonly pattern_ids: readonly string[] };

export class ConfigurationState {
  private value = $state<Configuration>({ revision: 0, patterns: [], playbooks: [] });
  private saved = $state<Configuration | null>(null);
  private pending = $state(false);
  private notice = $state('');
  private collision = $state<Configuration | null>(null);
  private selection = $state<string | null>(null);
  private request: AbortController | null = null;
  private disposed = false;

  constructor(private readonly api: ConfigurationPort, private readonly revoke: () => void, private readonly generateId: () => string = (): string => `pattern-${crypto.randomUUID()}`) {}

  get revision(): number { return this.value.revision; }
  get patterns(): readonly ReadonlyPattern[] { return this.value.patterns; }
  get playbooks(): readonly ReadonlySettings[] { return this.value.playbooks; }
  get settings(): readonly ReadonlySettings[] { return this.value.playbooks; }
  get publishedPatterns(): readonly ReadonlyPattern[] { return this.saved?.patterns ?? []; }
  get publishedPlaybooks(): readonly ReadonlySettings[] { return this.saved?.playbooks ?? []; }
  get selected(): ReadonlyPattern | undefined { return this.patterns.find((pattern): boolean => pattern.id === this.selection); }
  get loaded(): boolean { return this.saved !== null; }
  get busy(): boolean { return this.pending; }
  get message(): string { return this.notice; }
  get conflict(): boolean { return this.collision !== null; }
  get dirty(): boolean { return this.loaded && JSON.stringify(this.value) !== JSON.stringify(this.saved); }
  get reportingMode(): string {
    const enabled = this.playbooks.filter((setting): boolean => setting.enabled && setting.pattern_ids.some((id): boolean => this.patterns.some((pattern): boolean => pattern.id === id && pattern.enabled)));
    if (!enabled.length) return 'Off';
    return enabled.some((setting): boolean => setting.allow_proactive) ? 'Automatic reports allowed' : 'When requested';
  }
  private get editable(): boolean { return !this.disposed && !this.pending && this.loaded; }

  private accept = (configuration: Configuration): void => {
    this.value = structuredClone($state.snapshot(configuration));
    this.saved = structuredClone($state.snapshot(configuration));
    this.collision = null;
    this.selection = null;
  };

  private failure = (error: unknown): void => {
    if (error instanceof AuthenticationRequiredError || (error instanceof HttpError && [401, 403].includes(error.status))) {
      this.revoke();
      return;
    }
    const parsed = error instanceof HttpError && error.status === 409 ? conflictSchema.safeParse(error.body) : null;
    if (parsed?.success) {
      this.collision = parsed.data.detail.current;
      this.notice = 'Another administrator saved changes. Your edits are preserved. Discard changes to use their version.';
      return;
    }
    this.notice = 'Changes could not be saved or loaded. Your edits are preserved. Try again.';
  };

  load = async (): Promise<void> => {
    if (this.disposed || this.pending || this.dirty) return;
    const request = new AbortController();
    this.request = request;
    this.pending = true;
    this.notice = '';
    try {
      const configuration = await this.api.get(request.signal);
      if (!this.disposed && this.request === request) this.accept(configuration);
    } catch (error) {
      if (!this.disposed && this.request === request) this.failure(error);
    } finally {
      if (!this.disposed && this.request === request) this.pending = false;
    }
  };

  save = async (): Promise<void> => {
    if (!this.editable || this.conflict) return;
    const parsed = publishSchema.safeParse({ expected_revision: this.revision, patterns: this.value.patterns, playbooks: this.value.playbooks });
    if (!parsed.success) {
      this.notice = configurationFeedback(parsed.error.issues, this.value);
      return;
    }
    const request = new AbortController();
    this.request = request;
    this.pending = true;
    this.notice = '';
    try {
      const configuration = await this.api.publish(parsed.data, request.signal);
      if (!this.disposed && this.request === request) {
        this.accept(configuration);
        this.notice = 'Changes saved';
      }
    } catch (error) {
      if (!this.disposed && this.request === request) this.failure(error);
    } finally {
      if (!this.disposed && this.request === request) this.pending = false;
    }
  };

  discard = (): void => {
    if (!this.editable) return;
    if (this.collision) this.accept(this.collision);
    else if (this.saved) this.accept(this.saved);
    this.notice = '';
  };

  editPattern = (id: string): void => { if (this.editable) this.selection = id; };
  closeEditor = (): void => { this.selection = null; };

  private firstSettingIsFull = (): boolean => (this.value.playbooks[0]?.pattern_ids.filter((id): boolean => this.patterns.some((pattern): boolean => pattern.id === id)).length ?? 0) >= 20;

  private attachPattern = (id: string): void => {
    this.value.playbooks = this.value.playbooks.map((setting, index): DiagnosticPlaybook => {
      if (index !== 0) return setting;
      const references = setting.pattern_ids.length >= 20 ? setting.pattern_ids.filter((reference): boolean => this.patterns.some((pattern): boolean => pattern.id === reference)) : setting.pattern_ids;
      if (references.length !== setting.pattern_ids.length) this.notice = 'Previously removed patterns were cleared from this reporting setup to make room.';
      return { ...setting, pattern_ids: [...references, id] };
    });
  };

  addPattern = async (): Promise<void> => {
    if (!this.editable) return;
    if (this.patterns.length >= 50) {
      this.notice = 'Up to 50 patterns are supported. Remove a pattern before adding another.';
      return;
    }
    if (this.firstSettingIsFull()) {
      this.notice = 'This reporting setup already includes 20 patterns. Remove a pattern before adding another.';
      return;
    }
    const id = this.generateId();
    if (!identifierSchema.safeParse(id).success || this.patterns.some((pattern): boolean => pattern.id === id) || this.playbooks.some((setting): boolean => setting.pattern_ids.includes(id))) {
      this.notice = 'A unique pattern identifier could not be generated. Try again.';
      return;
    }
    if (!this.value.playbooks.length) {
      const request = new AbortController();
      this.request = request;
      this.pending = true;
      try {
        const defaults = await this.api.defaults(request.signal);
        if (this.disposed || this.request !== request) return;
        this.value.playbooks = defaults.playbooks.map((setting): DiagnosticPlaybook => ({ ...setting, pattern_ids: [], allow_proactive: false }));
      } catch (error) {
        if (!this.disposed && this.request === request) this.failure(error);
        return;
      } finally {
        if (!this.disposed && this.request === request) this.pending = false;
      }
    }
    if (this.disposed) return;
    this.value.patterns.push({ id, name: '', description: '', assessment_prompt: '', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'neutral', enabled: true });
    this.attachPattern(id);
    this.selection = id;
  };

  updatePattern = <K extends Exclude<keyof BehaviourPattern, 'id'>>(id: string, key: K, value: BehaviourPattern[K]): void => {
    if (!this.editable) return;
    this.value.patterns = this.value.patterns.map((pattern): BehaviourPattern => {
      if (pattern.id !== id) return pattern;
      const derivesPrompt = key === 'description' && (!pattern.assessment_prompt || pattern.assessment_prompt === pattern.description);
      return { ...pattern, [key]: value, ...(derivesPrompt ? { assessment_prompt: value as string } : {}) };
    });
  };

  removePattern = (id: string): void => {
    if (!this.editable) return;
    this.value.patterns = this.value.patterns.filter((pattern): boolean => pattern.id !== id);
    if (this.selection === id) this.selection = null;
  };

  updateSettings = <K extends 'collection_instructions' | 'allow_proactive' | 'enabled'>(id: string, key: K, value: DiagnosticPlaybook[K]): void => {
    if (!this.editable) return;
    this.value.playbooks = this.value.playbooks.map((setting): DiagnosticPlaybook => setting.id === id ? { ...setting, [key]: value } : setting);
  };

  dispose = (): void => {
    this.disposed = true;
    this.request?.abort();
    this.pending = false;
    this.value = { revision: 0, patterns: [], playbooks: [] };
    this.saved = null;
    this.selection = null;
    this.collision = null;
    this.notice = '';
  };
}
