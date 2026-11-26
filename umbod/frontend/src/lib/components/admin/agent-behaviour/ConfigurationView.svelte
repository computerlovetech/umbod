<script lang="ts">
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import { agentBehaviourFindingsHref, agentDiagnosticsReportingHref } from '#lib/workspace/navigation.js';
  import type { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  import ConfigurationEditor from './ConfigurationEditor.svelte';

  let { state }: { state: ConfigurationState } = $props();
</script>

<SubpageContainer title="Agent diagnostics">
  {#snippet actions()}
    <div class="actions">
      <a class="admin-back-link" href={agentDiagnosticsReportingHref}>Reporting settings</a>
      <a class="admin-back-link" href={agentBehaviourFindingsHref}>View findings <span aria-hidden="true">→</span></a>
    </div>
  {/snippet}
  <ConfigurationEditor {state} section="patterns" />
</SubpageContainer>

<style>
  .actions { display: flex; flex-wrap: wrap; gap: .75rem 1rem; }
  a { gap: .35rem; margin-bottom: 0; }
</style>
