# Personal connection presentation

**Module responsibility:** Clear owner-scoped connection status, a single contextual next step, and personal authorization actions without administration controls.

- `ConnectionCard.svelte` presents the current status, contextual recovery, a blocked-window sign-in fallback, optional connection details, and confirmed disconnect. Embedded cards keep secondary actions out of the detail panel; standalone cards provide their own menu.
- `ConnectionStatusBadge.svelte` combines text, an icon, and semantic colours for ready, attention, disabled, and pending states. The dashboard also uses its compact form in the connector list.
- `ConnectionActions.svelte` reuses the shared connector three-dot menu with keyboard navigation, focus restoration, and owner-scoped action guards. Dashboard menu actions select the affected connector so its progress or confirmation is visible.

`$lib/personal-connections/presentation.ts` and `state/access-view-state.svelte.ts` derive presentation from the public controller. Enablement, authorization presence, local health, and tool eligibility remain independent. Ready status is based on saved authorization and runtime availability, not an upstream connectivity probe. Uncertain outcomes require safe status inspection before further mutations.

Sign-in navigation belongs to the owner-lifetime controller, not the mounted card. Only an explicit sign-in action reserves and opens a provider tab; blocked or closed reservations retain the current attempt and a safe fallback link. Completion is checked manually. Rendering and status inspection never sign in, renew, or discover automatically.
