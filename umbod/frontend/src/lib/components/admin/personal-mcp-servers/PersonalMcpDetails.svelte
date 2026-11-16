<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import PersonalServerPolicyPanel from './PersonalServerPolicyPanel.svelte';
  import type { PersonalOAuthSetupState } from './personal-oauth-setup-state.svelte';

  let { state, connectorId }: { state: PersonalOAuthSetupState; connectorId: string } = $props();
  const lifetime = untrack(() => ({ state, connectorId }));
  onMount(() => { void lifetime.state.load(lifetime.connectorId); return lifetime.state.detach; });
</script>

<PersonalServerPolicyPanel />
