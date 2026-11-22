<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import PersonalServerPolicyPanel from './PersonalServerPolicyPanel.svelte';
  import type { PersonalOAuthSetupState } from './personal-oauth-setup-state.svelte';

  let { state, connectorId, locked, oncheck, onreview }: {
    state: PersonalOAuthSetupState;
    connectorId: string;
    locked: boolean;
    oncheck: (trigger: HTMLElement) => void;
    onreview: (trigger: HTMLElement) => void;
  } = $props();
  const startCheck = $derived(state.outcome === 'required' && state.canCheck);
  const checkMessage = $derived(state.validated
    ? 'Provider metadata checked. User sign-in not tested.'
    : startCheck ? 'Check saved OAuth settings before publishing.' : state.message);
  const lifetime = untrack(() => ({ state, connectorId }));
  onMount(() => { void lifetime.state.load(lifetime.connectorId); return lifetime.state.detach; });
</script>

<PersonalServerPolicyPanel
  policy={state.policy?.connector_id === connectorId ? state.policy : null}
  checkStatus={state.sidebarLabel(connectorId)}
  {checkMessage}
  checked={state.policy?.connector_id === connectorId && state.validated}
  locked={locked || state.pending !== null}
  checkAction={startCheck ? 'Check configuration' : state.validated ? 'View check' : 'Review check'}
  oncheck={startCheck ? oncheck : onreview}
/>
