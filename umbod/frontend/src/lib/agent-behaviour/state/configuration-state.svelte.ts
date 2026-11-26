import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import type { ConfigurationPort } from '../api';
import { configurationFeedback, newPatternFeedback } from '../domain/editing';
import { conflictSchema, identifierSchema, patternCategoryLimit, patternSchema, publishSchema, type Configuration, type BehaviourPattern, type DiagnosticPlaybook } from '../domain/schemas';

type ReadonlyPattern = Readonly<Omit<BehaviourPattern, 'categories'>> & { readonly categories: readonly string[] };
type ReadonlySettings = Readonly<Omit<DiagnosticPlaybook, 'pattern_ids'>> & { readonly pattern_ids: readonly string[] };
type PatternSelection = { baseline: string; pendingCategory: string } & ({ kind: 'existing'; id: string } | { kind: 'new'; pattern: BehaviourPattern; message: string });
type CollectionStatus = 'unavailable' | 'unconfigured' | 'off' | 'configured';
function hasUsablePlaybook(settings: readonly ReadonlySettings[], patterns: readonly ReadonlyPattern[]): boolean {
  const enabledPatternIds = new Set(patterns.filter((pattern): boolean => pattern.enabled).map((pattern): string => pattern.id));
  return settings.some((setting): boolean => setting.enabled && setting.pattern_ids.some((id): boolean => enabledPatternIds.has(id)));
}

export class ConfigurationState {
  private value = $state<Configuration>({ revision: 0, reporting_enabled: false, patterns: [], playbooks: [] });
  private saved = $state<Configuration | null>(null);
  private pending = $state(false);
  private notice = $state('');
  private collision = $state<Configuration | null>(null);
  private selection = $state<PatternSelection | null>(null);
  private request: AbortController | null = null;
  private disposed = $state(false);

  constructor(private readonly api: ConfigurationPort, private readonly revoke?: () => void, private readonly generateId: () => string = (): string => `pattern-${crypto.randomUUID()}`) {}

  get allowed(): boolean { return !this.disposed; }
  get revision(): number { return this.value.revision; }
  get patterns(): readonly ReadonlyPattern[] { return this.value.patterns; }
  get playbooks(): readonly ReadonlySettings[] { return this.value.playbooks; }
  get settings(): readonly ReadonlySettings[] { return this.value.playbooks; }
  get publishedPatterns(): readonly ReadonlyPattern[] { return this.saved?.patterns ?? []; }
  get publishedPlaybooks(): readonly ReadonlySettings[] { return this.saved?.playbooks ?? []; }
  get enabledPatternCount(): number { return this.patterns.filter((pattern): boolean => pattern.enabled).length; }
  get creatingPattern(): boolean { return this.selection?.kind === 'new'; }
  get editorMessage(): string { return this.selection?.kind === 'new' ? this.selection.message : ''; }
  get selected(): ReadonlyPattern | undefined {
    const selection = this.selection;
    if (selection?.kind === 'new') return selection.pattern;
    return this.patterns.find((pattern): boolean => pattern.id === selection?.id);
  }
  get pendingCategory(): string { return this.selection?.pendingCategory ?? ''; }
  get editorDirty(): boolean {
    const selected = this.selected;
    return !!selected && !!this.selection && (this.pendingCategory.trim().length > 0 || JSON.stringify(selected) !== this.selection.baseline);
  }
  get loaded(): boolean { return this.saved !== null; }
  get busy(): boolean { return this.pending; }
  get message(): string { return this.notice; }
  get conflict(): boolean { return this.collision !== null; }
  get dirty(): boolean { return this.loaded && JSON.stringify(this.value) !== JSON.stringify(this.saved); }
  get collectionStatus(): CollectionStatus {
    if (!this.saved) return 'unavailable';
    if (!this.publishedPlaybooks.length) return 'unconfigured';
    if (!this.saved.reporting_enabled) return 'off';
    return hasUsablePlaybook(this.publishedPlaybooks, this.publishedPatterns) ? 'configured' : 'unconfigured';
  }
  get reportingEnabled(): boolean { return this.value.reporting_enabled; }
  get reportingNeedsUsablePlaybook(): boolean {
    return this.reportingEnabled && !hasUsablePlaybook(this.playbooks, this.patterns);
  }
  get savedReportingEnabled(): boolean { return (this.collision ?? this.saved)?.reporting_enabled ?? false; }
  get savedReportingNeedsUsablePlaybook(): boolean {
    const latest = this.collision ?? this.saved;
    return !!latest?.reporting_enabled && !hasUsablePlaybook(latest.playbooks, latest.patterns);
  }
  private get editable(): boolean { return !this.disposed && !this.pending && this.loaded; }

