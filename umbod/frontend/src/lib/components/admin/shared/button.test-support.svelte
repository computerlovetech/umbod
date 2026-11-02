<script lang="ts">
  import type { ComponentProps } from 'svelte';
  import Button from './Button.svelte';
  import ButtonLink from './ButtonLink.svelte';
  import LoadingButton from './LoadingButton.svelte';

  let {
    kind,
    buttonProps,
    loadingProps,
    linkProps,
    getRef,
    setRef
  }: {
    kind: 'button' | 'loading' | 'link';
    buttonProps: () => Omit<ComponentProps<typeof Button>, 'children'>;
    loadingProps: () => ComponentProps<typeof LoadingButton>;
    linkProps: () => Omit<ComponentProps<typeof ButtonLink>, 'children'>;
    getRef: () => HTMLButtonElement | undefined;
    setRef: (element: HTMLButtonElement | undefined) => void;
  } = $props();
</script>

{#if kind === 'button'}
  <Button {...buttonProps()} bind:ref={getRef, setRef}><span>Action</span></Button>
{:else if kind === 'loading'}
  <LoadingButton {...loadingProps()} bind:ref={getRef, setRef} />
{:else}
  <ButtonLink {...linkProps()}><span>Destination</span></ButtonLink>
{/if}
