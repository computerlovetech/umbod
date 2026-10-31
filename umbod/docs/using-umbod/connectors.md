# Shared and Personal connectors

Umbod distinguishes between **Shared** and **Personal** downstream MCP connectors. The distinction determines whose account authorizes access to the downstream server, not whether the connector is public.

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

Use Shared when authorized users should access a centrally managed downstream connection. Configure the endpoint and shared authentication, discover capabilities, publish the connector, activate the intended capabilities, and grant the necessary group permissions. Publication or activation alone does not grant access.

Use Personal when users must act through their own downstream accounts. Users cannot add arbitrary personal servers: administrators control the available server inventory.

### Register a Personal connector

1. Add a Personal server with its name, endpoint, and naming settings. These server definition fields are read-only after registration.
2. Configure the OAuth application and requested scopes. **Automatic registration** requires provider support for public dynamic client registration. Otherwise use **Use an existing client ID** or **Use an existing client ID and secret**. Confidential clients require an explicit Basic or POST authentication method.
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

Your connector catalogue shows what your groups may access. Shared connector configuration is read-only for normal users; administrators manage the shared account and permissions.

For a Personal connector:

1. Open the connector's **Personal access** controls and choose **Enable access** for your account.
2. Choose **Sign in**, then complete the downstream provider's account selection and consent flow. Signing into Umbod alone does not authorize that provider.
3. Return to Umbod and check the saved authorization state. If the provider flow is still pending, complete or cancel that attempt before starting another.
4. After successful browser sign-in, Umbod attempts to load your personal tools automatically. Authorization and successful tool loading are separate states. If loading fails, follow **Retry loading tools**; use **Refresh tools** to rediscover later. Discovery saves a private inventory for your account, not a catalogue shared with other users.
5. Check for **Tools available** before using the connector through your MCP client. Your tools and downstream permissions are those of your own account.

### Manage your connection

| Action or state | Meaning |
| --- | --- |
| Check authorization status | Checks saved authorization records, not a live provider connection |
| Renew access | Explicitly refresh authorization where supported; sign in again if required |
| Refresh tools | Refreshes your private catalogue, including new downstream tools |
| Disable access | Stops personal access while retaining saved authorization |
| Disconnect | Removes saved authorization and disables access; a pending sign-in cannot restore it |

Umbod does not silently refresh credentials or retry a tool operation for you. Follow the displayed recovery action after expiry, authorization changes, or discovery failures. Disconnecting in Umbod does not promise provider-side token revocation; manage the provider's connected-app settings separately when needed.

If a connector disappears or stops working after an administrator changes publication, group access, or OAuth settings, contact your administrator. Personal authorization cannot bypass those controls. Previously saved connections can remain visible for cleanup after access is withdrawn.
