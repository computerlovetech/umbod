import { BrowserRequestError, browserRequest } from '$lib/admin/infrastructure/browser-request';
import { adminApi } from '$lib/admin/infrastructure/admin-api';

import type { ToastApi } from '$lib/components/feedback';

export class OpenApiBearerConfigurationState {
  token = $state('');
  configured = $state(false);
  loading = $state(true);
  saving = $state(false);
  message = $state('');

  constructor(
    private readonly connectorId: string,
    private readonly request: typeof globalThis.fetch = globalThis.fetch,
    private readonly toast?: ToastApi
  ) {}

  setTokenValue = (token: string): void => {
    this.token = token;
  };

  setToken = (event: Event): void => {
    if (event.currentTarget instanceof HTMLInputElement) this.setTokenValue(event.currentTarget.value);
  };

  load = async (): Promise<void> => {
    this.loading = true;
    this.message = '';
    try {
      const configuration = await browserRequest(() => adminApi(this.request).openApiConnectors.connectors.getConfiguration(this.connectorId));
      this.configured = configuration.configured;
    } catch (error) {
      if (!(error instanceof BrowserRequestError)) throw error;
      this.message = 'Bearer configuration is unavailable.';
      this.toast?.error(this.message);
    } finally {
      this.token = '';
      this.loading = false;
    }
  };

  save = async (event: SubmitEvent): Promise<void> => {
    event.preventDefault();
    this.saving = true;
    this.message = '';
    try {
      const configuration = await browserRequest(() => adminApi(this.request).openApiConnectors.connectors.putConfiguration(this.connectorId, { authentication_type: 'bearer', bearer_token: this.token }));
      this.configured = configuration.configured;
      this.message = configuration.configured ? 'Bearer token saved.' : 'Enter a Bearer token.';
      if (configuration.configured) this.toast?.success(this.message);
    } catch (error) {
      if (!(error instanceof BrowserRequestError)) throw error;
      this.message = 'Bearer configuration could not be saved.';
      this.toast?.error(this.message);
    } finally {
      this.token = '';
      this.saving = false;
    }
  };
}
