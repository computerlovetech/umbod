<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import McpSetupGuide from '$lib/components/admin/mcp-setup/McpSetupGuide.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<svelte:head><title>Connect Umbod</title></svelte:head>

<AdminShell activeItem="mcpSetup" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity} contentWidth="wide">
  <McpSetupGuide mcpEndpoint={data.mcpEndpoint} />
</AdminShell>
