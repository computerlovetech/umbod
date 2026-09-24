<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';

  let { data }: { data: { accountIdentity?: HeaderAccountIdentityState } } = $props();
  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<svelte:head><title>OpenAPI connector</title></svelte:head>

<AdminShell activeItem="connectors" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity}>
  <div class="admin-page">
    <p class="admin-message">Redirecting to OpenAPI connectors…</p>
    <a class="admin-back-link" href="/admin/openapi-connectors">← OpenAPI connectors</a>
  </div>
</AdminShell>
