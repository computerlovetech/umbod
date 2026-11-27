---
description: Add an OpenAPI or MCP connector, publish it, and grant groups access.
---

# Connectors

A connector gives agents tools from an API or an MCP server. Every connector follows the same three steps: add it, publish it, and grant a group access. Nothing is visible to anyone until all three are done.

| You have | Add |
| --- | --- |
| An HTTP API with an OpenAPI description | [An OpenAPI connector](#add-an-api) |
| An MCP server | [An MCP connector](#add-an-mcp-server) |
| Neither | [A custom connector plugin](../extend/build-a-connector.md) |

You need to be an administrator. All steps start in **Administration → Connectors**.

## Add an API

1. Choose **Add connector**, then **OpenAPI specification**.
2. Upload the OpenAPI JSON file or enter its HTTPS URL.
3. Approve the hostname the connector may call. Add authentication if the API needs it.
4. Enable the tools you want to offer.
5. Publish the connector.
6. In **Administration → Permissions**, select a group and grant it the connector.

**Check:** sign in as a member of that group, [connect an agent](connect-agents.md), and confirm it lists the tools.

## Add an MCP server

First choose how users reach the server:

| | Shared | Personal |
| --- | --- | --- |
| Account on the server | One, set up by you | Each user signs in with their own |
| Tools | You choose which are active | Everything the server offers that user |
| User setup | None | **Enable access**, then **Sign in** |

### Shared

1. Choose **Add connector**, then **MCP server**, and choose **Shared**.
2. Find the server in the MCP Registry or enter its endpoint URL. Add the shared credentials.
3. Discover the tools and activate the ones you want to offer.
4. Publish the connector.
5. In **Administration → Permissions**, grant a group the connector and its tools.

### Personal

1. Choose **Add connector**, then **MCP server**, and choose **Personal**.
2. Find the server in the MCP Registry or enter its name and endpoint URL. These cannot be changed later.
3. Choose how Umbod registers with the server's OAuth provider:

    | Option | Use when |
    | --- | --- |
    | **Automatic registration** | The provider supports dynamic client registration |
    | **Use an existing client ID** | You registered a public client yourself |
    | **Use an existing client ID and secret** | You registered a confidential client yourself |

    With an existing client, register the callback URI Umbod shows you with the provider.

4. Publish the connector.
5. In **Administration → Permissions**, grant a group the connector.

!!! warning "A Personal grant covers every tool"
    Users in the group can use all tools the server exposes to them, including tools it adds later. Only register servers you trust.

Each user then opens **Connectors**, chooses **Enable access**, and signs in to the server.

**Check:** as a group member, the connector shows **Tools available** after sign-in.

Self-hosting? Personal connectors need [one extra setting](../self-host/operate.md#personal-connectors).

## Change or remove access

| Action | Effect |
| --- | --- |
| Remove a group grant or unpublish | Users lose the tools immediately. Their accounts on the server are not signed out |
| Change OAuth settings on a Personal connector | Every user must sign in again |
| Delete a connector | Remove its group grants first, or deletion is blocked |

## When a user cannot see or use a tool

Check in this order:

1. The connector is published.
2. The user's group has a grant in **Administration → Permissions**.
3. For Shared: the tool is activated.
4. For Personal: the user chose **Enable access** and signed in, and the connector shows **Tools available**. If not, they choose **Retry loading tools**.
5. The sign-in has not expired. Umbod does not renew it silently: the user chooses **Renew access** or signs in again.

**Disconnect** removes a user's saved sign-in from Umbod. It does not revoke the token at the provider. Do that in the provider's own connected-apps settings.
