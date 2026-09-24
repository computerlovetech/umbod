<script lang="ts">
  type Props = {
    status: string;
  };

  let { status }: Props = $props();

  const normalizedStatus = $derived(status.toLowerCase());
  const displayStatus = $derived(normalizedStatus.charAt(0).toUpperCase() + normalizedStatus.slice(1));
  const tone = $derived(normalizedStatus === 'published' ? 'published' : normalizedStatus === 'draft' || normalizedStatus === 'unconfigured' ? 'draft' : 'neutral');
</script>

<span class={['publication-status', tone]}>{displayStatus}</span>

<style>
  .publication-status {
    border: 1px solid;
    border-radius: 999px;
    flex: 0 0 auto;
    font-size: 0.75rem;
    font-weight: 650;
    line-height: 1;
    padding: 0.35rem 0.55rem;
  }

  .published {
    background: #edf7ed;
    border-color: #d3e8d3;
    color: #2f6f3e;
  }

  .draft {
    background: #fff4e8;
    border-color: #f1d6b8;
    color: #9a5a18;
  }

  .neutral {
    background: #f1f1ef;
    border-color: #e2e2df;
    color: #787774;
  }
</style>
