<script lang="ts">
  import { navigating } from '$app/state';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { logoutNavigation, type LogoutNavigation } from '$lib/admin/infrastructure/logout';
  import type { Snippet } from 'svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import AccountPicture from '$lib/components/header/AccountPicture.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import { WorkspaceShellState, type WorkspaceNavigationItem } from './workspace-shell-state.svelte';
  import { useWorkspaceNavigationHistory } from '$lib/workspace/navigation-history-context';
  import WorkspaceNavigationIcon from './WorkspaceNavigationIcon.svelte';

  type Props = {
    workspaceLabel: string;
    homeHref: string;
    navigationItems: readonly WorkspaceNavigationItem[];
    activeItem: string;
    accountIdentity?: HeaderAccountIdentityState;
    accountFallback?: string;
    sidebarLabel?: string;
    navigationLabel?: string;
    navigationDescription?: string;
    backLink?: { label: string; href: string };
    contentWidth?: 'default' | 'wide';
    contentLoading?: boolean;
    navigationScope?: string;
    children: Snippet;
    logout?: LogoutNavigation;
  };

  let {
    workspaceLabel, homeHref, navigationItems, activeItem,
    accountIdentity = { kind: 'hidden' }, accountFallback = 'Account',
    sidebarLabel = workspaceLabel + ' sidebar', navigationLabel = workspaceLabel + ' navigation',
    navigationDescription, backLink,
    contentWidth = 'default', contentLoading = false, navigationScope, children, logout = logoutNavigation
  }: Props = $props();

  const navigationHistory = useWorkspaceNavigationHistory();
  const state = new WorkspaceShellState(() => ({
    activeItem,
    navigationItems,
    destinationPath: navigating.to?.url.pathname ?? null,
    originPath: navigating.from?.url.pathname ?? null,
    navigationScope,
    hasBackLink: backLink !== undefined,
    sidebarTransition: navigationHistory?.transition ?? null
  }));
</script>

