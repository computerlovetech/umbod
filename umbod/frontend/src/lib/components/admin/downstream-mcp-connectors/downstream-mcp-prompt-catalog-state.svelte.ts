import type { CapabilityActivationStatus, PromptActivationBatchResponse, PromptCatalog } from '$lib/admin/capability-catalogs';

export class DownstreamMcpPromptCatalogState {
  prompts: PromptCatalog['prompts'];
  persistedStatuses: Record<string, CapabilityActivationStatus>;
  pending = $state(false);
  changedPrompts = $derived.by(() =>
    this.prompts
      .filter((prompt) => this.persistedStatuses[prompt.name] !== prompt.activation_status)
      .map((prompt) => ({ prompt_id: prompt.name, activation_status: prompt.activation_status }))
  );
  dirty = $derived(this.changedPrompts.length > 0);
  catalog = $derived.by((): PromptCatalog => ({
    prompts: this.prompts,
    available_actions: this.prompts.length ? ['activate'] : []
  }));

  constructor(catalog: PromptCatalog) {
    this.prompts = $state(catalog.prompts);
    this.persistedStatuses = $state(Object.fromEntries(catalog.prompts.map((prompt) => [prompt.name, prompt.activation_status])));
  }

  setPromptActivation = (name: string, enabled: boolean): void => {
    if (this.pending) return;
    const activationStatus: CapabilityActivationStatus = enabled ? 'enabled' : 'disabled';
    this.prompts = this.prompts.map((prompt) =>
      prompt.name === name ? { ...prompt, activation_status: activationStatus } : prompt
    );
  };

  activationEnabled = (name: string): boolean =>
    (this.prompts.find((prompt) => prompt.name === name)?.activation_status ?? 'disabled') === 'enabled';

  beginSave = (): void => {
    this.pending = true;
  };

  finishSave = (response?: PromptActivationBatchResponse): void => {
    if (response) {
      this.persistedStatuses = {
        ...this.persistedStatuses,
        ...Object.fromEntries(response.prompts.map((prompt) => [prompt.prompt_id, prompt.activation_status]))
      };
      this.prompts = this.prompts.map((prompt) => ({
        ...prompt,
        activation_status: this.persistedStatuses[prompt.name] ?? prompt.activation_status
      }));
    }
    this.pending = false;
  };

  reconcileAuthoritative = (response: PromptActivationBatchResponse): void => {
    this.persistedStatuses = Object.fromEntries(response.prompts.map((prompt) => [prompt.prompt_id, prompt.activation_status]));
  };

  activationRequestJson = (): string => JSON.stringify(this.changedPrompts);
}
