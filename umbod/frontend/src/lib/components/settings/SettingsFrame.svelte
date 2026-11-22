<script lang="ts">
  import type { Snippet } from 'svelte';
  import { workspaceSettingsHref, workspaceTokensHref } from '#lib/workspace/navigation.js';

  type SettingsPage = 'profile' | 'tokens';

  let { currentPage, children }: { currentPage: SettingsPage; children: Snippet } = $props();

  const pageLabels: Record<SettingsPage, string> = { profile: 'Profile', tokens: 'Access tokens' };
</script>

{#snippet profileIcon()}
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21v-2a5 5 0 0 1 5-5h6a5 5 0 0 1 5 5v2" />
  </svg>
{/snippet}

<div class="settings-frame">
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <ol>
      <li>Account</li>
      <li aria-current="page">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
        {pageLabels[currentPage]}
      </li>
    </ol>
  </nav>

  <header class="hero">
    <p class="eyebrow">{@render profileIcon()} Your account</p>
    <h1 class="admin-title">Account settings</h1>
    <p class="admin-lede">View your profile and manage personal access.</p>
  </header>

  <div class="settings-columns">
    <nav class="settings-nav" aria-label="Account settings">
      <div>
        <p class="eyebrow">Personal</p>
        <a href={workspaceSettingsHref} aria-current={currentPage === 'profile' ? 'page' : undefined}>
          {@render profileIcon()} {pageLabels.profile}
        </a>
      </div>
      <div>
        <p class="eyebrow">Access</p>
        <a href={workspaceTokensHref} aria-current={currentPage === 'tokens' ? 'page' : undefined}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3a6 6 0 0 0-5.7 7.8L3 17v4h4v-3h3v-3l1.2-1.2A6 6 0 1 0 15 3zM16 8h.01" /></svg>
          {pageLabels.tokens}
        </a>
      </div>
    </nav>
    <div class="settings-content">
      {@render children()}
    </div>
  </div>
</div>

<style>
  .settings-frame {
    color: var(--admin-ink);
    container-type: inline-size;
    max-width: 70rem;
    margin-inline: auto;
  }

  ol {
    display: flex;
    gap: .5rem;
    align-items: center;
    margin: 0 0 1.5rem;
    padding: 0;
    list-style: none;
    color: var(--admin-muted);
    font-size: .875rem;
  }

  li[aria-current] {
    display: flex;
    align-items: center;
    gap: .5rem;
    color: var(--admin-ink);
    font-weight: 600;
  }

  svg {
    width: 1.125rem;
    height: 1.125rem;
    flex: none;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.7;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .breadcrumb svg, .hero svg {
    width: .9375rem;
    height: .9375rem;
  }

  .hero {
    position: relative;
    isolation: isolate;
    overflow: hidden;
    padding: clamp(1.125rem, 4cqi, 1.875rem);
    border: 1px solid var(--admin-accent-border);
    border-radius: var(--admin-radius-panel);
    background: radial-gradient(ellipse at right, var(--admin-accent-soft), transparent 75%), var(--admin-soft);
  }

  .hero::after {
    content: "";
    position: absolute;
    inset: 0 0 0 55%;
    z-index: -1;
    background: radial-gradient(var(--admin-accent) 1px, transparent 1px) 0 0 / 11px 11px;
    mask-image: linear-gradient(to right, transparent, var(--admin-ink));
    opacity: .24;
  }

  .hero h1 {
    font-size: clamp(2rem, 5cqi, 2.8rem);
    line-height: 1.08;
  }

  .eyebrow {
    margin: 0 0 .625rem;
    color: var(--admin-muted);
    font-size: .6875rem;
    font-weight: 700;
    letter-spacing: .14em;
    text-transform: uppercase;
  }

  .hero .eyebrow {
    display: flex;
    align-items: center;
    gap: .5rem;
    color: var(--admin-accent);
  }

  .settings-columns {
    display: grid;
    grid-template-columns: clamp(9rem, 22cqi, 12.75rem) minmax(0, 1fr);
    gap: clamp(1.25rem, 4cqi, 2.5rem);
    margin-top: 2rem;
  }

  .settings-nav {
    display: grid;
    align-content: start;
    gap: 1.25rem;
  }

  .settings-nav .eyebrow {
    margin-inline: .75rem;
  }

  .settings-nav a {
    display: flex;
    align-items: center;
    gap: .625rem;
    padding: .625rem .75rem;
    border-radius: var(--admin-radius);
    color: var(--admin-muted);
    text-decoration: none;
  }

  .settings-nav a:hover {
    background: var(--admin-hover);
    color: var(--admin-ink);
  }

  .settings-nav a[aria-current] {
    background: var(--admin-accent-soft);
    box-shadow: inset 3px 0 var(--admin-accent);
    color: var(--admin-accent);
    font-weight: 650;
  }

  @container (max-width: 38rem) {
    .settings-columns {
      grid-template-columns: minmax(0, 1fr);
      margin-top: 1.25rem;
    }

    .settings-nav {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: .5rem;
      border-bottom: 1px solid var(--admin-border);
      padding-bottom: .75rem;
    }
  }
</style>
