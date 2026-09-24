<script lang="ts">
  import type { Snippet } from 'svelte';
  import ToastRegion from './ToastRegion.svelte';
  import { provideToast } from './toast-context';
  import { ToastState } from './toast-state.svelte';

  let { children }: { children: Snippet } = $props();

  const state = new ToastState();
  provideToast(state);
</script>

{@render children()}
<ToastRegion {state} />
