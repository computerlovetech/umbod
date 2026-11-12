<script lang="ts">
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import DateTimeView from '$lib/components/shared/DateTimeView.svelte';
  import type { NodeSummary } from '$lib/files/domain/schemas';

  let { node, close, displayName }: { node: NodeSummary; close: () => void; displayName?: string } = $props();
  const id = $props.id();
</script>

<ModalShell title="Details" titleId={id + '-title'} {close} initialFocus={'button[aria-label="Close"]'} --modal-overflow="auto">
  <dl aria-label="Item details">
    <dt>Name</dt><dd>{displayName ?? node.name}</dd>
    <dt>Type</dt><dd>{node.kind === 'directory' ? 'Folder' : 'File'}</dd>
    <dt>Description</dt><dd>{node.metadata.attributes.description || 'Not specified'}</dd>
    {#if typeof node.metadata.content_type === 'string'}<dt>Content type</dt><dd>{node.metadata.content_type}</dd>{/if}
    <dt>Created</dt><dd><DateTimeView value={node.created_at} /></dd>
    <dt>Updated</dt><dd><DateTimeView value={node.updated_at} /></dd>
    <dt>Revision</dt><dd>{node.revision}</dd>
  </dl>
  <h3>Your permissions</h3>
  <dl aria-label="Your permissions">
    <dt>Discover</dt><dd>{node.permissions.can_discover ? 'Allowed' : 'Not allowed'}</dd>
    <dt>Read</dt><dd>{node.permissions.can_read ? 'Allowed' : 'Not allowed'}</dd>
    <dt>Write</dt><dd>{node.permissions.can_write ? 'Allowed' : 'Not allowed'}</dd>
    <dt>Delete</dt><dd>{node.permissions.can_delete ? 'Allowed' : 'Not allowed'}</dd>
    <dt>Share</dt><dd>{node.permissions.can_share ? 'Allowed' : 'Not allowed'}</dd>
  </dl>
</ModalShell>

<style>
  dl { display: grid; grid-template-columns: minmax(5rem, 8rem) minmax(0, 1fr); gap: 0.65rem 1rem; font-size: 0.9rem; }
  dt { color: var(--admin-muted); }
  dd { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
  h3 { margin-bottom: 0; font-size: 1rem; }
</style>
