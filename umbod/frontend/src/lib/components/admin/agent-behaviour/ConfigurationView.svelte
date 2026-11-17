<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  import ConfigurationEditor from './ConfigurationEditor.svelte';
  let { state }: { state: ConfigurationState } = $props();
  onDestroy((): void => state.closeEditor());
</script>

<a class="admin-back-link" href="/admin/insights/agent-behaviour">← Agent behaviour</a>
<header class="insight-heading"><h2>Configuration</h2></header>
<ConfigurationEditor {state} />
