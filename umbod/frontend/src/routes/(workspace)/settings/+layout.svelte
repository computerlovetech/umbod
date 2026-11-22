<script lang="ts">
  import { page } from '$app/state';
  import SettingsFrame from '#lib/components/settings/SettingsFrame.svelte';
  import type { LayoutProps } from './$types';

  let { children }: LayoutProps = $props();
</script>

<SettingsFrame currentPage={page.route.id === '/(workspace)/settings/tokens' ? 'tokens' : 'profile'}>
  {@render children()}
</SettingsFrame>
