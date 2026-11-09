<script lang="ts">
  import type { NodeSummary } from '$lib/files/domain/schemas';
  import { permissionLabel } from './permission-label';
  let { permissions }: { permissions: NodeSummary['permissions'] } = $props();
</script>

<span class="permission-badge">{permissionLabel(permissions)}</span>

<style>
  .permission-badge { display: inline-block; flex-shrink: 0; border: 1px solid var(--admin-border); border-radius: 1rem; padding: 0.1rem 0.45rem; color: var(--admin-muted); font-size: 0.7rem; font-weight: 400; line-height: 1.4; white-space: nowrap; }
</style>
