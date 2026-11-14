<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import InsightsWorkspace from './InsightsWorkspace.svelte';
  import { createInsightsState } from './insights-factory';
  import type { InsightsState } from './insights-state.svelte';

  let { accountIdentity, pathname, children, createState = createInsightsState }: {
    accountIdentity: HeaderAccountIdentityState;
    pathname: string;
    children: Snippet;
    createState?: () => InsightsState;
  } = $props();
</script>

<AdminShell activeItem="insights" {accountIdentity} contentWidth="wide" navigationScope="/admin/insights">
  {#if accountIdentity.kind === 'visible'}
    {#key accountIdentity.hiddenValues.id}
      <InsightsWorkspace {pathname} {createState}>{@render children()}</InsightsWorkspace>
    {/key}
  {:else}
    <p class="admin-message admin-message--error" role="alert">Administration access is no longer available. Reload or sign in again.</p>
  {/if}
</AdminShell>
