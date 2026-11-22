<script lang="ts">
  import AccountProfile from '#lib/components/settings/AccountProfile.svelte';
  import { useWorkspace } from '#lib/workspace/workspace-context.js';

  const workspace = useWorkspace();
</script>

<svelte:head><title>Profile · Account settings · Umbod</title></svelte:head>

<AccountProfile identity={workspace.personalIdentity} />
