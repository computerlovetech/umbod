import { describe, expect, test, vi } from 'vitest';

type ConnectorListPageLoad = (event: { fetch: typeof fetch; url: URL }) => Promise<unknown>;
type ConnectorListPageActions = {
  publish: (event: { fetch: typeof fetch; request: Request }) => Promise<unknown>;
  unpublish: (event: { fetch: typeof fetch; request: Request }) => Promise<unknown>;
};

function createConnectorListFetch(): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (!url.endsWith('/admin/connectors/catalog')) return new Response(null, { status: 404, statusText: 'Not Found' });
    return new Response(
      JSON.stringify({
        connectors: [
          {
            id: 'slack',
            display_name: 'Slack',
            description: 'Connects to Slack workspaces and channels',
            extension: { source: 'built-in' },
            publication_status: 'unconfigured',
            available_actions: ['configure']
          },
          {
            id: 'test',
            display_name: 'Test Connector',
            description: 'Provides a simple connector for validating configuration and MCP publishing flows',
            extension: { source: 'built-in' },
            publication_status: 'draft',
            available_actions: ['configure', 'publish']
          },
          {
            id: 'github',
            display_name: 'GitHub',
            description: 'Connects to GitHub repositories and issues',
            extension: { source: 'user-supplied' },
            publication_status: 'published',
            available_actions: ['configure', 'unpublish']
          },
          {
            id: 'linear',
            display_name: 'Linear',
            description: 'Connects to Linear issues and projects',
            extension: { source: 'user-supplied' },
            publication_status: 'unpublished',
            available_actions: ['configure', 'publish']
          }
        ]
      }),
      { status: 200 }
    );
  }) as typeof fetch;
}

function createPublicationRequest(connectorId: string): Request {
  const body = new FormData();
  body.set('connectorId', connectorId);
  return new Request('http://frontend/admin/connectors', { method: 'POST', body });
}

describe('admin connector publishing UI acceptance', () => {
  test('connector list shows publication status and allowed operations for each connector', async () => {
    const { load } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      load: ConnectorListPageLoad;
    };

    const pageData = await load({
      fetch: createConnectorListFetch(),
      url: new URL('http://frontend/admin/connectors')
    });

    expect(pageData).toEqual({
      status: 'ready',
      successMessage: null,
      selectedConnectorId: 'test',
      selectedDetailFailed: true,
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
        },
        {
          id: 'test',
          name: 'Test Connector',
          description: 'Provides a simple connector for validating configuration and MCP publishing flows',
          sourceLabel: 'Built-in',
          configureHref: '/admin/connectors/test/configuration',
          publicationStatus: 'Draft',
          isConfigured: true,
          canPublish: true,
          canUnpublish: false,
          tools: []
        },
        {
          id: 'github',
          name: 'GitHub',
          description: 'Connects to GitHub repositories and issues',
          sourceLabel: 'User supplied',
          configureHref: '/admin/connectors/github/configuration',
          publicationStatus: 'Published',
          isConfigured: true,
          canPublish: false,
          canUnpublish: true,
          tools: []
        },
        {
          id: 'linear',
          name: 'Linear',
          description: 'Connects to Linear issues and projects',
          sourceLabel: 'User supplied',
          configureHref: '/admin/connectors/linear/configuration',
          publicationStatus: 'Unpublished',
          isConfigured: true,
          canPublish: true,
          canUnpublish: false,
          tools: []
        }
      ]
    });
  });

  test('publish action calls the connector publication API after confirmation has been submitted', async () => {
    const { actions } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      actions: ConnectorListPageActions;
    };
    const publishConnector = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toBe('http://api:8000/admin/connectors/catalog/test/publication');
      expect(init?.method).toBe('PUT');
      return new Response(JSON.stringify({ connector_id: 'test', publication_status: 'published' }), {
        status: 200
      });
    }) as typeof fetch;

    const result = await actions.publish({
      fetch: publishConnector,
      request: createPublicationRequest('test')
    });

    expect(result).toEqual({
      status: 'published',
      successMessage: 'test was published successfully'
    });
  });

  test('unpublish action calls the connector publication API after confirmation has been submitted', async () => {
    const { actions } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      actions: ConnectorListPageActions;
    };
    const unpublishConnector = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toBe('http://api:8000/admin/connectors/catalog/test/publication');
      expect(init?.method).toBe('DELETE');
      return new Response(JSON.stringify({ connector_id: 'test', publication_status: 'unpublished' }), {
        status: 200
      });
    }) as typeof fetch;

    const result = await actions.unpublish({
      fetch: unpublishConnector,
      request: createPublicationRequest('test')
    });

    expect(result).toEqual({
      status: 'unpublished',
      successMessage: 'test was unpublished successfully'
    });
  });

  test('publish action reports connector check failures without publishing', async () => {
    const { actions } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      actions: ConnectorListPageActions;
    };
    const rejectPublication = vi.fn(async () =>
      new Response(
        JSON.stringify({
          valid: false,
          message: 'Test Connector API key must be "test-key" before publishing.',
          field_messages: { api_key: 'Use "test-key" for the local Test Connector.' }
        }),
        { status: 422 }
      )
    ) as typeof fetch;

    const result = await actions.publish({
      fetch: rejectPublication,
      request: createPublicationRequest('test')
    });

    expect(result).toEqual({
      status: 'failed',
      errorMessage: 'Test Connector API key must be "test-key" before publishing.'
    });
  });
});
