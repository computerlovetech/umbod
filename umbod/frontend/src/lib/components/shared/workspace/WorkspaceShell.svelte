<script lang="ts">
  import { navigating } from '$app/state';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import type { LogoutNavigation } from '#lib/admin/infrastructure/logout.js';
  import type { Snippet } from 'svelte';
  import DelayedSpinner from '#lib/components/admin/shared/DelayedSpinner.svelte';
  import AccountPicture from '#lib/components/header/AccountPicture.svelte';
  import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
  import ActionMenu from '../ActionMenu.svelte';
  import { WorkspaceShellState, type AccountMenuLocation, type WorkspaceNavigationItem } from './workspace-shell-state.svelte';
  import type { WorkspaceAccountLink } from '#lib/workspace/navigation.js';
  import { useWorkspaceNavigationHistory } from '#lib/workspace/navigation-history-context.js';
  import { SidebarPreference, useSidebarPreference } from '#lib/workspace/sidebar-preference.svelte.js';
  import WorkspaceNavigationIcon from './WorkspaceNavigationIcon.svelte';
  import { attachMobileNavigation } from './mobile-navigation';
  import '#lib/styles/mobile-navigation.css';

  type Props = {
    workspaceLabel: string;
    homeHref: string;
    navigationItems: readonly WorkspaceNavigationItem[];
    activeItem: string | undefined;
    accountLinks?: readonly WorkspaceAccountLink[];
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
    accountIdentity = { kind: 'hidden' }, accountFallback = 'Account', accountLinks = [],
    sidebarLabel = workspaceLabel + ' sidebar', navigationLabel = workspaceLabel + ' navigation',
    navigationDescription, backLink,
    contentWidth = 'default', contentLoading = false, navigationScope, children, logout
  }: Props = $props();

  const sidebarId = $props.id();
  const sidebarPreference = useSidebarPreference() ?? new SidebarPreference();
  const sidebarToggleLabel = $derived(sidebarPreference.expanded ? 'Collapse sidebar' : 'Expand sidebar');
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

  function attachSidebar(panel: HTMLElement): (() => void) | undefined {
    return attachMobileNavigation(panel, state.closeAccountMenu);
  }
</script>

