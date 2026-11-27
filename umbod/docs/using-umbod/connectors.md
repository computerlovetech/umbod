# Set up connectors

Use an OpenAPI connector for an HTTP API with an OpenAPI description, or add an MCP connector for an existing MCP server. In both cases, publish the connector and grant access only to the groups that need it.

## OpenAPI connectors

1. In **Administration**, open **Connectors**, choose **Add connector**, and select **OpenAPI**.
2. Upload the OpenAPI JSON file or enter its HTTPS URL. Approve only the hostname the connector is allowed to call, and configure authentication if the API requires it.
3. Review and enable the tools you want to offer. Publish the connector, then grant access in **Group permissions**. Verify that a member of an intended group can see the tools.

## Shared and Personal connectors

For an MCP server, choose **Shared** if authorized groups should use one account managed by an administrator. Choose **Personal** if each user should sign in to that server with their own account. Neither choice makes a connector public.

| | Shared | Personal |
| --- | --- | --- |
| Downstream account | One connection configured by an administrator | Each user connects their own account |
| Credentials | Managed for the shared connection | Saved encrypted by Umbod, scoped to the individual user and server |
| Tool catalogue | Centrally discovered and managed | Discovered privately for each user |
| Administrator control | Publication, capability activation, and group/capability permissions | Server allowlist, OAuth settings, publication, and connector-level group permission |
| User setup | No individual downstream sign-in | Enable access and sign in; Umbod then loads personal tools |

These labels apply to downstream MCP servers. They are not separate plugin packaging formats; see [Connector plugins](../plugins/index.md) for installing custom connector code.

## For administrators

### Choose the connection type

Open the **MCP connectors** workspace at `/admin/downstream-mcp-connectors`. Its inventory contains both types, labelled Shared or Personal. Use **Add** and choose the appropriate type.

For Shared, configure the endpoint and shared authentication, discover capabilities, publish the connector, activate the intended capabilities, and grant the necessary group permissions. Verify discovery with an account in an intended group. Publication or activation alone does not grant access.

For Personal, register only servers you trust: users can connect only to servers administrators make available.

### Register a Personal connector

1. Add a Personal server with its name, endpoint, and naming settings. These server definition fields are read-only after registration.
2. Configure the OAuth application and requested scopes. **Automatic registration** requires provider support for dynamic client registration, either public or confidential. Otherwise use **Use an existing client ID** or **Use an existing client ID and secret**. Confidential clients require an explicit Basic or POST authentication method.
3. Register the exact callback URI required by the provider when using a preconfigured client. Follow the [operator prerequisites](../operations/configuration.md#personal-connections-identity-policy); Umbod login and downstream account authorization are separate.
4. Publish the server explicitly. New registrations start unpublished, without user consent, discovery, or permissions.
5. Open **Group permissions** and grant connector-level access only to the intended groups.

!!! warning "A Personal grant trusts the server's tools"
    A connector-level group grant permits all tools the downstream server exposes to that user, including tools added later and discovered on an explicit rediscovery. Personal tools do not require administrator per-tool approval, activation, or capability grants. Grant access only to trusted servers.

Publication and group access make a server eligible for users to connect. They do not sign anyone in, enable personal access, or discover tools on a user's behalf. Administrators do not enter each user's credentials in the shared authentication form.

### Change or withdraw access

- **Replace OAuth settings:** an effective policy change invalidates users' saved authorizations, private tool inventories, and pending sign-ins. Users must sign in and discover tools again. Publication, group permissions, and enablement are preserved. Stored confidential client secrets are not displayed; saving confidential settings requires a freshly entered secret.
- **Withdraw publication or remove a group grant:** users lose current eligibility and tool execution access. This is not a downstream token-revocation operation or an owner disconnect.
- **Delete a server:** explicitly remove outstanding connector and tool grants first; otherwise deletion is blocked. Retained grants remain removable in Group permissions even for unpublished servers.

Keep the identity namespace and root secret stable. Changing identity authority changes ownership; changing encryption material can make saved credentials unreadable. If Personal registration is unavailable, ask the deployment operator to check [personal connections identity policy](../operations/configuration.md#personal-connections-identity-policy).

## For normal users

When supporting a user, check that the connector is published and their group has access before troubleshooting sign-in. Normal users see eligible connectors and cannot edit Shared configuration.

For Personal connections, ask the user to check **Personal access**: they must choose **Enable access**, then **Sign in** to choose a downstream account and grant consent. Umbod sign-in alone is not enough. A pending provider flow must be completed or canceled before starting another.

A successful sign-in triggers tool loading automatically, but does not guarantee it succeeds. Check for **Tools available**. If loading failed, use **Retry loading tools**; use **Refresh tools** for later discovery. The user sees a private inventory and runs tools with their own downstream permissions.

### Manage your connection

| Action or state | Meaning |
| --- | --- |
| Check authorization status | Checks saved authorization records, not a live provider connection |
| Renew access | Explicitly refresh authorization where supported; sign in again if required |
| Refresh tools | Refreshes your private catalogue, including new downstream tools |
| Disable access | Stops personal access while retaining saved authorization |
| Disconnect | Removes saved authorization and disables access; a pending sign-in cannot restore it |

Umbod does not silently refresh credentials or retry tool calls. Ask the user to follow the displayed recovery action after expiry, authorization changes, or discovery failures. Disconnecting in Umbod does not guarantee provider-side token revocation; use the provider's connected-app settings when revocation is needed.

If a connector disappears or stops working, check recent changes to publication, group access, or OAuth settings. Personal authorization cannot bypass those controls. A saved connection may still appear for cleanup after access is withdrawn.
