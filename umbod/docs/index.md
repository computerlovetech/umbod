---
description: What Umbod is and where to start.
---

# Umbod documentation

Umbod gives your AI agents one MCP endpoint for your company's APIs, MCP servers, and shared files. An administrator decides which tools exist and which groups can use them.

## Start here

| You want to | Go to |
| --- | --- |
| Try Umbod on your own computer | [Try it locally](self-host/local.md) |
| Run Umbod for your organization | [Install for a team](self-host/install.md) |
| Set up a workspace that is already running | [Set up a workspace](#set-up-a-workspace) |

## Set up a workspace

These steps are the same whether Umbod is hosted for you or you host it yourself.

1. [Add a connector](use/connectors.md) for an API or an MCP server, and grant a group access.
2. [Connect an agent](use/connect-agents.md) and check that it sees the tools.
3. Optional: [share files](use/files.md) between people and agents.
4. Optional: [see what agents do](use/insights.md).

## How it fits together

| Term | Meaning |
| --- | --- |
| Connector | A source of tools: an OpenAPI description, an MCP server, or a [custom plugin](extend/build-a-connector.md). |
| Group | A group from your identity provider. Access is always granted to groups. |
| Administrator | A member of the configured administrator group. Sees **Administration** in the workspace. |
| Namespace | A file workspace: personal (**My files**) or shared with groups. |
| MCP endpoint | The one URL agents connect to: `https://<your-umbod-host>/mcp`. |

## For agents

Every page is also published as Markdown: replace the trailing `/` of its URL with `.md`. <a href="llms.txt"><code>llms.txt</code></a> lists all pages, and <a href="llms-full.txt"><code>llms-full.txt</code></a> holds them in one file.

## Early beta

Chart `{{ release.chartVersion }}` and images `{{ release.imageTag }}`. The chart runs one replica on SQLite and is not highly available. Ask questions on [Discord](https://discord.gg/Njy4GnurpE) or read the [source on GitHub](https://github.com/computerlovetech/umbod).
