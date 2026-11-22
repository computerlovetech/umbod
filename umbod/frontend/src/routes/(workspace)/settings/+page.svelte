<script lang="ts">
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import { workspaceTokensHref } from '#lib/workspace/navigation.js';
</script>

<svelte:head><title>Settings · Umbod</title></svelte:head>

<SubpageContainer title="Settings">
  <a class="admin-card-link" href={workspaceTokensHref}>Tokens</a>
</SubpageContainer>
