export type ConnectorConfigurationFeedback = {
  message: string;
  tone: 'success' | 'warning' | 'error' | 'muted';
};

export class ConnectorConfigurationFormState {
  currentSignature = $state('');
  checkedSignature = $state<string | null>(null);

  saveEnabled = $derived(this.currentSignature.length > 0 && this.currentSignature === this.checkedSignature);

  replaceCurrentSignature = (signature: string): void => {
    this.currentSignature = signature;
  };

  markChecked = (signature: string): void => {
    this.checkedSignature = signature;
  };

  invalidateCheck = (): void => {
    this.checkedSignature = null;
  };

  feedback = (formStatus: string | undefined, errorMessage: string | undefined): ConnectorConfigurationFeedback => {
    if (formStatus === 'check-valid' && this.saveEnabled) {
      return { message: 'Configuration check passed. You can save this configuration.', tone: 'success' };
    }

    if (formStatus === 'check-invalid') {
      return { message: errorMessage ?? 'Configuration check failed', tone: 'error' };
    }

    if (formStatus === 'failed') {
      return { message: errorMessage ?? 'Configuration could not be saved', tone: 'error' };
    }

    if (!this.saveEnabled) {
      return { message: 'Run configuration check before saving.', tone: 'warning' };
    }

    return { message: 'Configuration is ready to save.', tone: 'muted' };
  };
}
