<script lang="ts">
  import DashboardContainer from './DashboardContainer.svelte';
  import DashboardRow from './DashboardRow.svelte';
  import DashboardColumn from './DashboardColumn.svelte';
  import DashboardPanel from './DashboardPanel.svelte';

  let { showActions, showFooter, refresh }: { showActions: boolean; showFooter: boolean; refresh: () => void } = $props();
</script>

{#snippet toolbar()}<button onclick={refresh}>Refresh dashboard</button>{/snippet}
{#snippet timestamp()}<time datetime="2026-11-30T12:00:00Z">Updated at noon</time>{/snippet}

<DashboardContainer title="Service health" actions={showActions ? toolbar : undefined} footer={showFooter ? timestamp : undefined}>
  <DashboardRow>
    <DashboardColumn span={7}>
      <DashboardPanel title="Daily activity" metadata="UTC">
        {#snippet actions()}<button onclick={refresh}>Refresh activity</button>{/snippet}
        <p>Activity visualization</p>
      </DashboardPanel>
    </DashboardColumn>
    <DashboardColumn span={5}>
      <DashboardPanel title="Outcomes"><p>Outcome visualization</p></DashboardPanel>
    </DashboardColumn>
  </DashboardRow>
  <DashboardRow>
    <DashboardColumn span={12}><DashboardPanel title="Operation mix"><p>Mix visualization</p></DashboardPanel></DashboardColumn>
  </DashboardRow>
</DashboardContainer>
