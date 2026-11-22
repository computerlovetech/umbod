<script lang="ts">
  import { onDestroy } from 'svelte';
  import SubpageNavigation, { type SubpageLink } from '#lib/components/shared/workspace/SubpageNavigation.svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import { agentBehaviourFindingsHref, agentDiagnosticsHref } from '#lib/workspace/navigation.js';
  import type { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  import ConfigurationEditor from './ConfigurationEditor.svelte';
  const links: readonly SubpageLink[] = [
    { id: 'patterns', label: 'Patterns', href: agentDiagnosticsHref },
    { id: 'reporting', label: 'Reporting settings', href: `${agentDiagnosticsHref}?tab=reporting` }
  ];
  let { state, section = 'patterns' }: { state: ConfigurationState; section?: 'patterns' | 'reporting' } = $props();
  onDestroy((): void => state.closeEditor());
</script>

<SubpageContainer title="Agent diagnostics">
  {#snippet actions()}
    <a class="admin-back-link" href={agentBehaviourFindingsHref}>View findings <span aria-hidden="true">→</span></a>
  {/snippet}
  <SubpageNavigation {links} activeId={section} label="Agent diagnostics subpages" />
  <ConfigurationEditor {state} {section} />
</SubpageContainer>

<style>
  a { gap: .35rem; }
</style>
