# Admin Overview Components

**Module responsibility:** Server-loaded administration dashboard presentation without local state or network access.

## Modules

- `AdminOverviewDashboard.svelte`: Four overview cards, linked connector-family breakdown, explicit unavailable warnings and conditional connector attention counts.
- `admin-overview-dashboard.test.ts`: SSR coverage for cards, zero counts, attention and partial availability.

The dashboard consumes `$lib/admin/overview/models.ts` contracts and existing admin theme tokens. The route retains `AdminShell` navigation. The breakdown has semantic headers and a labelled keyboard-focusable horizontal scroll region.
