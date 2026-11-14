<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import type { PersonalServerAdministration } from '$lib/admin/personal-mcp-servers/administration';
  import type { InstanceConfigurationRoute } from '$lib/admin/instance-configuration-api';
  import PersonalServerRegistration from './PersonalServerRegistration.svelte';
  import { PersonalServerFormState } from './personal-server-form-state.svelte';

  let { connectorId, close, api, configuration, accessLost, lockChanged, reconciliationRequired }: {
    connectorId: string;
    close: () => void;
    api?: PersonalServerAdministration;
    configuration?: InstanceConfigurationRoute;
    accessLost: () => void;
    lockChanged: (locked: boolean) => void;
    reconciliationRequired: (message: string) => void;
  } = $props();
  const dependencies = untrack(() => {
    const composite = api && configuration ? null : adminApi();
    return { api: api ?? composite!.personalServers, configuration: configuration ?? composite!.instanceConfiguration };
  });
  const state = new PersonalServerFormState(dependencies.api, dependencies.configuration, untrack(() => connectorId), async () => close(), untrack(() => accessLost), untrack(() => lockChanged));
  onMount(() => { void state.reload(); return state.dispose; });

  function closeEditor(): void {
    if (state.busy) return;
    if (state.blocked) reconciliationRequired(state.message);
    state.close();
    close();
  }
</script>

<PersonalServerRegistration {state} close={closeEditor} reload={state.reload} />
