<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import type { FilesState } from '#lib/files/state/files-state.svelte.js';

  let { state, signIn }: { state: FilesState; signIn: () => void } = $props();
</script>

<nav aria-label="File locations">
  <div class="groups">
  {#each state.locationGroups as group (group.kind)}
    <section aria-label={group.label}>
      <h2>{group.label}</h2>
      <ul>
        {#each group.locations as location (location.id)}
          <li>
            <a href={location.href} aria-current={location.selected ? 'page' : undefined}>
              <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                {#if group.kind === 'personal'}<path d="M3 6h6l2 3h10v11H3Z" /><circle cx="12" cy="13" r="2" /><path d="M8.5 18c.4-2.7 6.6-2.7 7 0" />{:else}<circle cx="9" cy="8" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v2" />{/if}
              </svg>
              <span>{location.label}</span>
              {#if location.selected}<svg class="check" aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6" /></svg>{/if}
            </a>
          </li>
        {/each}
      </ul>
    </section>
  {/each}
  </div>
  {#if state.discoveryPhase !== 'ready' && state.discoveryPhase !== 'loading'}
    <div class="recovery">
      <p role="alert">{state.discoveryPhase === 'sign-in' ? 'Sign in to view locations.' : state.discoveryPhase === 'denied' ? "You don't have access to the locations list." : "Couldn't load locations."}</p>
      {#if state.discoveryPhase === 'sign-in'}<Button variant="secondary" onclick={signIn}>Sign in</Button>{:else}<Button variant="secondary" onclick={state.reload}>Retry locations</Button>{/if}
    </div>
  {:else if state.discoveryPhase === 'ready' && state.locationGroups.length === 0}
    <p role="status">No locations available.</p>
  {/if}
</nav>

<style>
  nav { min-width: 0; padding: 0 0.75rem 1rem; }
  .groups { display: grid; gap: 1.25rem; min-width: 0; }
  section { min-width: 0; }
  @container (max-width: 760px) {
    .groups { grid-template-columns: repeat(auto-fit, minmax(min(100%, 8rem), 1fr)); }
  }
  h2 { margin: 0 0 0.5rem; padding-inline: 0.5rem; color: var(--admin-muted); font-size: 0.625rem; font-weight: 600; letter-spacing: 0.075em; text-transform: uppercase; }
  ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.25rem; }
  li { min-width: 0; }
  a { box-sizing: border-box; min-width: 0; min-height: 44px; display: flex; align-items: center; gap: 0.6rem; padding: 0.65rem 0.5rem; border-radius: var(--admin-radius); color: var(--admin-ink); text-decoration: none; font-size: 0.9rem; }
  a:hover { background: var(--admin-panel); }
  a[aria-current] { background: var(--admin-accent-soft); color: var(--admin-accent); font-weight: 600; }
  a:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 2px; }
  span { min-width: 0; overflow-wrap: anywhere; flex: 1; }
  svg { flex-shrink: 0; }
  p { color: var(--admin-muted); font-size: 0.85rem; overflow-wrap: anywhere; }
  [role='alert'] { color: var(--admin-danger); }
</style>
