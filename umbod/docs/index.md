# Umbod documentation

<div class="umbod-intro" markdown>

Install and run Umbod

This guide is for administrators. Learn how to install Umbod, connect internal tools, and decide which groups can use them. Try it on your computer before setting up a shared Kubernetes installation.

[Install Umbod :material-arrow-right:](getting-started/kubernetes-installation.md){ .md-button .md-button--primary }
[See how it runs](operations/service-topology.md){ .umbod-secondary-link }

</div>

## Find your next step

<div class="grid cards" markdown>

-   :material-server-network: **Understand the deployment**

    Learn how services connect, where data lives, and which ports to expose.

    [Services and storage :material-arrow-right:](operations/service-topology.md)

-   :material-tune: **Configure Umbod**

    Set the URLs people and agents use, configure sign-in, and keep data across restarts.

    [Configuration guide :material-arrow-right:](operations/configuration.md)

-   :material-puzzle-outline: **Connect tools and grant access**

    Decide whether to use a shared connection or let users connect their own accounts.

    [Connector setup :material-arrow-right:](using-umbod/connectors.md)

-   :material-code-braces: **Look up a setting**

    Find Helm setting names and defaults, or check what a built-in MCP tool accepts and returns.

    [Helm values](reference/helm-values.md) · [Built-in MCP tools](reference/built-in-tools.md)

</div>

## Run and maintain Umbod

- [Endpoints and ports](operations/endpoints-and-ports.md): check which addresses to expose and which to keep private.
- [Files](using-umbod/files.md): understand upload limits, sharing, and agent access.
- [S3 file storage](operations/s3-file-storage.md): store file contents in an S3 bucket without replacing the application database.
- [Scheduled cleanup](operations/cleanup.md): set up regular removal of expired records.
- [Application diagnostics](operations/application-diagnostics.md): find and interpret service logs.
- [Connector plugins](plugins/index.md): build and deploy a custom connector when you need one.

## Early beta

Umbod is in early beta. The current Helm chart is for evaluation, not a highly available deployment. Questions or feedback? [Join the community on Discord](https://discord.gg/Njy4GnurpE) or [visit the source on GitHub](https://github.com/computerlovetech/umbod).

## About the name

Umbod takes its name from Old Norse *umboð*: a mandate to act on another’s behalf. Its theme song is [MMMBop by Hanson](https://www.youtube.com/watch?v=NHozn0YXAeE).
