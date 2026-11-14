<script lang="ts">
  import type { Snippet } from 'svelte';
  import { page } from '$app/state';
  import InsightsLayout from '$lib/components/admin/insights/InsightsLayout.svelte';
  import type { LayoutData } from './$types';

  let { data, children }: { data: LayoutData; children: Snippet } = $props();
</script>

<InsightsLayout accountIdentity={data.accountIdentity} pathname={page.url.pathname}>
  {@render children()}
</InsightsLayout>
