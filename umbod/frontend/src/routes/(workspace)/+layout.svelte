<script lang="ts">
  import { page } from '$app/state';
  import WorkspaceFrame from '#lib/components/workspace/WorkspaceFrame.svelte';
  import type { LayoutProps } from './$types';

  let { children, data }: LayoutProps = $props();
</script>

<WorkspaceFrame pathname={page.url.pathname} accountIdentity={data.accountIdentity}>
  {@render children()}
</WorkspaceFrame>
