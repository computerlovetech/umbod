<script lang="ts">
  import '#lib/styles/form-fields.css';
  import type { HTMLTextareaAttributes } from 'svelte/elements';

  let { id, label, value, ...attributes }: Omit<HTMLTextareaAttributes, 'id' | 'value' | 'children'> & {
    id: string;
    label: string;
    value: string;
  } = $props();
</script>

<div class="form-field">
  <label class="form-field-label" for={id}>{label}</label>
  <textarea {...attributes} class={['form-control', attributes.class]} {id} {value}></textarea>
</div>
