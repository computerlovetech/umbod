<script lang="ts">
  let { label }: { label: string } = $props();
</script>

<span class="kind-badge">{label}</span>

<style>
  .kind-badge { background: var(--admin-accent-soft); border: 1px solid var(--admin-accent-border); border-radius: 999px; color: var(--admin-accent); display: inline-block; font-size: .7rem; font-weight: 600; justify-self: start; line-height: 1.2; padding: .15rem .45rem; }
</style>
