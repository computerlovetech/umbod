<script lang="ts">
  import { filesHref, type FilesState } from '$lib/files/state/files-state.svelte';
  import type { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
  import NewFolderForm from './NewFolderForm.svelte';

  let { state, folder, signIn }: { state: FilesState; folder: NewFolderState; signIn: () => void } = $props();

  function updatedAt(timestamp: string): string {
    return new Date(timestamp).toLocaleString();
  }
</script>

<div class="heading">
  <h1 class="admin-title">Files</h1>
  {#if state.phase === 'ready' && state.node?.kind === 'directory'}
    <button id="new-folder-button" onclick={folder.show} disabled={folder.open}>New folder</button>
  {/if}
</div>
<nav class="breadcrumbs" aria-label="Visited folders">
  <a href="/files">Files</a>
  {#each state.trail as item (item.id)}
    <span aria-hidden="true">/</span>
    <a href={filesHref(item.id)} aria-current={state.node?.id === item.id ? 'page' : undefined}>{item.name}</a>
  {/each}
</nav>

{#if state.phase === 'loading'}
  <p role="status">Loading files…</p>
{:else if state.phase !== 'ready'}
  <p role="alert">{state.phase === 'denied' ? "You don't have access to this location." : state.phase === 'sign-in' ? 'Sign in to view files.' : state.phase === 'missing' ? 'This location is unavailable.' : "Couldn't load files."}</p>
  {#if state.phase === 'sign-in'}
    <button onclick={signIn}>Sign in</button>
  {:else}
    <button onclick={folder.reload}>Retry</button>
  {/if}
{:else if state.node}
  {#if state.node.kind === 'directory'}
    {#if folder.open}<NewFolderForm state={folder} />{/if}
    {#if state.children.length === 0}
      <p role="status">This folder is empty.</p>
    {:else}
      <div class="items">
        <table>
          <caption class="visually-hidden">Files and folders</caption>
          <thead><tr><th scope="col">Name</th><th scope="col">Type</th><th scope="col">Updated</th></tr></thead>
          <tbody>
            {#each state.children as item (item.id)}
              <tr>
                <td>
                  <a class="item-name" href={filesHref(item.id)}>
                    <svg role="img" aria-label={item.kind === 'directory' ? 'Folder' : 'File'} viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5">
                      {#if item.kind === 'directory'}<path d="M3 6h7l2 3h9v11H3z" />{:else}<path d="M6 3h8l4 4v14H6z M14 3v5h4" />{/if}
                    </svg>
                    {item.name}
                  </a>
                </td>
                <td>{item.kind === 'directory' ? 'Folder' : 'File'}</td>
                <td><time datetime={item.updated_at}>{updatedAt(item.updated_at)}</time></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {:else}
    <section aria-label="File details" class="details">
      <h2>{state.node.name}</h2>
      <dl>
        <dt>Type</dt><dd>File</dd>
        <dt>Content type</dt><dd>{typeof state.node.metadata.content_type === 'string' ? state.node.metadata.content_type : 'Not specified'}</dd>
        <dt>Updated</dt><dd><time datetime={state.node.updated_at}>{updatedAt(state.node.updated_at)}</time></dd>
        {#each Object.entries(state.node.metadata.attributes) as [name, value] (name)}
          <dt>{name}</dt><dd>{value}</dd>
        {/each}
      </dl>
      {#if typeof state.node.parent_id === 'string'}<a href={filesHref(state.node.parent_id)}>Open parent folder</a>{/if}
    </section>
  {/if}
{/if}

<style>
  .heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
  .breadcrumbs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0 1.5rem; }
  a { color: var(--admin-accent); overflow-wrap: anywhere; }
  button { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-ink); font: inherit; cursor: pointer; padding: 0.6rem 0.9rem; }
  button:disabled { opacity: 0.6; cursor: default; }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .items { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem; }
  th, td { padding: 0.8rem 0.6rem; border-bottom: 1px solid var(--admin-border); }
  th { color: var(--admin-muted); font-weight: 500; }
  .item-name { display: flex; align-items: center; gap: 0.6rem; }
  svg { flex-shrink: 0; }
  p, dt { color: var(--admin-muted); }
  [role='alert'] { color: var(--admin-danger); }
  h2 { font-size: 1.15rem; overflow-wrap: anywhere; }
  dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.65rem 1rem; font-size: 0.9rem; }
  dd { margin: 0; overflow-wrap: anywhere; }
  .details { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 1rem; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
</style>
