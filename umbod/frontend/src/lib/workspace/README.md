# Workspace

**Module responsibility:** Shared dashboard and administration navigation and safe administration presentation resolution.

- `navigation.ts` defines Dashboard-first navigation, administrator links, the common home destination and accessible shell/account labels.
- `admin-access.ts` accepts the validated current-user port already implemented by the admin client. Only a successful read permits administrator navigation and exposes the validated account identity. Authentication, forbidden access and unavailable services/schema validation remain distinct fail-closed outcomes.
- `workspace-access-state.svelte.ts` owns the independent, initially checking access read started alongside catalogue loading on dashboard mount. Disposal discards late responses; no access request delays catalogue mounting.
- `workspace-access-state.test.ts` verifies pending access cannot block the catalogue or reveal privileged navigation.
- `admin-access.test.ts` tests presentation resolution through an injected in-memory current-user port.

Dashboard lookup failures or stalled requests do not block catalogue rendering. Confirmed identity replaces the existing account identity fallback.

See [ADR-005: One Workspace and Only Usable Controls](../../../../project/architecture-records/ADR-005-unified-workspace-and-usable-controls.md).

These presentation decisions do not grant authority: the existing admin layout and backend remain responsible for direct administration access.
