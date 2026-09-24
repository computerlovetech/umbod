<script lang="ts">
  import { navigating } from '$app/state';
  import type { Snippet } from 'svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import AccountPicture from '$lib/components/header/AccountPicture.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';

  type AdminShellActiveItem =
    | 'overview'
    | 'connectors'
    | 'groupPermissions'
    | 'mcpSetup'
    | 'instanceConfiguration';

  type AdminShellProps = {
    activeItem: AdminShellActiveItem;
    accountIdentity: HeaderAccountIdentityState;
    contentWidth?: 'default' | 'wide';
    children: Snippet;
  };

  let { activeItem, accountIdentity, contentWidth = 'default', children }: AdminShellProps = $props();

  const navigationItems: { id: AdminShellActiveItem; label: string; href: string }[] = [
    { id: 'overview', label: 'Overview', href: '/admin' },
    { id: 'connectors', label: 'Connectors', href: '/admin/connectors' },
    { id: 'groupPermissions', label: 'Group permissions', href: '/admin/group-permissions' },
    { id: 'mcpSetup', label: 'MCP setup guide', href: '/admin/mcp-setup' },
    {
      id: 'instanceConfiguration',
      label: 'Configuration',
      href: '/admin/instance-configuration'
    }
  ];
  const pendingNavigationItem = $derived(
    navigating.to !== null && navigating.to.url.pathname !== navigating.from?.url.pathname
      ? navigationItems.find((item) => item.href === navigating.to?.url.pathname && item.id !== activeItem)
      : undefined
  );
  const displayedActiveItem = $derived(pendingNavigationItem?.id ?? activeItem);
</script>

<div class="admin-shell">
  <aside class="sidebar" aria-label="Admin sidebar">
    <div class="sidebar-top">
      <a class="brand" href="/admin">Umbod</a>
      <p class="workspace">Administration</p>

      <nav class="navigation" aria-label="Admin navigation">
        {#each navigationItems as item (item.id)}
          <a class={["navigation-link", displayedActiveItem === item.id && "active"]} href={item.href} aria-current={displayedActiveItem === item.id ? 'page' : undefined}>
            {item.label}
          </a>
        {/each}
      </nav>
    </div>

    <div class="account-block">
      {#if accountIdentity.kind === 'visible'}
        <div class="account-details">
          <AccountPicture picture={accountIdentity.picture} label="Current account picture" />
          <div class="account-text">
            <p class="account-name">{accountIdentity.name}</p>
            <p class="account-email">{accountIdentity.email}</p>
          </div>
        </div>
      {:else}
        <p class="account-name">Admin area</p>
      {/if}
    </div>
  </aside>

  <section class="content-shell" aria-busy={pendingNavigationItem !== undefined}>
    <div class:active={pendingNavigationItem !== undefined} class="content-loading">
      <DelayedSpinner active={pendingNavigationItem !== undefined} label="Loading page" />
    </div>
    <div class:wide={contentWidth === 'wide'} class="content-width" inert={pendingNavigationItem !== undefined}>
      {@render children()}
    </div>
  </section>
</div>

<style>
  .admin-shell {
    background: var(--admin-canvas);
    color: var(--admin-ink);
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr);
    height: 100vh;
    overflow: hidden;
  }

  .sidebar {
    background:
      radial-gradient(circle at 0 0, var(--admin-accent-soft), transparent 13rem),
      var(--admin-sidebar);
    border-right: 1px solid var(--admin-border);
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 100vh;
    min-height: 0;
    padding: 18px 12px;
  }

  .brand {
    border-radius: 6px;
    color: var(--admin-ink);
    display: block;
    font-size: 15px;
    font-weight: 650;
    line-height: 1.3;
    padding: 7px 8px;
    text-decoration: none;
  }

  .brand:hover,
  .navigation-link:hover {
    background: var(--admin-accent-soft);
  }

  .workspace {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.4;
    margin: 2px 8px 18px;
  }

  .navigation {
    display: grid;
    gap: 2px;
  }

  .navigation-link {
    border-radius: 6px;
    color: var(--admin-ink);
    font-size: 14px;
    line-height: 1.35;
    padding: 7px 8px;
    text-decoration: none;
  }

  .navigation-link.active {
    background: linear-gradient(90deg, var(--admin-accent-soft), var(--admin-border));
    box-shadow: inset 3px 0 0 var(--admin-accent);
    font-weight: 600;
  }

  .account-block {
    border-top: 1px solid var(--admin-border);
    padding: 12px 8px 0;
  }

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
    background:
      radial-gradient(circle at 100% 0, rgb(147 197 253 / 8%), transparent 18rem),
      var(--admin-canvas);
    box-sizing: border-box;
    min-height: 0;
    overflow: auto;
    position: relative;
  }

  .content-loading {
    align-items: center;
    background: rgb(235 235 232 / 78%);
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
    max-width: 860px;
    padding: 52px 60px;
    width: 100%;
  }

  .content-width.wide {
    max-width: 1440px;
  }

  @media (max-width: 720px) {
    .admin-shell {
      grid-template-columns: 1fr;
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
