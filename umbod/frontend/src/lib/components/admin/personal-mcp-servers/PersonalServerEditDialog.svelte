<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import type { PersonalServerDiscovery } from '$lib/admin/personal-mcp-servers/discovery-administration';
  import type { PersonalServerAdministration } from '$lib/admin/personal-mcp-servers/administration';
  import type { InstanceConfigurationRoute } from '$lib/admin/instance-configuration-api';
  import PersonalServerRegistration from './PersonalServerRegistration.svelte';
  import { PersonalServerFormState } from './personal-server-form-state.svelte';

  import type { DownstreamMcpConnector } from '$lib/admin/downstream-mcp-connectors';
  import type { PolicyProposal } from './policy-form.svelte';
  let { connectorId, close, api, configuration, accessLost, lockChanged, reconciliationRequired, saved, proposal, discovery }: {
    connectorId: string;
    close: () => void;
    api?: PersonalServerAdministration;
    discovery?: PersonalServerDiscovery;
    configuration?: InstanceConfigurationRoute;
    accessLost: () => void;
    lockChanged: (locked: boolean) => void;
    reconciliationRequired: (message: string) => void;
    saved?: (connector: DownstreamMcpConnector) => void;
    proposal?: PolicyProposal;
  } = $props();
  const dependencies = untrack(() => {
    const composite = api && configuration && discovery ? null : adminApi();
    return { api: api ?? composite!.personalServers, configuration: configuration ?? composite!.instanceConfiguration, discovery: discovery ?? composite!.personalServerDiscovery };
  });
  const state = new PersonalServerFormState(dependencies.api, dependencies.configuration, untrack(() => connectorId), dependencies.discovery, async (_id, connector) => { if (connector) saved?.(connector); close(); }, untrack(() => accessLost), untrack(() => lockChanged));
  onMount(() => { void state.reload(); return state.dispose; });

  function closeEditor(): void {
    if (state.busy) return;
    if (state.blocked) reconciliationRequired(state.message);
    state.close();
    close();
  }
</script>

<PersonalServerRegistration {state} {proposal} close={closeEditor} reload={state.reload} />
