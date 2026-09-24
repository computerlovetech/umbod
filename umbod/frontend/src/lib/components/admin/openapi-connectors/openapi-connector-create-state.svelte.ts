import { normalizeToolNamePrefix } from '$lib/admin/openapi-connectors';

export class OpenApiConnectorCreateState {
  displayName = $state('');
  toolNamePrefix = $state('connector');
  capabilityDescription = $state('');
  submitting = $state(false);
  initialCapabilityOverride = $state(false);
  initialCapabilityOverrideDescription = $state('');
  private toolNamePrefixEdited = false;

  constructor(displayName: string) {
    this.displayName = displayName;
    this.toolNamePrefix = normalizeToolNamePrefix(displayName);
  }

  setDisplayName = (event: Event): void => {
    if (!(event.currentTarget instanceof HTMLInputElement)) return;
    this.displayName = event.currentTarget.value;
    if (!this.toolNamePrefixEdited) this.toolNamePrefix = normalizeToolNamePrefix(this.displayName);
  };
  setToolNamePrefix = (event: Event): void => {
    if (!(event.currentTarget instanceof HTMLInputElement)) return;
    this.toolNamePrefix = event.currentTarget.value;
    this.toolNamePrefixEdited = true;
  };
  setInitialCapabilityOverride = (event: Event): void => { this.initialCapabilityOverride = event.currentTarget instanceof HTMLInputElement && event.currentTarget.checked; };
  beginSubmit = (): void => { this.submitting = true; };
}
