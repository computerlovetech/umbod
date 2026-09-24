export type AdminNavigationItem = {
  label: string;
  href: string;
};

export type AdminPageData = {
  navigationItems: AdminNavigationItem[];
};

export function load(): AdminPageData {
  return {
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
  };
}
