# ADR-005: One Workspace and Only Usable Controls

- **Status:** Accepted
- **Date:** 2026-10-23
- **Decision owners:** Product / UX
- **Scope:** Umbod web application

## Context

A landing page that asks users to choose between Dashboard and Administration makes them interpret internal roles before starting work. Showing administration destinations to people without access creates avoidable dead ends. Separate navigation also makes the same product feel like two applications.

## Decision

Umbod presents one workspace. The root URL opens Dashboard directly for both ordinary users and administrators. The brand link always returns to Dashboard, and workspace structure, navigation, and account controls remain consistent across user and administration pages.

Only show pages, tabs, components, and actions that the current user is authorized and eligible to use. Hide unavailable capabilities instead of offering disabled role-restricted controls or links that end in an access-denied page. Apply this rule to new features and when changing existing UI.

Administrators see additional administration destinations in the same navigation. Ordinary users see Dashboard without administration links. Do not infer access from names, email addresses, or whether account details are visible.

For this change, the existing administrator API boundary determines administration access: a validated successful current-user response grants administration navigation. The backend currently provides one administration boundary, not separate page or tab permissions. If finer permissions become available, filter each destination and action using those explicit permissions.

Until access is confirmed, privileged controls stay hidden. Resolve administration access independently of Dashboard loading so that even a stalled access check cannot delay the connector catalogue. Denial, expired authentication, and failed access checks remain distinct states; a failed check never grants access or prevents independently available Dashboard features from loading. Recoverable loading errors and their retry actions may remain visible: temporary service failure is not a permission decision. A control may also be temporarily disabled during an operation to prevent duplicate submission.

Visibility is a usability rule, not a security mechanism. Backend authorization remains mandatory for every protected operation. Direct URLs, bookmarks, and access revoked after navigation must still receive safe authentication or access-denied handling without exposing protected content.

## Acceptance criteria

- Opening `/` leads directly to `/dashboard`, with no role chooser.
- Ordinary users see no administration navigation, including while access is being checked or when the check fails.
- Administrators see Dashboard and the administration destinations in the same workspace navigation.
- Navigating between Dashboard and administration preserves the workspace identity and Dashboard home destination.
- A failed administration check does not block the user's connector catalogue.
- Direct administration requests remain protected by backend authorization.

## Consequences

- Users can start working without understanding administrator roles.
- Navigation reflects usable capabilities rather than advertising inaccessible features.
- Future UI changes must account for access and eligibility before rendering controls.
- Access-state changes and direct navigation still require defensive handling; hidden links alone never establish authorization.
- The frontend currently checks the existing administrator current-user endpoint. A dedicated capability contract can replace that check when the backend exposes one without changing the UX rule.
