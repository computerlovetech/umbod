# User dashboard components

**Module responsibility:** Single-page user dashboard presentation outside administration.

- `Dashboard.svelte` composes the shared workspace shell using `$lib/workspace/` navigation and independently resolved administration access (hidden while checking), user-scoped catalogue, personal controls and compact MCP client setup. Mounting and disposal belong to the dashboard controller; focus and visibility events revalidate reads only.
- `ConnectorCard.svelte` supplies the common summary and inline detail structure for all connector kinds and both MCP ownership modes. Optional personal actions appear before read-only capabilities. Capability descriptions expand individually without invoking tools.
- `dashboard.test.ts` verifies passive rendering, minimal copy, correct kind labels and shared/personal read-only presentation.

Data validation and lifetime behavior live in `$lib/dashboard/`. Owner authorization and mutation guards remain in `$lib/personal-connections/`.
