<script lang="ts">
  type AccountPictureProps = {
    label: string;
    picture: string | null;
  };

  let { label, picture }: AccountPictureProps = $props();

  const hasPicture = $derived(picture !== null && picture.trim().length > 0);
</script>

{#if hasPicture}
  <img class="account-picture" src={picture} alt="" referrerpolicy="no-referrer" />
{:else}
  <span class="account-picture-placeholder" aria-label={label} role="img">
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 12.25a4.25 4.25 0 1 0 0-8.5 4.25 4.25 0 0 0 0 8.5Zm0 2c-3.87 0-7 2.05-7 4.58 0 .78.64 1.42 1.42 1.42h11.16c.78 0 1.42-.64 1.42-1.42 0-2.53-3.13-4.58-7-4.58Z" />
    </svg>
  </span>
{/if}

<style>
  .account-picture,
  .account-picture-placeholder {
    border-radius: 999px;
    flex: 0 0 auto;
    height: var(--account-picture-size, 2.25rem);
    width: var(--account-picture-size, 2.25rem);
  }

  .account-picture {
    object-fit: cover;
  }

  .account-picture-placeholder {
    align-items: center;
    background: rgb(148 163 184 / 24%);
    color: currentColor;
    display: inline-flex;
    justify-content: center;
  }

  .account-picture-placeholder svg {
    fill: currentColor;
    height: 62%;
    opacity: 0.72;
    width: 62%;
  }
</style>
