import { CapabilityDescriptionConflictError, type CapabilityDescriptionResponse } from '$lib/admin/capability-descriptions';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import type { ToastApi } from '$lib/components/feedback';

export type SaveResult = CapabilityDescriptionResponse | { kind: 'conflict'; current: CapabilityDescriptionResponse };

function isConflictResult(result: SaveResult): result is { kind: 'conflict'; current: CapabilityDescriptionResponse } {
  return 'kind' in result && result.kind === 'conflict';
}

export class CapabilityDescriptionOverrideState {
  current = $state.raw<CapabilityDescriptionResponse>();
  draft = $state('');
  loading = $state(false);
  saving = $state(false);
  message = $state<string>();
  confirmingRestore = $state(false);

  constructor(current?: CapabilityDescriptionResponse, private readonly toast?: ToastApi) {
    if (current) this.apply(current, true);
  }

  get characterCount(): number { return this.draft.length; }
  get validationMessage(): string | undefined {
    if (!this.draft.trim()) return 'Enter an override description.';
    if (/[\u0000-\u001f\u007f]/.test(this.draft)) return 'Control characters are not allowed.';
    if (this.draft.length > 300) return 'Override descriptions must be 300 characters or fewer.';
    return undefined;
  }
  get canSave(): boolean { return Boolean(this.current) && !this.validationMessage && !this.saving; }

  load = async (loader: () => Promise<CapabilityDescriptionResponse>): Promise<void> => {
    this.loading = true;
    try { this.apply(await loader(), true); this.message = undefined; }
    catch (error) {
      if (!(error instanceof BrowserRequestError)) throw error;
      this.message = 'Capability description settings could not be loaded.';
      this.toast?.error(this.message);
    }
    finally { this.loading = false; }
  };
  updateDraft = (value: string): void => { this.draft = value; this.message = undefined; };
  requestRestore = (): void => { this.confirmingRestore = true; };
  cancelRestore = (): void => { this.confirmingRestore = false; };
  save = async (saveOverride: () => Promise<SaveResult>): Promise<void> => {
    if (!this.canSave) return;
    this.saving = true;
    try {
      const result = await saveOverride();
      if (isConflictResult(result)) { this.apply(result.current, false); this.message = 'This description changed elsewhere. Current state was refreshed; review your draft and save again.'; }
      else { this.apply(result, true); this.message = 'Override saved.'; this.toast?.success(this.message); }
    } catch (error) {
      if (error instanceof CapabilityDescriptionConflictError) { this.apply(error.current, false); this.message = 'This description changed elsewhere. Current state was refreshed; review your draft and save again.'; }
      else if (error instanceof BrowserRequestError) { this.message = 'Override was not saved. Your draft has been preserved.'; this.toast?.error(this.message); }
      else throw error;
    } finally { this.saving = false; }
  };
  restore = async (clearOverride: () => Promise<CapabilityDescriptionResponse>): Promise<void> => {
    if (!this.current || this.current.override.state === 'system') return;
    this.saving = true;
    try { this.apply(await clearOverride(), true); this.confirmingRestore = false; this.message = 'System default restored.'; this.toast?.success(this.message); }
    catch (error) {
      if (error instanceof CapabilityDescriptionConflictError) { this.apply(error.current, false); this.message = 'This description changed elsewhere. Current state was refreshed; try restoring again.'; }
      else if (error instanceof BrowserRequestError) { this.message = 'System default was not restored. Your draft has been preserved.'; this.toast?.error(this.message); }
      else throw error;
    } finally { this.saving = false; }
  };
  private apply(current: CapabilityDescriptionResponse, replaceDraft: boolean): void {
    this.current = current;
    if (replaceDraft) this.draft = current.override.state === 'overridden' ? current.override.description : current.base_description;
  }
}
