<script lang="ts">
  import AdminShell from '#lib/components/admin/AdminShell.svelte';
  import AgentTokensWorkspace from '#lib/components/admin/agent-tokens/AgentTokensWorkspace.svelte';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
</script>

<svelte:head><title>Agent tokens · Administration</title></svelte:head>
<AdminShell activeItem="agentTokens" accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} contentWidth="wide">
  {#key data}
    <AgentTokensWorkspace agents={data.agents} groups={data.groups} />
  {/key}
</AdminShell>
