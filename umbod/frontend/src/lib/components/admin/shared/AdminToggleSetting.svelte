<script lang="ts">
  import type { Snippet } from 'svelte';
  import AdminToggle from './AdminToggle.svelte';

  let { title, description, checked, disabled, onChange, metadata, children }: {
    title: string;
    description: string;
    checked: boolean;
    disabled: boolean;
    onChange: (checked: boolean) => void;
    metadata?: Snippet;
    children?: Snippet;
  } = $props();

  const id = $props.id();

  function change(event: Event): void {
    if (event.currentTarget instanceof HTMLInputElement) onChange(event.currentTarget.checked);
  }
</script>

<section class="setting" aria-labelledby={`${id}-title`}>
  <div class="row">
    <div class="copy">
      <h3 id={`${id}-title`}>{title}</h3>
      <p id={`${id}-description`}>{description}</p>
      {#if metadata}<div class="metadata">{@render metadata()}</div>{/if}
    </div>
    <div class="toggle">
      <AdminToggle {checked} {disabled} ariaLabel={title} ariaDescribedBy={`${id}-description`} onchange={change} />
      <span aria-hidden="true">{checked ? 'On' : 'Off'}</span>
    </div>
  </div>
  {#if children}<div class="details">{@render children()}</div>{/if}
</section>

<style>
  .setting { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 16px; }
  .row { align-items: flex-start; display: flex; gap: 1rem; justify-content: space-between; }
  .copy { min-width: 0; }
  h3 { font-size: 15px; margin: 0; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin: 0.375rem 0 0; }
  .metadata, .details { margin-top: 0.875rem; }
  .toggle { align-items: center; display: flex; flex-shrink: 0; gap: 0.5rem; font-size: 13px; }
</style>
