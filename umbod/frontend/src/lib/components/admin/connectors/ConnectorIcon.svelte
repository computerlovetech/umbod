<script lang="ts">
  import { connectorInitials } from './connector-icon';

  let { label, dataUrl, size = 'small' }: { label: string; dataUrl?: string; size?: 'small' | 'medium' | 'large' } = $props();
</script>

<span class={`connector-icon ${size}`} aria-hidden="true">
  {#if dataUrl}
    <img src={dataUrl} alt="" />
  {:else}
    {connectorInitials(label)}
  {/if}
</span>

<style>
  .connector-icon { align-items: center; background: #37352f; border-radius: 50%; color: #fff; display: inline-flex; flex: 0 0 auto; font-size: 8px; font-weight: 700; height: 20px; justify-content: center; letter-spacing: -.02em; overflow: hidden; width: 20px; }
  .connector-icon.medium { font-size: 12px; height: 36px; width: 36px; }
  .connector-icon.large { font-size: 14px; height: 44px; width: 44px; }
  img { display: block; height: 100%; object-fit: contain; width: 100%; }
</style>
