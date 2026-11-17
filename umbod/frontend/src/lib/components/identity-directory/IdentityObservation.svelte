<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { identityDirectoryApi } from '#lib/identity-directory/api.js';
  import { browserObservationEnvironment } from '#lib/identity-directory/browser-environment.js';
  import { ObservationCoordinator } from '#lib/identity-directory/observation-coordinator.js';
  import type { IdentityObservation, ObservationEnvironment } from '#lib/identity-directory/port.js';

  let { observation = identityDirectoryApi().observations, environment = browserObservationEnvironment() }: {
    observation?: IdentityObservation;
    environment?: ObservationEnvironment;
  } = $props();
  const coordinator = new ObservationCoordinator(untrack(() => observation), untrack(() => environment));
  onMount(() => {
    coordinator.start();
    return coordinator.dispose;
  });
</script>

<svelte:window onfocus={coordinator.trigger} />
<svelte:document onvisibilitychange={coordinator.trigger} />