<div class="workspace-shell">
  <aside class="sidebar" aria-label={sidebarLabel}>
    <div class="sidebar-top">
      <a class="brand" href={homeHref}><img src="/umbod-logo.svg" alt="" width="40" height="40" /><span>Umbod</span></a>
      <div class={["sidebar-navigation", state.sidebarTransition === 'forward' && "enter-forward", state.sidebarTransition === 'backward' && "enter-backward"]}>
        {#if backLink}
          <a class="workspace-back" href={backLink.href}><span aria-hidden="true">←</span>{backLink.label}</a>
        {/if}
        <p class={["workspace", navigationDescription && "section-heading"]}>{workspaceLabel}</p>
        {#if navigationDescription}
          <p class="navigation-description">{navigationDescription}</p>
        {/if}

        <nav class="navigation" aria-label={navigationLabel}>
          {#each navigationItems as item (item.id)}
            <a class={["navigation-link", item.startsSection && "section-start", state.displayedActiveItem === item.id && "active"]} href={item.href} aria-current={state.displayedActiveItem === item.id ? 'page' : undefined}>
              {#if item.icon}<WorkspaceNavigationIcon name={item.icon} />{/if}
              {item.label}
            </a>
          {/each}
        </nav>
      </div>
    </div>

    <div class="account-block">
      {#if accountIdentity.kind === 'visible'}
        <div class="account-details">
          <AccountPicture picture={accountIdentity.picture} label="Current account picture" />
          <div class="account-text">
            <p class="account-name">{accountIdentity.name}</p>
            {#if accountIdentity.email !== null}
              <p class="account-email">{accountIdentity.email}</p>
            {/if}
          </div>
        </div>
      {:else}
        <p class="account-name">{accountFallback}</p>
      {/if}
      <div class="logout-action"><Button variant="secondary" disabled={state.loggingOut} onclick={() => state.logout(logout)} style="width: 100%">Log out</Button></div>
    </div>
  </aside>

  <section class="content-shell" aria-busy={contentLoading || state.navigationPending}>
    <div class={["content-loading", (contentLoading || state.navigationPending) && "active"]}>
      <DelayedSpinner active={contentLoading || state.navigationPending} label="Loading page" />
    </div>
    <div class={["content-width", contentWidth === 'wide' && "wide"]} inert={contentLoading || state.navigationPending}>
      {@render children()}
    </div>
  </section>
</div>

<style>
  .workspace-shell {
    background: var(--admin-canvas);
    color: var(--admin-ink);
    display: grid;
    grid-template-columns: 232px minmax(0, 1fr);
    height: 100vh;
    overflow: hidden;
  }

  .sidebar {
    background: var(--admin-sidebar);
    border-right: 1px solid var(--admin-border);
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 100vh;
    min-height: 0;
    min-width: 0;
    padding: 26px 16px 18px;
  }

  .brand {
    align-items: center;
    border-radius: var(--admin-radius);
    color: var(--admin-ink);
    display: flex;
    gap: 8px;
    font-size: 24px;
    font-weight: 650;
    letter-spacing: -0.06em;
    line-height: 1.3;
    padding: 0 4px;
    text-decoration: none;
  }

  .brand:hover,
  .workspace-back:hover,
  .navigation-link:hover {
    background: var(--admin-accent-soft);
  }

  .workspace {
    color: var(--admin-muted);
    font-family: var(--admin-mono);
    font-size: 10px;
    letter-spacing: 0.08em;
    line-height: 1.4;
    margin: 18px 12px 12px;
    text-transform: uppercase;
  }

  .sidebar-top {
    min-height: 0;
    overflow: auto;
    padding-bottom: 18px;
  }

  .sidebar-navigation {
    padding-top: 1px;
  }

  .enter-forward {
    animation: sidebar-forward 300ms cubic-bezier(0.2, 0, 0, 1);
  }

  .enter-backward {
    animation: sidebar-backward 300ms cubic-bezier(0.2, 0, 0, 1);
  }

  @keyframes sidebar-forward {
    from { opacity: 0; transform: translateX(10px); }
    to { opacity: 1; transform: translateX(0); }
  }

  @keyframes sidebar-backward {
    from { opacity: 0; transform: translateX(-10px); }
    to { opacity: 1; transform: translateX(0); }
  }

  .workspace-back {
    align-items: center;
    border-radius: var(--admin-radius);
    color: var(--admin-muted);
    display: flex;
    font-size: 12px;
    gap: 8px;
    margin: 22px 0;
    padding: 8px 10px;
    text-decoration: none;
  }

  .workspace.section-heading {
    color: var(--admin-ink);
    font-family: inherit;
    font-size: 17px;
    font-weight: 650;
    letter-spacing: -0.02em;
    margin: 0 12px 7px;
    text-transform: none;
  }

  .navigation-description {
    color: var(--admin-muted);
    font-size: 11px;
    line-height: 1.6;
    margin: 0 12px 23px;
  }

  .navigation {
    display: grid;
    gap: 4px;
  }

  .navigation-link {
    align-items: center;
    display: flex;
    gap: 11px;
    border-radius: var(--admin-radius);
    color: var(--admin-muted);
    font-size: 14px;
    line-height: 1.35;
    padding: 10px 12px;
    text-decoration: none;
  }

  .navigation-link.section-start {
    margin-top: 24px;
    position: relative;
  }

  .section-start::before {
    background: var(--admin-border);
    content: '';
    height: 1px;
    left: 10px;
    position: absolute;
    right: 10px;
    top: -14px;
  }

  .navigation-link.active {
    background: var(--admin-accent-soft);
    color: var(--admin-accent);
    box-shadow: inset 2px 0 0 var(--admin-accent);
    font-weight: 600;
  }

  .account-block {
    flex-shrink: 0;
    border-top: 1px solid var(--admin-border);
    padding: 12px 8px 0;
  }

  .logout-action { margin-top: 12px; }

  .account-details {
    --account-picture-size: 28px;
    align-items: center;
    display: flex;
    gap: 8px;
    min-width: 0;
  }

  .account-text {
    min-width: 0;
  }

  .account-name,
  .account-email {
    line-height: 1.35;
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .account-name {
    color: var(--admin-ink);
    font-size: 13px;
    font-weight: 600;
  }

  .account-email {
    color: var(--admin-muted);
    font-size: 12px;
    margin-top: 2px;
  }

  .content-shell {
    background: var(--admin-canvas);
    box-sizing: border-box;
    min-height: 0;
    min-width: 0;
    overflow: auto;
    position: relative;
  }

  .content-loading {
    align-items: center;
    background: var(--admin-loading-bg);
    display: flex;
    inset: 0;
    justify-content: center;
    opacity: 0;
    pointer-events: none;
    position: absolute;
    transition: opacity 120ms ease-out;
    visibility: hidden;
    z-index: 2;
  }

  .content-loading.active {
    opacity: 1;
    pointer-events: auto;
    visibility: visible;
  }

  .content-width {
    box-sizing: border-box;
    container-type: inline-size;
    max-width: 860px;
    padding: 48px clamp(24px, 4vw, 56px);
    width: 100%;
  }

  .content-width.wide {
    max-width: 1440px;
  }

  @media (prefers-reduced-motion: reduce) {
    .enter-forward,
    .enter-backward {
      animation: none;
    }
  }

  @media (max-width: 720px) {
    .workspace-shell {
      grid-template-columns: minmax(0, 1fr);
      height: auto;
      min-height: 100vh;
      overflow: visible;
    }

    .sidebar {
      height: auto;
      min-height: auto;
      padding: 12px;
    }

    .content-shell {
      overflow: visible;
    }

    .account-block {
      margin-top: 14px;
    }

    .content-width {
      padding: 32px 24px;
    }
  }
</style>
