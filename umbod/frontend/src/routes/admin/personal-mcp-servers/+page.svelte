<script lang="ts">
  import { replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import PersonalServersPage from '$lib/components/admin/personal-mcp-servers/PersonalServersPage.svelte';
  import type { PageData } from './$types';
  let { data }: { data: PageData } = $props();
  function selectionChanged(id: string | null): void {
    const url = new URL(page.url);
    if (id) url.searchParams.set('connector', id);
    else url.searchParams.delete('connector');
    replaceState(url, {});
  }
</script>

{#key data}
  <PersonalServersPage accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} requestedId={data.requestedId} {selectionChanged} />
{/key}
