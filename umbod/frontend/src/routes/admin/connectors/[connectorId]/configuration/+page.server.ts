import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { checkConnectorConfiguration, loadConnectorConfiguration, saveConnectorConfiguration } from '$lib/admin/connectors-api';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import { createConfigurationBody, createFailureValues, getSecretFields } from '$lib/admin/connectors-forms';

export const load: PageServerLoad = (event) => {
  return loadConnectorConfiguration(adminServerApi(event).connectors, event.params.connectorId);
};

export const actions: Actions = {
  checkConfiguration: async ({ fetch, params, request }) => {
    const formData = await request.formData();
    const secretFields = getSecretFields(formData);
    const configuration = createConfigurationBody(formData, secretFields);
    const values = createFailureValues(formData, secretFields);
    const result = await checkConnectorConfiguration(adminServerApi({ fetch, request }).connectors, params.connectorId, configuration);

    if (result.status === 'valid') {
      return { status: 'check-valid', connectorId: params.connectorId, successMessage: 'Configuration check passed', values };
    }

    if (result.status === 'invalid') {
      return { status: 'check-invalid', connectorId: params.connectorId, errorMessage: result.message, fieldMessages: result.fieldMessages, values };
    }

    return { status: 'failed', connectorId: params.connectorId, errorMessage: result.errorMessage, values };
  },
  default: async ({ fetch, params, request }) => {
    const formData = await request.formData();
    const secretFields = getSecretFields(formData);
    const configuration = createConfigurationBody(formData, secretFields);
    const values = createFailureValues(formData, secretFields);

    const result = await saveConnectorConfiguration(adminServerApi({ fetch, request }).connectors, params.connectorId, configuration);

    if (result.status === 'saved') {
      throw redirect(303, `/admin/connectors?configured=${params.connectorId}`);
    }

    return { status: 'failed', connectorId: params.connectorId, errorMessage: result.errorMessage, values };
  }
};
