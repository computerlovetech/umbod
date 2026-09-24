import { describe, expect, test } from 'vitest';
import { ConnectorConfigurationFormState } from '$lib/components/admin/connectors/connector-configuration-form-state.svelte';

describe('connector configuration form state', () => {
  test('allows saving only after the current form signature has passed a check', () => {
    const state = new ConnectorConfigurationFormState();

    state.replaceCurrentSignature('workspace=acme&token=secret');

    expect(state.saveEnabled).toBe(false);

    state.markChecked('workspace=acme&token=secret');

    expect(state.saveEnabled).toBe(true);
  });

  test('disables saving when form values change after a successful check', () => {
    const state = new ConnectorConfigurationFormState();

    state.replaceCurrentSignature('workspace=acme&token=secret');
    state.markChecked('workspace=acme&token=secret');
    state.replaceCurrentSignature('workspace=acme&token=changed');

    expect(state.saveEnabled).toBe(false);
    expect(state.feedback('check-valid', undefined)).toEqual({
      message: 'Run configuration check before saving.',
      tone: 'warning'
    });
  });
});
