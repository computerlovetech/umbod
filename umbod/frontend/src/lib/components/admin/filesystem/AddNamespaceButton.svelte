<script lang="ts">
  import Button from '../shared/Button.svelte';
  import PlusIcon from '#lib/components/shared/PlusIcon.svelte';
  import type { NamespaceManagementState } from './namespace-management-state.svelte';

  let { state }: { state: NamespaceManagementState } = $props();
</script>

<Button disabled={!state.canOpenEditor} onclick={state.beginCreate}>
  <PlusIcon />
  Add Namespace
</Button>
