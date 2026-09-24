import { describe, expect, test, vi } from 'vitest';

type ConnectorListPageLoad = (event: { fetch: typeof fetch; url: URL }) => Promise<unknown>;
type ConnectorConfigurationPageLoad = (event: {
  fetch: typeof fetch;
  params: { connectorId: string };
}) => Promise<unknown>;
type ConnectorConfigurationActionEvent = {
  fetch: typeof fetch;
  params: { connectorId: string };
  request: Request;
};

type ConnectorConfigurationActions = {
  checkConfiguration: (event: ConnectorConfigurationActionEvent) => Promise<unknown>;
  default: (event: ConnectorConfigurationActionEvent) => Promise<unknown>;
};

type ConnectorConfigurationApiResponse = {
  connector: {
    id: string;
    display_name: string;
  };
  schema: {
    fields: Array<{
      name: string;
      type: string;
      required: boolean;
      secret: boolean;
    }>;
  };
  configuration: Record<string, unknown> | null;
};

function createConfigurationResponse(
  status: number,
  body: ConnectorConfigurationApiResponse | Record<string, unknown>
): Response {
  return new Response(JSON.stringify(body), { status });
}

function createFormRequest(formData: Record<string, string>): Request {
  const body = new FormData();

  for (const [key, value] of Object.entries(formData)) {
    body.set(key, value);
  }

  return new Request('http://frontend/admin/connectors/catalog/slack/configuration', {
    method: 'POST',
    body
  });
}

