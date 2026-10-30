<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { identityDirectoryApi } from '$lib/identity-directory/api';
  import { browserObservationEnvironment } from '$lib/identity-directory/browser-environment';
  import { ObservationCoordinator } from '$lib/identity-directory/observation-coordinator';
  import type { IdentityObservation, ObservationEnvironment } from '$lib/identity-directory/port';

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
