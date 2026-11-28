<script lang="ts">
  import { goto } from '$app/navigation';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import { getAddConnector } from '#lib/components/admin/connectors/add-connector-state.svelte.js';
  import PortableConnectorWorkspace from '#lib/components/admin/portable-connectors/PortableConnectorWorkspace.svelte';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const api = adminApi().portableConnectors;
  const addConnector = getAddConnector();
</script>

{#key data}
  <PortableConnectorWorkspace {data} {api} {addConnector} navigate={(href) => goto(href, { reset: false })} />
{/key}
