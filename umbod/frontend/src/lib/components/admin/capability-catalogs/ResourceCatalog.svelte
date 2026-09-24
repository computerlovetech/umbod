<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { ResourceCatalog } from '$lib/admin/capability-catalogs';
  import ToolSaveBar from '$lib/components/admin/connectors/ToolSaveBar.svelte';
  import AdminToggle from '$lib/components/admin/shared/AdminToggle.svelte';
  import CapabilityCatalogGrid from '$lib/components/admin/shared/CapabilityCatalogGrid.svelte';

  let {
    catalog,
    heading = 'Resource catalog',
    emptyMessage = 'No resources are available',
    embedded = false,
    activationEnabled,
    onActivationChange,
    dirty = false,
    pending = false,
    saveBarMessage,
    children
  }: {
    catalog: ResourceCatalog;
    heading?: string;
    emptyMessage?: string;
    embedded?: boolean;
    activationEnabled?: (resourceId: string, kind: 'resource' | 'resource_template') => boolean;
    onActivationChange?: (resourceId: string, kind: 'resource' | 'resource_template', enabled: boolean) => void;
    dirty?: boolean;
    pending?: boolean;
    saveBarMessage?: string;
    children?: Snippet;
  } = $props();

  const interactive = $derived(Boolean(activationEnabled && onActivationChange));
  const message = $derived(
    saveBarMessage ??
      (pending ? 'Saving resource changes' : dirty ? 'Unsaved resource changes' : 'All resource changes saved')
  );

  function inputChecked(event: Event): boolean {
    return event.currentTarget instanceof HTMLInputElement && event.currentTarget.checked;
  }

  function resourceId(resource: ResourceCatalog['resources'][number]): string {
    return resource.kind === 'resource' ? resource.uri : resource.uriTemplate;
  }
</script>

<section class="catalog" class:embedded aria-labelledby="resource-catalog-title">
  <div class="catalog-heading">
    <h3 id="resource-catalog-title">{heading}</h3>
    <span>{catalog.resources.length}</span>
  </div>
  {#if interactive}
    <ToolSaveBar {message} {dirty} {pending}>
      {#if children}{@render children()}{/if}
    </ToolSaveBar>
  {/if}
  {#if catalog.resources.length === 0}
    <p>{emptyMessage}</p>
  {:else}
    <CapabilityCatalogGrid>
      {#each catalog.resources as resource (`${resource.kind}:${resourceId(resource)}`)}
        <li>
          <div class="resource-heading">
            <div class="resource-title">
              <h4>{resource.name}</h4>
              <span>{resource.kind === 'resource' ? 'Resource' : 'Resource template'}</span>
            </div>
            {#if interactive && activationEnabled && onActivationChange}
              <AdminToggle
                checked={activationEnabled(resourceId(resource), resource.kind)}
                ariaLabel={`${resource.name} activation`}
                disabled={pending}
                onchange={(event) => onActivationChange(resourceId(resource), resource.kind, inputChecked(event))}
              />
            {/if}
          </div>
          <p>{resource.description}</p>
          <code>{resourceId(resource)}</code>
        </li>
      {/each}
    </CapabilityCatalogGrid>
  {/if}
</section>

<style>
  .catalog { border-top: 1px solid var(--admin-border); margin-top: 1.5rem; padding-top: 1rem; }
  .catalog.embedded { border-top: 0; margin-top: 0; padding-top: 0; }
  .catalog-heading, .resource-heading, .resource-title { align-items: center; display: flex; gap: 0.5rem; }
  .catalog-heading { margin-bottom: 0.875rem; }
  .resource-heading { align-items: flex-start; flex-wrap: wrap; justify-content: space-between; }
  .resource-title { align-items: flex-start; flex-wrap: wrap; }
  .catalog-heading span, .resource-title span { background: var(--admin-sidebar); border: 1px solid var(--admin-border); border-radius: 999px; color: var(--admin-muted); font-size: 0.75rem; font-weight: 650; padding: 0.1rem 0.45rem; }
  .catalog > p, li > p { color: var(--admin-muted); }
  h3, h4 { color: var(--admin-ink); margin: 0; }
  h3 { font-size: 1rem; }
  h4 { font-size: 0.94rem; overflow-wrap: anywhere; }
  li { background: #fff; border: 1px solid var(--admin-border); border-radius: 10px; min-width: 0; padding: 1rem; }
  li > p { font-size: 0.875rem; line-height: 1.5; margin: 0.55rem 0 0.75rem; overflow-wrap: anywhere; }
  code { background: var(--admin-sidebar); border: 1px solid var(--admin-border); border-radius: 6px; display: block; font-size: 0.75rem; line-height: 1.5; overflow-wrap: anywhere; padding: 0.4rem 0.55rem; }
</style>
