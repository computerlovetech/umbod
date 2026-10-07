# Instance settings

Read-only administration presentation at `/admin/instance-configuration`.

- `InstanceConfigurationView.svelte` composes essentials, task sections and collapsed deployment details.
- `SettingRow.svelte` presents readable values and technical disclosures with raw-value copying.
- `presentation.ts` classifies entries by variable, formats display values and preserves original group context for advanced settings.
- `instance-settings-state.svelte.ts` derives presentation from current page data.
- `instance-configuration-copy-state.svelte.ts` owns clipboard feedback and the unchanged raw-value formatter.

Wire schemas and page-state contracts remain in `$lib/admin/instance-configuration.ts`. The route server loader owns authorization and failure handling.
