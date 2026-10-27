# One Workspace and Only Usable Controls — supporting detail

Preserved from [ADR-005: One Workspace and Only Usable Controls](../ADR-005-unified-workspace-and-usable-controls.md). These details remain part of the accepted record; relocation does not change their authority or claim that implementation or verification is complete.

## Acceptance criteria

- Opening `/` leads directly to `/dashboard`, with no role chooser.
- Ordinary users see no administration navigation, including while access is being checked or when the check fails.
- Administrators see Dashboard and the administration destinations in the same workspace navigation.
- Navigating between Dashboard and administration preserves the workspace identity and Dashboard home destination.
- A failed administration check does not block the user's connector catalogue.
- Direct administration requests remain protected by backend authorization.
