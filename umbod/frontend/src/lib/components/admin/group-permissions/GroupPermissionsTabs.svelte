<script lang="ts">
  import SubpageNavigation from '#lib/components/shared/workspace/SubpageNavigation.svelte';

  let { activeTab }: { activeTab: 'connectors' | 'filesystem' } = $props();

  const tabs = [
    { id: 'connectors', label: 'Connectors', href: '/admin/group-permissions/connectors' },
    { id: 'filesystem', label: 'Filesystem', href: '/admin/group-permissions/filesystem' }
  ] as const;
</script>

<SubpageNavigation links={tabs} activeId={activeTab} label="Group permission type" />
