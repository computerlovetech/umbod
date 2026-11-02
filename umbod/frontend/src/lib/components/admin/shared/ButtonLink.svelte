<script lang="ts">
  import type { ComponentProps, Snippet } from 'svelte';
  import type { HTMLAnchorAttributes } from 'svelte/elements';
  import type Button from './Button.svelte';
  import '$lib/styles/buttons.css';

  type Props = Omit<HTMLAnchorAttributes, 'children'> & Pick<ComponentProps<typeof Button>, 'variant' | 'size'> & {
    children: Snippet;
  };

  let {
    children,
    variant = 'primary',
    size = 'normal',
    class: className,
    ...attributes
  }: Props = $props();
</script>

<a {...attributes} class={["admin-shared-button", `admin-shared-button--${variant}`, `admin-shared-button--${size}`, className]}>
  {@render children()}
</a>
