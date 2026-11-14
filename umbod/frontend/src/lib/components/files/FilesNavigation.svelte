<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import type { FilesNavigationState } from '$lib/files/state/navigation-state.svelte';
  import ActionMenu from '$lib/components/shared/ActionMenu.svelte';

  let { state, signIn }: { state: FilesNavigationState; signIn: () => void } = $props();
</script>

<div class="navigation">
    {#if state.path}
      <svg class="location-icon" data-kind={state.rootIcon} aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        {#if state.rootIcon === 'home'}
          <path d="m3 10 9-7 9 7v11h-7v-7h-4v7H3z" />
        {:else if state.rootIcon === 'namespace'}
          <circle cx="9" cy="8" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v2" />
        {:else}
          <path d="M3 6h7l2 3h9v11H3z" />
        {/if}
      </svg>
      <nav class="desktop-path" aria-label="File path">
        <ol>
          {#if !state.displayComplete}
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
      <nav class="mobile-path" aria-label={state.atRoot ? 'File path' : 'Parent folder'}>
        {#if state.atRoot}
          {#each state.visibleItems as item (item.id)}
            <span class="name" aria-current="page" title={state.label(item)}>{state.label(item)}</span>
          {/each}
        {:else if state.parent}
          <a class="parent-link" href={state.href(state.parent)} title={state.label(state.parent)}><span aria-hidden="true">‹</span><span class="name">{state.label(state.parent)}</span></a>
        {:else}
          <span class="name" title="Earlier folders are unavailable">Earlier folders unavailable</span>
        {/if}
      </nav>
    {:else if state.phase === 'loading'}
      <p role="status">Loading file path…</p>
    {:else}
      <p role="status">{state.phase === 'sign-in' ? 'Sign in to view the file path.' : 'File path unavailable.'}</p>
      {#if state.phase === 'sign-in'}<Button variant="secondary" onclick={signIn}>Sign in</Button>{:else}<Button variant="secondary" onclick={state.reload}>Retry file path</Button>{/if}
    {/if}
</div>

<style>
  .navigation { box-sizing: border-box; display: flex; align-items: center; gap: 0.5rem; min-width: 0; max-width: 100%; min-height: 2.75rem; padding: 0 0.75rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-soft); font-size: 0.85rem; }
  .location-icon { flex-shrink: 0; color: var(--admin-accent); }
  nav { min-width: 0; max-width: 100%; }
  .desktop-path { flex: 1; }
  ol { display: flex; align-items: center; gap: 0.5rem; padding: 0; margin: 0; list-style: none; min-width: 0; }
  li { display: flex; align-items: center; gap: 0.5rem; min-width: 0; min-height: 2.625rem; }
  li > span[aria-hidden] { flex: 0 0 auto; color: var(--admin-muted); opacity: 0.65; }
  [aria-current='page'] { color: var(--admin-ink); font-weight: 600; }
  .overflow { flex: 0 0 auto; }
  .partial { color: var(--admin-muted); }
  .partial > span:first-child, .name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  a { color: var(--admin-accent); text-decoration: none; border-radius: 4px; }
  a:hover { background: var(--admin-accent-soft); }
  a.name, .parent-link { display: inline-flex; align-items: center; min-height: 2.625rem; }
  a.name { display: block; line-height: 2.625rem; }
  .mobile-path { display: none; }
  .parent-link { gap: 0.5rem; max-width: 100%; text-decoration: none; }
  p { margin: 0; color: var(--admin-muted); }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  @media (max-width: 640px) {
    .desktop-path { display: none; }
    .mobile-path { display: flex; align-items: center; min-height: 2.625rem; }
  }
</style>