describe('admin connector configuration UI acceptance', () => {
  test('connector list includes configure actions and no success message by default', async () => {
    const { load } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      load: ConnectorListPageLoad;
    };
    const fetchConnectors = vi.fn(async () =>
      new Response(
        JSON.stringify({
          connectors: [
            {
              id: 'slack',
              display_name: 'Slack',
              description: 'Connects to Slack workspaces and channels',
              extension: { source: 'built-in' },
              publication_status: 'unconfigured',
              available_actions: ['configure']
            }
          ]
        }),
        { status: 200 }
      )
    ) as typeof fetch;

    const pageData = await load({
      fetch: fetchConnectors,
      url: new URL('http://frontend/admin/connectors')
    });

    expect(pageData).toEqual({
      status: 'ready',
      successMessage: null,
      connectors: [
        {
          id: 'slack',
          name: 'Slack',
          description: 'Connects to Slack workspaces and channels',
          sourceLabel: 'Built-in',
          configureHref: '/admin/connectors/slack/configuration',
          publicationStatus: 'Unconfigured',
          isConfigured: false,
          canPublish: false,
          canUnpublish: false,
          tools: []
        }
      ]
    });
  });

  test('selecting an unconfigured Slack connector loads its schema for the catalog modal', async () => {
    const { load } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      load: ConnectorListPageLoad;
    };
    const fetchConnectorData = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/admin/connectors/catalog')) {
        return new Response(JSON.stringify({
          connectors: [{
            id: 'slack',
            display_name: 'Slack',
            description: 'Connects to Slack workspaces and channels',
            extension: { source: 'built-in' },
            publication_status: 'unconfigured',
            available_actions: ['configure']
          }]
        }), { status: 200 });
      }
      expect(input).toBe('http://api:8000/admin/connectors/catalog/slack/configuration');
      return createConfigurationResponse(200, {
        connector: { id: 'slack', display_name: 'Slack' },
        schema: {
          fields: [
            { name: 'workspace_name', type: 'string', required: true, secret: false },
            { name: 'bot_token', type: 'string', required: true, secret: true },
            { name: 'default_channel_id', type: 'string', required: true, secret: false }
          ]
        },
        configuration: null
      });
    }) as typeof fetch;

    const pageData = await load({
      fetch: fetchConnectorData,
      url: new URL('http://frontend/admin/connectors?connector=slack')
    });

    expect(pageData).toMatchObject({
      status: 'ready',
      selectedConnectorId: 'slack',
      connectors: [{
        id: 'slack',
        configurationFields: [
          { name: 'workspace_name', inputType: 'text' },
          { name: 'bot_token', inputType: 'password' },
          { name: 'default_channel_id', inputType: 'text' }
        ]
      }]
    });
    expect(fetchConnectorData).toHaveBeenCalledTimes(2);
  });

  test('connector list shows configuration success after returning from a saved connector', async () => {
    const { load } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      load: ConnectorListPageLoad;
    };
    const fetchConnectors = vi.fn(async () =>
      new Response(
        JSON.stringify({
          connectors: [
            {
              id: 'slack',
              display_name: 'Slack',
              description: 'Connects to Slack workspaces and channels',
              extension: { source: 'built-in' },
              publication_status: 'unconfigured',
              available_actions: ['configure']
            }
          ]
        }),
        { status: 200 }
      )
    ) as typeof fetch;

    const pageData = await load({
      fetch: fetchConnectors,
      url: new URL('http://frontend/admin/connectors?configured=slack')
    });

    expect(pageData).toMatchObject({
      status: 'ready',
      successMessage: 'Slack was configured successfully'
    });
  });

  test('admin opens a schema-driven connector configuration page for string and secret fields', async () => {
    const { load } = (await import(
      '../../routes/admin/connectors/[connectorId]/configuration/+page.server'
    )) as unknown as { load: ConnectorConfigurationPageLoad };
    const fetchConfiguration = vi.fn(async (input: RequestInfo | URL) => {
      expect(input).toBe('http://api:8000/admin/connectors/catalog/slack/configuration');
      return createConfigurationResponse(200, {
        connector: { id: 'slack', display_name: 'Slack' },
        schema: {
          fields: [
            { name: 'workspace_name', type: 'string', required: true, secret: false },
            { name: 'bot_token', type: 'string', required: true, secret: true },
            { name: 'default_channel_id', type: 'string', required: true, secret: false }
          ]
        },
        configuration: null
      });
    }) as typeof fetch;

    const pageData = await load({ fetch: fetchConfiguration, params: { connectorId: 'slack' } });

    expect(pageData).toEqual({
      status: 'ready',
      connector: { id: 'slack', name: 'Slack' },
      fields: [
        {
          name: 'workspace_name',
          label: 'Workspace name',
          inputType: 'text',
          required: true,
          value: '',
          unsupported: false
        },
        {
          name: 'bot_token',
          label: 'Bot token',
          inputType: 'password',
          required: true,
          value: '',
          secretConfigured: false,
          unsupported: false
        },
        {
          name: 'default_channel_id',
          label: 'Default channel id',
          inputType: 'text',
          required: true,
          value: '',
          unsupported: false
        }
      ],
      errorMessage: null
    });
  });

  test('existing secret configuration is represented without exposing the real secret', async () => {
    const { load } = (await import(
      '../../routes/admin/connectors/[connectorId]/configuration/+page.server'
    )) as unknown as { load: ConnectorConfigurationPageLoad };
    const fetchConfiguration = vi.fn(async () =>
      createConfigurationResponse(200, {
        connector: { id: 'slack', display_name: 'Slack' },
        schema: {
          fields: [
            { name: 'workspace_name', type: 'string', required: true, secret: false },
            { name: 'bot_token', type: 'string', required: true, secret: true }
          ]
        },
        configuration: {
          workspace_name: 'Acme',
          bot_token: '**********'
        }
      })
    ) as typeof fetch;

    const pageData = await load({ fetch: fetchConfiguration, params: { connectorId: 'slack' } });

    expect(JSON.stringify(pageData)).not.toContain('xoxb-secret');
    expect(pageData).toMatchObject({
      fields: [
        { name: 'workspace_name', value: 'Acme' },
        { name: 'bot_token', inputType: 'password', value: '', secretConfigured: true }
      ]
    });
  });

  test('successful save posts configuration and redirects to connector list success page', async () => {
    const { actions } = (await import(
      '../../routes/admin/connectors/[connectorId]/configuration/+page.server'
    )) as unknown as { actions: ConnectorConfigurationActions };
    const saveConfiguration = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toBe('http://api:8000/admin/connectors/catalog/slack/configuration');
      expect(init?.method).toBe('PUT');
      expect(JSON.parse(String(init?.body))).toEqual({
        configuration: {
          workspace_name: 'Acme',
          bot_token: 'xoxb-secret',
          default_channel_id: 'C123'
        }
      });
      return createConfigurationResponse(200, {
        connector_id: 'slack',
        status: 'configured',
        configuration: {
          workspace_name: 'Acme',
          bot_token: '**********',
          default_channel_id: 'C123'
        }
      });
    }) as typeof fetch;

    await expect(
      actions.default({
        fetch: saveConfiguration,
        params: { connectorId: 'slack' },
        request: createFormRequest({
          workspace_name: 'Acme',
          bot_token: 'xoxb-secret',
          default_channel_id: 'C123'
        })
      })
    ).rejects.toMatchObject({ status: 303, location: '/admin/connectors?configured=slack' });
  });

  test('blank existing secret is omitted during update so it can remain unchanged', async () => {
    const { actions } = (await import(
      '../../routes/admin/connectors/[connectorId]/configuration/+page.server'
    )) as unknown as { actions: ConnectorConfigurationActions };
    const saveConfiguration = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({
        configuration: {
          workspace_name: 'Acme Support',
          default_channel_id: 'C789'
        }
      });
      return createConfigurationResponse(200, {
        connector_id: 'slack',
        status: 'configured',
        configuration: {
          workspace_name: 'Acme Support',
          bot_token: '**********',
          default_channel_id: 'C789'
        }
      });
    }) as typeof fetch;

    await expect(
      actions.default({
        fetch: saveConfiguration,
        params: { connectorId: 'slack' },
        request: createFormRequest({
          workspace_name: 'Acme Support',
          bot_token: '',
          default_channel_id: 'C789',
          __secret_fields: 'bot_token'
        })
      })
    ).rejects.toMatchObject({ status: 303, location: '/admin/connectors?configured=slack' });
  });

  test('configuration check posts current values without saving them', async () => {
    const { actions } = (await import(
      '../../routes/admin/connectors/[connectorId]/configuration/+page.server'
    )) as unknown as { actions: ConnectorConfigurationActions };
    const checkConfiguration = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toBe('http://api:8000/admin/connectors/catalog/slack/configuration/validations');
      expect(init?.method).toBe('POST');
      expect(JSON.parse(String(init?.body))).toEqual({
        configuration: {
          workspace_name: 'Acme',
          bot_token: 'xoxb-secret',
          default_channel_id: 'C123'
        }
      });
      return createConfigurationResponse(200, { valid: true, message: null, field_messages: {} });
    }) as typeof fetch;

    const result = await actions.checkConfiguration({
      fetch: checkConfiguration,
      params: { connectorId: 'slack' },
      request: createFormRequest({
        workspace_name: 'Acme',
        bot_token: 'xoxb-secret',
        default_channel_id: 'C123'
      })
    });

    expect(result).toEqual({
      status: 'check-valid',
      connectorId: 'slack',
      successMessage: 'Configuration check passed',
      values: {
        workspace_name: 'Acme',
        bot_token: 'xoxb-secret',
        default_channel_id: 'C123'
      }
    });
  });

  test('invalid configuration check stays on the configuration page and keeps non-secret values', async () => {
    const { actions } = (await import(
      '../../routes/admin/connectors/[connectorId]/configuration/+page.server'
    )) as unknown as { actions: ConnectorConfigurationActions };
    const checkConfiguration = vi.fn(async () =>
      createConfigurationResponse(200, {
        valid: false,
        message: 'Slack bot token is not valid',
        field_messages: { bot_token: 'Use a valid token' }
      })
    ) as typeof fetch;

    const result = await actions.checkConfiguration({
      fetch: checkConfiguration,
      params: { connectorId: 'slack' },
      request: createFormRequest({
        workspace_name: 'Acme',
        bot_token: 'xoxb-secret',
        default_channel_id: 'C123',
        __secret_fields: 'bot_token'
      })
    });

    expect(result).toEqual({
      status: 'check-invalid',
      connectorId: 'slack',
      errorMessage: 'Slack bot token is not valid',
      fieldMessages: { bot_token: 'Use a valid token' },
      values: {
        workspace_name: 'Acme',
        default_channel_id: 'C123'
      }
    });
    expect(JSON.stringify(result)).not.toContain('xoxb-secret');
  });

  test('validation failure stays on the configuration page and keeps non-secret values', async () => {
    const { actions } = (await import(
      '../../routes/admin/connectors/[connectorId]/configuration/+page.server'
    )) as unknown as { actions: ConnectorConfigurationActions };
    const saveConfiguration = vi.fn(async () =>
      createConfigurationResponse(422, {
        detail: [
          {
            loc: ['default_channel_id'],
            msg: 'Field required'
          }
        ]
      })
    ) as typeof fetch;

    const result = await actions.default({
      fetch: saveConfiguration,
      params: { connectorId: 'slack' },
      request: createFormRequest({
        workspace_name: 'Acme',
        bot_token: 'xoxb-secret',
        default_channel_id: '',
        __secret_fields: 'bot_token'
      })
    });

    expect(result).toEqual({
      status: 'failed',
      connectorId: 'slack',
      errorMessage: 'default_channel_id: Field required',
      values: {
        workspace_name: 'Acme',
        default_channel_id: ''
      }
    });
    expect(JSON.stringify(result)).not.toContain('xoxb-secret');
  });

  test('configuration load failure shows a retryable page state instead of a form', async () => {
    const { load } = (await import(
      '../../routes/admin/connectors/[connectorId]/configuration/+page.server'
    )) as unknown as { load: ConnectorConfigurationPageLoad };
    const fetchConfiguration = vi.fn(async () => new Response('Not found', { status: 404 })) as typeof fetch;

    const pageData = await load({ fetch: fetchConfiguration, params: { connectorId: 'github' } });

    expect(pageData).toEqual({
      status: 'failed',
      message: 'Connector configuration could not be loaded',
      backHref: '/admin/connectors'
    });
  });
});
