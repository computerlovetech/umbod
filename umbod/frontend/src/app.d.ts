declare global {
  namespace App {
    interface PageState {
      openConnectorSetup?: import('#lib/components/admin/connectors/add-connector-state.svelte.js').ConnectorSetupKind;
    }
  }
}

export {};
