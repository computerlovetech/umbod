<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { PromptCatalog } from '$lib/admin/capability-catalogs';
  import ToolSaveBar from '$lib/components/admin/connectors/ToolSaveBar.svelte';
  import AdminToggle from '$lib/components/admin/shared/AdminToggle.svelte';
  import CapabilityCatalogGrid from '$lib/components/admin/shared/CapabilityCatalogGrid.svelte';

  let {
    catalog,
    heading = 'Prompt catalog',
    emptyMessage = 'No prompts are available',
    embedded = false,
    activationEnabled,
    onActivationChange,
    dirty = false,
    pending = false,
    saveBarMessage,
    children
  }: {
    catalog: PromptCatalog;
    heading?: string;
    emptyMessage?: string;
    embedded?: boolean;
    activationEnabled?: (promptId: string) => boolean;
    onActivationChange?: (promptId: string, enabled: boolean) => void;
    dirty?: boolean;
    pending?: boolean;
    saveBarMessage?: string;
    children?: Snippet;
  } = $props();

  const interactive = $derived(Boolean(activationEnabled && onActivationChange));
  const message = $derived(
    saveBarMessage ??
      (pending ? 'Saving prompt changes' : dirty ? 'Unsaved prompt changes' : 'All prompt changes saved')
  );

  function inputChecked(event: Event): boolean {
    return event.currentTarget instanceof HTMLInputElement && event.currentTarget.checked;
  }
</script>

<section class="catalog" class:embedded aria-labelledby="prompt-catalog-title">
  <div class="catalog-heading">
    <h3 id="prompt-catalog-title">{heading}</h3>
    <span>{catalog.prompts.length}</span>
  </div>
  {#if interactive}
    <ToolSaveBar {message} {dirty} {pending}>
      {#if children}{@render children()}{/if}
    </ToolSaveBar>
  {/if}
  {#if catalog.prompts.length === 0}
    <p>{emptyMessage}</p>
  {:else}
    <CapabilityCatalogGrid>
      {#each catalog.prompts as prompt (prompt.name)}
        <li>
          <div class="item-heading">
            <h4>{prompt.name}</h4>
            {#if interactive && activationEnabled && onActivationChange}
              <AdminToggle
                checked={activationEnabled(prompt.name)}
                ariaLabel={`${prompt.name} activation`}
                disabled={pending}
                onchange={(event) => onActivationChange(prompt.name, inputChecked(event))}
              />
            {/if}
          </div>
          <p>{prompt.description}</p>
          {#if prompt.arguments.length > 0}
            <dl>
              {#each prompt.arguments as argument (argument.name)}
                <div><dt>{argument.name}{argument.required ? ' (required)' : ''}</dt><dd>{argument.description}</dd></div>
              {/each}
            </dl>
          {/if}
        </li>
      {/each}
    </CapabilityCatalogGrid>
  {/if}
</section>

<style>
  .catalog { border-top: 1px solid var(--admin-border); margin-top: 1.5rem; padding-top: 1rem; }
  .catalog.embedded { border-top: 0; margin-top: 0; padding-top: 0; }
  .catalog-heading, .item-heading { align-items: center; display: flex; gap: 0.5rem; }
  .catalog-heading { margin-bottom: 0.875rem; }
  .item-heading { justify-content: space-between; }
  .catalog-heading span { background: var(--admin-sidebar); border: 1px solid var(--admin-border); border-radius: 999px; color: var(--admin-muted); font-size: 0.75rem; font-weight: 650; padding: 0.1rem 0.45rem; }
  .catalog > p, li > p, dd { color: var(--admin-muted); }
  h3, h4 { color: var(--admin-ink); margin: 0; }
  h3 { font-size: 1rem; }
  h4 { font-size: 0.94rem; overflow-wrap: anywhere; }
  li { background: #fff; border: 1px solid var(--admin-border); border-radius: 10px; min-width: 0; padding: 1rem; }
  li > p, dl { margin: 0.55rem 0 0; }
  li > p, dd { font-size: 0.875rem; line-height: 1.5; overflow-wrap: anywhere; }
  dl { border-top: 1px solid var(--admin-border); display: grid; gap: 0.55rem; padding-top: 0.75rem; }
  dl div { display: grid; gap: 0.15rem; }
  dt { font-size: 0.8125rem; font-weight: 650; overflow-wrap: anywhere; }
  dd { margin: 0; }
</style>
