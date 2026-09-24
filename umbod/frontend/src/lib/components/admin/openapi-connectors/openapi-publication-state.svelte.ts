export type OpenApiPublicationActionLabel = 'Publish' | 'Unpublish';
export type OpenApiPendingPublication = {
  form: HTMLFormElement;
  connectorName: string;
  actionLabel: OpenApiPublicationActionLabel;
};

export class OpenApiPublicationState {
  pendingPublication = $state<OpenApiPendingPublication | null>(null);
  modalTitle = $derived(this.pendingPublication ? `${this.pendingPublication.actionLabel} ${this.pendingPublication.connectorName}?` : '');
  modalMessage = $derived(this.pendingPublication ? `Please confirm that you want to ${this.pendingPublication.actionLabel.toLowerCase()} the OpenAPI connector ${this.pendingPublication.connectorName}.` : '');

  request = (form: HTMLFormElement, connectorName: string, actionLabel: OpenApiPublicationActionLabel): void => {
    this.pendingPublication = { form, connectorName, actionLabel };
  };

  cancel = (): void => {
    this.pendingPublication = null;
  };

  confirm = (): void => {
    const form = this.pendingPublication?.form;
    this.pendingPublication = null;
    form?.requestSubmit();
  };
}
