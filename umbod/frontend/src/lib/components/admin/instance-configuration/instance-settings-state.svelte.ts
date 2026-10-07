import type { InstanceConfigurationPageData } from '$lib/admin/instance-configuration';
import { presentConfiguration } from './presentation';

export class InstanceSettingsState {
  presentation = $derived.by(() => {
    const state = this.readState();
    return presentConfiguration(state.status === 'ready' ? state.configuration : { groups: [] });
  });

  constructor(private readonly readState: () => InstanceConfigurationPageData) {}
}
