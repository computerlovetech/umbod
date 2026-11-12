<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import type { FilePreviewState } from '$lib/files/preview/file-preview-state.svelte';

  let { state, signIn }: { state: FilePreviewState; signIn: () => void } = $props();
</script>

{#if state.phase !== 'hidden'}
  <section class="file-preview" aria-label="File preview" aria-busy={state.phase === 'loading'}>
    {#if state.phase === 'ready' && state.adapter}
      {@const Renderer = state.adapter.component}
      <Renderer content={state.content} />
    {:else if state.phase === 'loading'}
      <p role="status">Loading preview…</p>
    {:else if state.phase === 'empty'}
      <p role="status">This file is empty.</p>
    {:else if state.phase === 'unsupported'}
      <p>Preview is not available for this file type.</p>
    {:else if state.phase === 'too-large'}
      <p>Preview is available for files up to 1 MiB.</p>
    {:else if state.phase === 'denied'}
      <p role="alert">You don't have access to this file's content.</p>
    {:else if state.phase === 'missing'}
      <p role="alert">This file is no longer available.</p>
    {:else if state.phase === 'sign-in'}
      <p role="alert">Sign in to preview this file.</p>
      <Button variant="secondary" onclick={signIn}>Sign in</Button>
    {:else}
      <p role="alert">Couldn't load the preview.</p>
      <Button variant="secondary" onclick={state.retry}>Retry preview</Button>
    {/if}
  </section>
{/if}

<style>
  .file-preview { min-width: 0; margin-bottom: 1.5rem; }
  p { color: var(--admin-muted); }
  [role='alert'] { color: var(--admin-danger); }
</style>
