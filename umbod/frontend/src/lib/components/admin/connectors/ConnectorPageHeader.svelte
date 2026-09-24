<script lang="ts">
  type Props = {
    title: string;
    lede: string;
    addLabel: string;
    onadd: (trigger: HTMLButtonElement) => void;
  };

  let { title, lede, addLabel, onadd }: Props = $props();
</script>

<div class="connector-page-header">
  <p class="admin-eyebrow">Umbod</p>
  <div class="connector-page-heading">
    <h1 class="admin-title">{title}</h1>
    <button class="add" type="button" aria-label={addLabel} onclick={(event) => onadd(event.currentTarget)}>+</button>
  </div>
  <p class="admin-lede">{lede}</p>
</div>

<style>
  .add {
    align-items: center;
    background: #37352f;
    border: 0;
    border-radius: 50%;
    color: white;
    cursor: pointer;
    display: inline-flex;
    font-size: 1.25rem;
    height: 2rem;
    justify-content: center;
    min-width: 2rem;
    width: 2rem;
  }

  .add:focus-visible {
    outline: 3px solid rgb(47 111 235 / 24%);
    outline-offset: 2px;
  }

  @media (max-width: 600px) {
    .connector-page-heading {
      align-items: flex-start;
    }
  }
</style>
