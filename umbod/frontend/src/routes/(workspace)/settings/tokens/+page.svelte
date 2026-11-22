<script lang="ts">
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import PersonalTokens from '#lib/components/settings/PersonalTokens.svelte';
  import { workspaceSettingsHref } from '#lib/workspace/navigation.js';
</script>

<svelte:head><title>Tokens · Settings · Umbod</title></svelte:head>

<SubpageContainer title="Tokens">
  {#snippet navigation()}
    <a class="admin-back-link" href={workspaceSettingsHref}>Back to Settings</a>
  {/snippet}
  <PersonalTokens />
</SubpageContainer>
