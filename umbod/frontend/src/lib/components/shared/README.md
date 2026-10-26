# Shared components

**Module responsibility:** Neutral presentation and interaction mechanisms reused across actors and features.

- `workspace/` provides workspace structure, navigation, account presentation and explicit logout interaction.
- `mcp-setup/` provides endpoint-driven client setup instructions shared by administration and Dashboard.
- `tools/` provides a snippet-based tool card, optional description/schema presenters, neutral display types and schema formatting. See `tools/README.md`.

Follow the composition boundaries in `../README.md`: parents choose actor-specific content, actions and presentation, while shared components own reusable mechanics. Shared styling changes are deliberate cross-consumer changes, not actor-local customization.
