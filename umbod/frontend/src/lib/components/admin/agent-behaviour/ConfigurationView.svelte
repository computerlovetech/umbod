<script lang="ts">
  import { onDestroy } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import { agentBehaviourFindingsHref } from '#lib/workspace/navigation.js';
  import type { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  import ConfigurationEditor from './ConfigurationEditor.svelte';
  let { state }: { state: ConfigurationState } = $props();
  onDestroy((): void => state.closeEditor());
</script>

<SubpageContainer title="Agent diagnostics">
  {#snippet actions()}
    {#if state.loaded}<Button disabled={state.busy} onclick={state.addPattern}>Add pattern</Button>{/if}
  {/snippet}
  <a class="admin-back-link" href={agentBehaviourFindingsHref}>View findings <span aria-hidden="true">→</span></a>
  <ConfigurationEditor {state} />
</SubpageContainer>

<style>
  a { gap: .35rem; }
</style>
