<script lang="ts">
  import type { FilesNavigationState } from '$lib/files/state/navigation-state.svelte';
  import ActionMenu from '$lib/components/shared/ActionMenu.svelte';

  let { state, signIn }: { state: FilesNavigationState; signIn: () => void } = $props();
</script>

{#if !state.atRoot}
  <div class="navigation">
    {#if state.path}
      <nav class="desktop-path" aria-label="File path">
        <ol>
          {#if !state.path.complete}
            <li class="partial"><span title="Earlier folders are unavailable">Earlier folders unavailable</span><span aria-hidden="true">/</span></li>
          {/if}
          {#each state.visibleItems as item, index (item.id)}
            {#if index === 1 && state.omittedAncestors.length > 0}
              <li class="overflow">
                <span aria-hidden="true">/</span>
                <ActionMenu open={state.menuOpen} label="Show parent folders" onopenchange={state.setMenuOpen}>
                  {#snippet trigger()}<span aria-hidden="true">…</span>{/snippet}
                  {#snippet menu()}
                    {#each state.omittedAncestors as ancestor (ancestor.id)}
                      <a role="menuitem" href={state.href(ancestor)} title={state.label(ancestor)}>{state.label(ancestor)}</a>
                    {/each}
                  {/snippet}
                </ActionMenu>
              </li>
            {/if}
            <li>
              {#if index > 0}<span aria-hidden="true">/</span>{/if}
              {#if index === state.visibleItems.length - 1}
                <span class="name" aria-current="page" title={state.label(item)}>{state.label(item)}</span>
              {:else}
                <a class="name" href={state.href(item)} title={state.label(item)}>{state.label(item)}</a>
              {/if}
            </li>
          {/each}
        </ol>
      </nav>
      <nav class="mobile-path" aria-label="Parent folder">
        {#if state.parent}
          <a class="parent-link" href={state.href(state.parent)} title={state.label(state.parent)}><span aria-hidden="true">‹</span><span class="name">{state.label(state.parent)}</span></a>
        {:else}
          <span class="name" title="Earlier folders are unavailable">Earlier folders unavailable</span>
        {/if}
      </nav>
    {:else if state.phase === 'loading'}
      <p role="status">Loading file path…</p>
    {:else}
      <p role="status">{state.phase === 'sign-in' ? 'Sign in to view the file path.' : 'File path unavailable.'}</p>
      {#if state.phase === 'sign-in'}<button onclick={signIn}>Sign in</button>{:else}<button onclick={state.reload}>Retry file path</button>{/if}
    {/if}
  </div>
{/if}

<style>
  .navigation { box-sizing: border-box; display: flex; align-items: center; gap: 0.75rem; min-width: 0; max-width: 100%; margin: 1rem 0; }
  nav { min-width: 0; max-width: 100%; }
  .desktop-path { flex: 1; }
  ol { display: flex; align-items: center; gap: 0.5rem; padding: 0; margin: 0; list-style: none; min-width: 0; }
  li { display: flex; align-items: center; gap: 0.5rem; min-width: 0; }
  li > span[aria-hidden] { flex: 0 0 auto; }
  .overflow { flex: 0 0 auto; }
  .partial { color: var(--admin-muted); }
  .partial > span:first-child, .name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  a { color: var(--admin-accent); }
  a.name, .parent-link { display: inline-flex; align-items: center; min-height: 2.75rem; }
  a.name { display: block; line-height: 2.75rem; }
  .mobile-path { display: none; }
  .parent-link { gap: 0.5rem; max-width: 100%; text-decoration: none; }
  button { background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 0.5rem; font: inherit; cursor: pointer; }
  p { margin: 0; color: var(--admin-muted); }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  @media (max-width: 640px) {
    .desktop-path { display: none; }
    .mobile-path { display: block; }
  }
</style>
