<script lang="ts">
  import Button from '../shared/Button.svelte';
  import type { NamespaceManagementState } from './namespace-management-state.svelte';

  let { state }: { state: NamespaceManagementState } = $props();
</script>

<Button disabled={!state.canOpenEditor} onclick={state.beginCreate}>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="M12 5v14M5 12h14" /></svg>
  Add Namespace
</Button>

<style>
  svg { display: block; height: 1.125rem; width: 1.125rem; }
</style>
