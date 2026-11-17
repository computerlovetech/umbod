<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import type { CatalogueGroup } from '#lib/admin/groups/domain/schemas.js';
  import type { GroupCatalogue } from '#lib/admin/groups/port.js';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import { identityDirectoryApi } from '#lib/identity-directory/api.js';
  import type { IdentityGroupDirectory } from '#lib/identity-directory/port.js';
  import GroupsManager from './GroupsManager.svelte';
  import { GroupsState } from './groups-state.svelte';
  let { groups, catalogue = adminApi().groups, directory = identityDirectoryApi().groups }: { groups: CatalogueGroup[]; catalogue?: GroupCatalogue; directory?: IdentityGroupDirectory } = $props();
  const state = new GroupsState(untrack(() => catalogue), untrack(() => groups), untrack(() => directory));
  onDestroy(state.dispose);
</script>

<GroupsManager {state} />
