import type { PageLoadEvent } from './$types';

export type AdminNavigationItem = {
  label: string;
  href: string;
};

export type AdminPageData = {
  navigationItems: AdminNavigationItem[];
};

export function load(): AdminPageData;
export function load(event: Pick<PageLoadEvent, 'data'>): AdminPageData & PageLoadEvent['data'];
export function load(event?: Pick<PageLoadEvent, 'data'>) {
  return {
    ...event?.data,
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
        label: 'Instance settings',
        href: '/admin/instance-configuration'
      }
    ]
  };
}