  private accept = (configuration: Configuration): void => {
    this.value = structuredClone($state.snapshot(configuration));
    this.saved = structuredClone($state.snapshot(configuration));
    this.collision = null;
    this.selection = null;
  };

  private failure = (error: unknown, source: 'configuration' | 'pattern' = 'configuration'): void => {
    if (error instanceof AuthenticationRequiredError || (error instanceof HttpError && [401, 403].includes(error.status))) {
      this.dispose();
      this.revoke?.();
      return;
    }
    if (source === 'pattern' && this.selection?.kind === 'new') {
      this.selection.message = 'Reporting defaults could not be loaded. Try again.';
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
    if (this.disposed || this.pending || this.dirty || this.creatingPattern) return;
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
    const parsed = publishSchema.safeParse({ expected_revision: this.revision, reporting_enabled: this.reportingEnabled, patterns: this.value.patterns, playbooks: this.value.playbooks });
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

  editPattern = (id: string): void => {
    if (!this.editable) return;
    const pattern = this.patterns.find((item): boolean => item.id === id);
    if (pattern) this.selection = { kind: 'existing', id, baseline: JSON.stringify(pattern), pendingCategory: '' };
  };

  setPendingCategory = (value: string): void => {
    if (this.selection) this.selection.pendingCategory = value;
  };

  closeEditor = (): void => {
    if (this.busy) return;
    this.selection = null;
  };

  private firstSettingIsFull = (): boolean => (this.value.playbooks[0]?.pattern_ids.filter((id): boolean => this.patterns.some((pattern): boolean => pattern.id === id)).length ?? 0) >= 20;

  private attachPattern = (id: string): void => {
    this.value.playbooks = this.value.playbooks.map((setting, index): DiagnosticPlaybook => {
      if (index !== 0) return setting;
      const references = setting.pattern_ids.length >= 20 ? setting.pattern_ids.filter((reference): boolean => this.patterns.some((pattern): boolean => pattern.id === reference)) : setting.pattern_ids;
      if (references.length !== setting.pattern_ids.length) this.notice = 'Previously removed patterns were cleared from this reporting setup to make room.';
      return { ...setting, pattern_ids: [...references, id] };
    });
  };

  addPattern = (): void => {
    if (!this.editable || this.creatingPattern) return;
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
    const pattern: BehaviourPattern = { id, name: '', description: '', assessment_prompt: '', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'neutral', enabled: true };
    this.selection = { kind: 'new', pattern, baseline: JSON.stringify(pattern), pendingCategory: '', message: '' };
  };

  savePatternEdit = async (): Promise<void> => {
    if (!this.editable || !this.selection || !this.editorDirty) return;
    if (this.selection.kind === 'existing') {
      this.closeEditor();
      return;
    }
    const parsed = patternSchema.safeParse(this.selection.pattern);
    if (!parsed.success) {
      this.selection.message = newPatternFeedback(parsed.error.issues);
      return;
    }
    if (!this.value.playbooks.length) {
      const request = new AbortController();
      this.request = request;
      this.pending = true;
      try {
        const defaults = await this.api.defaults(request.signal);
        if (this.disposed || this.request !== request) return;
        this.value.playbooks = defaults.playbooks.map((setting): DiagnosticPlaybook => ({ ...setting, pattern_ids: [] }));
      } catch (error) {
        if (!this.disposed && this.request === request) this.failure(error, 'pattern');
        return;
      } finally {
        if (!this.disposed && this.request === request) this.pending = false;
      }
    }
    this.closeEditor();
    this.value.patterns.push(parsed.data);
    this.attachPattern(parsed.data.id);
  };

  updatePattern = <K extends Exclude<keyof BehaviourPattern, 'id'>>(id: string, key: K, value: BehaviourPattern[K]): void => {
    if (!this.editable) return;
    const edit = (pattern: BehaviourPattern): BehaviourPattern => {
      const derivesPrompt = key === 'description' && (!pattern.assessment_prompt || pattern.assessment_prompt === pattern.description);
      return { ...pattern, [key]: value, ...(derivesPrompt ? { assessment_prompt: value as string } : {}) };
    };
    if (this.selection?.kind === 'new' && this.selection.pattern.id === id) {
      this.selection.pattern = edit(this.selection.pattern);
      return;
    }
    this.value.patterns = this.value.patterns.map((pattern): BehaviourPattern => pattern.id === id ? edit(pattern) : pattern);
  };

  addCategory = (id: string, input: string): string => {
    const pattern = this.selected;
    if (!this.editable || pattern?.id !== id) return 'The pattern cannot be edited right now.';
    const tag = input.trim().toLowerCase().replace(/\s+/g, '-');
    if (!identifierSchema.safeParse(tag).success) return 'Start with a letter and use up to 64 letters, numbers, or hyphens.';
    if (pattern.categories.includes(tag)) return 'This category is already added.';
    if (pattern.categories.length >= patternCategoryLimit) return `You can add up to ${patternCategoryLimit} categories.`;
    this.updatePattern(id, 'categories', [...pattern.categories, tag]);
    return '';
  };

  removeCategory = (id: string, category: string): void => {
    const pattern = this.selected;
    if (pattern?.id === id) this.updatePattern(id, 'categories', pattern.categories.filter((tag): boolean => tag !== category));
  };

  removePattern = (id: string): void => {
    if (!this.editable) return;
    this.value.patterns = this.value.patterns.filter((pattern): boolean => pattern.id !== id);
    if (this.selection?.kind === 'existing' && this.selection.id === id) this.selection = null;
  };

  setReportingEnabled = (enabled: boolean): void => {
    if (this.editable) this.value.reporting_enabled = enabled;
  };

  canEditPlaybookInclusion = (playbook: ReadonlySettings): boolean => this.playbooks.length > 1 || !playbook.enabled;

  setPlaybookIncluded = (id: string, included: boolean): void => {
    const playbook = this.playbooks.find((setting): boolean => setting.id === id);
    if (playbook && this.canEditPlaybookInclusion(playbook)) this.updatePlaybook(id, { enabled: included });
  };

  updateCollectionInstructions = (id: string, instructions: string): void => {
    this.updatePlaybook(id, { collection_instructions: instructions });
  };

  private updatePlaybook = (id: string, update: Partial<Pick<DiagnosticPlaybook, 'enabled' | 'collection_instructions'>>): void => {
    if (!this.editable) return;
    this.value.playbooks = this.value.playbooks.map((setting): DiagnosticPlaybook => setting.id === id ? { ...setting, ...update } : setting);
  };

  dispose = (): void => {
    if (this.disposed) return;
    this.disposed = true;
    this.request?.abort();
    this.pending = false;
    this.value = { revision: 0, reporting_enabled: false, patterns: [], playbooks: [] };
    this.saved = null;
    this.selection = null;
    this.collision = null;
    this.notice = '';
  };
}
