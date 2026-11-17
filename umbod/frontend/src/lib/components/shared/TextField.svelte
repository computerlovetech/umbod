<script lang="ts">
  import '#lib/styles/form-fields.css';
  import type { HTMLInputAttributes } from 'svelte/elements';

  let { id, label, value, ...attributes }: Omit<HTMLInputAttributes, 'id' | 'type' | 'value' | 'children'> & {
    id: string;
    label: string;
    value: string;
  } = $props();
</script>

<div class="form-field">
  <label class="form-field-label" for={id}>{label}</label>
  <input {...attributes} class={["form-control", attributes.class]} {id} type="text" {value} />
</div>

