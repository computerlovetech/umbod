<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import '$lib/styles/buttons.css';

  type Props = Omit<HTMLButtonAttributes, 'children'> & {
    children: Snippet;
    variant?: 'primary' | 'secondary' | 'danger' | 'quiet';
    size?: 'normal' | 'compact';
    iconOnly?: boolean;
    ref?: HTMLButtonElement;
  };

  let {
    children,
    variant = 'primary',
    size = 'normal',
    iconOnly = false,
    ref = $bindable(),
    type = 'button',
    class: className,
    ...attributes
  }: Props = $props();
</script>

<button {...attributes} bind:this={ref} {type} class={["admin-shared-button", `admin-shared-button--${variant}`, `admin-shared-button--${size}`, { 'admin-shared-button--icon': iconOnly }, className]}>
  {@render children()}
</button>
