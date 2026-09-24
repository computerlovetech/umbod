import { describe, expect, test, vi } from 'vitest';

type ConnectorApiResponse = {
  connectors: Array<{
    id: string;
    display_name: string;
    description: string;
    extension: {
      source: 'built-in' | 'user-supplied';
    };
    publication_status: 'unconfigured' | 'draft' | 'published' | 'unpublished';
    available_actions: Array<'configure' | 'publish' | 'unpublish'>;
  }>;
};

type ConnectorPageLoad = (event: { fetch: typeof fetch; url: URL }) => Promise<unknown>;
type AdminPageLoad = () => Promise<unknown> | unknown;

function createJsonFetch(status: number, body: ConnectorApiResponse): typeof fetch {
  return vi.fn(async () => new Response(JSON.stringify(body), { status })) as typeof fetch;
}

function createFailingFetch(): typeof fetch {
  return vi.fn(async () => new Response('Service unavailable', { status: 503 })) as typeof fetch;
}

describe('admin connector list UI acceptance', () => {
  test('admin navigation offers navigation to the connector list page', async () => {
    const { load } = (await import('../../routes/admin/+page')) as unknown as { load: AdminPageLoad };

    const pageData = await load();

    expect(pageData).toEqual({
      navigationItems: [
        {
          label: 'Connectors',
          href: '/admin/connectors'
        },
        {
          label: 'Group permissions',
          href: '/admin/group-permissions'
        },
        {
          label: 'MCP setup guide',
          href: '/admin/mcp-setup'
        },
        {
          label: 'Configuration',
          href: '/admin/instance-configuration'
        }
      ]
    });
  });

  test('server-side connector loading uses the private API base URL instead of the frontend origin', async () => {
    const { load } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      load: ConnectorPageLoad;
    };
    const fetchConnectors = vi.fn(async (input: RequestInfo | URL) => {
      if (input !== 'http://api:8000/admin/connectors/catalog') {
        throw new TypeError('fetch failed');
      }
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
            }
          ]
        }),
        { status: 200 }
      );
    }) as typeof fetch;

    const pageData = await load({ fetch: fetchConnectors, url: new URL('http://frontend/admin/connectors') });

    expect(fetchConnectors).toHaveBeenCalledWith('http://api:8000/admin/connectors/catalog', { method: 'GET' });
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

  test('admin sees registered connectors with human readable source labels', async () => {
    const { load } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      load: ConnectorPageLoad;
    };
    const fetchConnectors = createJsonFetch(200, {
      connectors: [
        {
          id: 'github',
          display_name: 'GitHub',
          description: 'Connects to GitHub repositories and issues',
          extension: { source: 'built-in' },
          publication_status: 'unconfigured',
          available_actions: ['configure']
        },
        {
          id: 'linear',
          display_name: 'Linear',
          description: 'Connects to Linear issues and projects',
          extension: { source: 'user-supplied' },
          publication_status: 'unconfigured',
          available_actions: ['configure']
        }
      ]
    });

    const pageData = await load({ fetch: fetchConnectors, url: new URL('http://frontend/admin/connectors') });

    expect(fetchConnectors).toHaveBeenCalledWith('http://api:8000/admin/connectors/catalog', { method: 'GET' });
    expect(pageData).toEqual({
      status: 'ready',
      successMessage: null,
      connectors: [
        {
          id: 'github',
          name: 'GitHub',
          description: 'Connects to GitHub repositories and issues',
          sourceLabel: 'Built-in',
          configureHref: '/admin/connectors/github/configuration',
          publicationStatus: 'Unconfigured',
          isConfigured: false,
          canPublish: false,
          canUnpublish: false,
          tools: []
        },
        {
          id: 'linear',
          name: 'Linear',
          description: 'Connects to Linear issues and projects',
          sourceLabel: 'User supplied',
          configureHref: '/admin/connectors/linear/configuration',
          publicationStatus: 'Unconfigured',
          isConfigured: false,
          canPublish: false,
          canUnpublish: false,
          tools: []
        }
      ]
    });
  });

  test('admin sees an empty state when no connectors are currently available', async () => {
    const { load } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      load: ConnectorPageLoad;
    };
    const fetchConnectors = createJsonFetch(200, { connectors: [] });

    const pageData = await load({ fetch: fetchConnectors, url: new URL('http://frontend/admin/connectors') });

    expect(pageData).toEqual({
      status: 'empty',
      message: 'No connectors are currently available',
      connectors: []
    });
  });

  test('admin sees a retryable failure state when the connector API request fails', async () => {
    const { load } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      load: ConnectorPageLoad;
    };
    const fetchConnectors = createFailingFetch();

    const pageData = await load({ fetch: fetchConnectors, url: new URL('http://frontend/admin/connectors') });

    expect(pageData).toEqual({
      status: 'failed',
      message: 'Failed to get connectors',
      retryLabel: 'Try again',
      connectors: []
    });
  });

  test('connector list reflects the latest successful API response after reload or retry', async () => {
    const { load } = (await import('../../routes/admin/connectors/+page.server')) as unknown as {
      load: ConnectorPageLoad;
    };
    const emptyFetch = createJsonFetch(200, { connectors: [] });
    const slackFetch = createJsonFetch(200, {
      connectors: [
        {
          id: 'slack',
          display_name: 'Slack',
          description: 'Connects to Slack workspaces and channels',
          extension: { source: 'user-supplied' },
          publication_status: 'unconfigured',
          available_actions: ['configure']
        }
      ]
    });

    const emptyPageData = await load({ fetch: emptyFetch, url: new URL('http://frontend/admin/connectors') });
    const latestPageData = await load({ fetch: slackFetch, url: new URL('http://frontend/admin/connectors') });

    expect(emptyPageData).toEqual({
      status: 'empty',
      message: 'No connectors are currently available',
      connectors: []
    });
    expect(latestPageData).toEqual({
      status: 'ready',
      successMessage: null,
      connectors: [
        {
          id: 'slack',
          name: 'Slack',
          description: 'Connects to Slack workspaces and channels',
          sourceLabel: 'User supplied',
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
});