{#snippet accountDetails()}
  <span class="account-details">
    {#if accountIdentity.kind === 'visible'}
      <AccountPicture picture={accountIdentity.picture} label="Current account picture" />
      <span class="account-text sidebar-detail">
        <span class="account-name">{accountIdentity.name}</span>
        {#if accountIdentity.email !== null}
          <span class="account-email">{accountIdentity.email}</span>
        {/if}
      </span>
    {:else}
      <span class="account-fallback-picture" aria-hidden="true"><AccountPicture picture={null} label="Account picture" /></span>
      <span class="account-name sidebar-detail">{accountFallback}</span>
    {/if}
  </span>
{/snippet}

{#snippet accountMenu(location: AccountMenuLocation)}
  {#if accountLinks.length > 0 || logout}
    <ActionMenu
      label={accountIdentity.kind === 'visible' ? `${accountIdentity.name} account menu` : 'Account menu'}
      appearance="surface"
      align={location === 'mobile' ? 'end' : 'start'}
      open={state.accountMenuOpen(location)}
      onopenchange={(open) => state.setAccountMenuOpen(location, open)}
      --action-menu-min-width="12.5rem"
    >
      {#snippet trigger()}
        {@render accountDetails()}
        <svg class="account-chevron" aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m8 9 4-4 4 4m-8 6 4 4 4-4" /></svg>
      {/snippet}
      {#snippet menu()}
        <div class="account-menu-heading" aria-hidden="true">Your account</div>
        {#each accountLinks as link (link.href)}
          <a role="menuitem" tabindex="-1" href={link.href} onclick={() => state.setAccountMenuOpen(location, false)}>
            <span class="account-menu-item"><WorkspaceNavigationIcon name={link.icon} />{link.label}</span>
          </a>
        {/each}
        {#if logout}
          <div class={accountLinks.length > 0 ? 'account-menu-divider' : undefined}>
            <button type="button" role="menuitem" tabindex="-1" disabled={state.loggingOut} onclick={() => logout && state.logout(logout)}>
              <span class="account-menu-item logout-item">
                <svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="m10 17 5-5-5-5m5 5H3m10-8h7v16h-7" /></svg>
                Log out
              </span>
            </button>
          </div>
        {/if}
      {/snippet}
    </ActionMenu>
  {:else}
    {@render accountDetails()}
  {/if}
{/snippet}

<div class={['workspace-shell', !sidebarPreference.expanded && 'sidebar-collapsed']}>
  <div class="mobile-navigation-trigger mobile-workspace-bar">
    <Button variant="quiet" iconOnly aria-label="Open workspace menu" popovertarget={sidebarId}>
      <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
    </Button>
    <span aria-hidden="true">Umbod</span>
    <div class="mobile-account">{@render accountMenu('mobile')}</div>
  </div>
  <aside class="sidebar mobile-navigation-panel" id={sidebarId} aria-label={sidebarLabel} {@attach attachSidebar}>
    <div class="mobile-navigation-close">
      <Button variant="quiet" iconOnly aria-label="Close workspace menu" popovertarget={sidebarId} popovertargetaction="hide">
        <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </Button>
    </div>
    <div class="sidebar-top">
      <a class="brand" href={homeHref} title="Umbod"><img src="/umbod-logo.svg" alt="" width="40" height="40" /><span class="sidebar-detail sidebar-label">Umbod</span></a>
      <div class={["sidebar-navigation", state.sidebarTransition === 'forward' && "enter-forward", state.sidebarTransition === 'backward' && "enter-backward"]}>
        {#if backLink}
          <a class="workspace-back" href={backLink.href} title={backLink.label}><span class="back-arrow" aria-hidden="true">←</span><svg class="back-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12H4m7-7-7 7 7 7" /></svg><span class="sidebar-detail sidebar-label">{backLink.label}</span></a>
        {/if}
        <p class={["workspace", navigationDescription && "section-heading"]}>{workspaceLabel}</p>
        {#if navigationDescription}
          <p class="navigation-description">{navigationDescription}</p>
        {/if}

        <nav class="navigation" aria-label={navigationLabel}>
          {#each navigationItems as item (item.id)}
            <a class={["navigation-link", item.startsSection && "section-start", state.displayedActiveItem === item.id && "active"]} href={item.href} title={item.label} aria-current={state.displayedActiveItem === item.id ? 'page' : undefined}>
              {#if item.icon}
                <WorkspaceNavigationIcon name={item.icon} />
              {:else}
                <svg class="navigation-fallback" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="5" y="5" width="14" height="14" rx="2" /><path d="M8 10h8m-8 4h5" /></svg>
              {/if}
              <span class="sidebar-detail sidebar-label">{item.label}</span>
            </a>
          {/each}
        </nav>
      </div>
    </div>

    <div class="account-block">{@render accountMenu('sidebar')}</div>
  </aside>

  <section class="content-shell" aria-busy={contentLoading || state.navigationPending}>
    <div class="desktop-sidebar-control">
      <Button variant="quiet" iconOnly aria-label={sidebarToggleLabel} title={sidebarToggleLabel} aria-expanded={sidebarPreference.expanded} aria-controls={sidebarId} onclick={sidebarPreference.toggle}>
        <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></svg>
      </Button>
    </div>
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

  .brand img {
    flex: none;
  }

  .back-icon,
  .navigation-fallback {
    flex: none;
    height: 17px;
    width: 17px;
  }

  .desktop-sidebar-control,
  .account-fallback-picture,
  .back-icon,
  .navigation-fallback {
    display: none;
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
    padding-top: 12px;
  }

  .account-details {
    --account-picture-size: 30px;
    align-items: center;
    display: flex;
    flex: 1;
    gap: 8px;
    min-width: 0;
  }

  .account-text {
    min-width: 0;
  }

  .account-name,
  .account-email {
    display: block;
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

  .account-chevron {
    flex: none;
    margin-left: 6px;
  }

  .account-menu-heading {
    color: var(--admin-muted);
    font-family: var(--admin-mono);
    font-size: 10px;
    letter-spacing: 0.08em;
    padding: 0.5rem 0.6rem 0.25rem;
    text-transform: uppercase;
  }

  .account-menu-item {
    align-items: center;
    display: flex;
    gap: 8px;
  }

  .logout-item {
    color: var(--admin-danger);
  }

  .account-menu-divider {
    border-top: 1px solid var(--admin-border);
    margin-top: 4px;
    padding-top: 4px;
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

  @media (width > 720px) {
    .workspace-shell {
      --content-gutter: clamp(24px, 4vw, 56px);
      --sidebar-control-height: 48px;
    }

    .workspace-shell.sidebar-collapsed {
      grid-template-columns: 64px minmax(0, 1fr);
    }

    .content-shell {
      scroll-padding-top: var(--sidebar-control-height);
    }

    .desktop-sidebar-control {
      background: var(--admin-canvas);
      box-sizing: border-box;
      display: block;
      height: var(--sidebar-control-height);
      padding: 6px var(--content-gutter) 0;
      position: sticky;
      top: 0;
      z-index: 3;
    }

    .content-width {
      padding-top: 0;
      padding-inline: var(--content-gutter);
    }

    .sidebar-top {
      padding-inline: 3px;
      scrollbar-width: thin;
    }

    .sidebar-label {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .account-chevron {
      flex-shrink: 1;
    }

    .sidebar-collapsed .sidebar {
      padding-inline: 7px;
    }

    .sidebar-collapsed :is(.brand, .workspace-back, .navigation-link, .account-details) {
      gap: 0;
      justify-content: center;
    }

    .sidebar-collapsed .brand {
      padding-inline: 0;
    }

    .sidebar-collapsed :is(.workspace-back, .navigation-link) {
      min-height: 39px;
      box-sizing: border-box;
      padding-inline: 0;
    }

    .sidebar-collapsed .sidebar-detail {
      clip-path: inset(50%);
      height: 1px;
      opacity: 0;
      overflow: hidden;
      position: absolute;
      white-space: nowrap;
      width: 1px;
    }

    .sidebar-collapsed :is(.workspace, .navigation-description, .account-chevron, .back-arrow) {
      display: none;
    }

    .sidebar-collapsed .sidebar-navigation {
      padding-top: 18px;
    }

    .sidebar-collapsed :is(.back-icon, .navigation-fallback, .account-block .account-fallback-picture) {
      display: inline-flex;
    }
  }

  @media (width > 720px) and (prefers-reduced-motion: no-preference) {
    .workspace-shell {
      transition: grid-template-columns 190ms cubic-bezier(.2, .75, .25, 1);
    }

    .sidebar {
      transition: padding-inline 190ms cubic-bezier(.2, .75, .25, 1);
    }

    .sidebar-detail {
      transition: opacity 120ms ease-out 55ms;
    }

    .sidebar-collapsed .sidebar-detail {
      transition: none;
    }
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
      grid-template-rows: auto 1fr;
      overflow: visible;
    }

    .mobile-workspace-bar {
      align-items: center;
      gap: 0.5rem;
      padding: 4px 12px;
      background: var(--admin-sidebar);
      border-bottom: 1px solid var(--admin-border);
      font-weight: 650;
    }

    .sidebar {
      min-height: 0;
      padding: 12px;
    }

    .sidebar-top {
      flex: 1;
    }

    .content-shell {
      overflow: visible;
    }

    .sidebar:global([popover]) .account-block,
    .mobile-account .account-email {
      display: none;
    }

    .mobile-account {
      margin-left: auto;
      min-width: 0;
    }

    .mobile-account .account-details {
      --account-picture-size: 24px;
    }

    .content-width {
      padding: 32px 24px;
    }
  }
</style>
