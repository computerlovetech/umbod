# Umbod documentation

<div class="umbod-intro" markdown>

Connect your tools. Control agent access.

Install, configure, and run Umbod on your own infrastructure. Start with a local Kubernetes cluster, then connect your first API or MCP server.

[Install Umbod :material-arrow-right:](getting-started/kubernetes-installation.md){ .md-button .md-button--primary }
[Explore the architecture](operations/service-topology.md){ .umbod-secondary-link }

</div>

## Find your next step

<div class="grid cards" markdown>

-   :material-server-network: **Understand the deployment**

    Learn how services connect, where data lives, and which ports to expose.

    [Service topology :material-arrow-right:](operations/service-topology.md)

-   :material-tune: **Configure Umbod**

    Set up profiles, public origins, persistence, and secrets for your environment.

    [Configuration guide :material-arrow-right:](operations/configuration.md)

-   :material-puzzle-outline: **Build a connector**

    Create a connector plugin and deploy it with the versioned builder image.

    [Connector guide :material-arrow-right:](plugins/index.md)

-   :material-code-braces: **Look up a setting**

    Find chart defaults, configuration constraints, and connection addresses.

    [Helm values](reference/helm-values.md) · [Endpoints and ports](reference/endpoints-and-ports.md)

</div>

## Connect accounts and work with files

- [Shared and Personal connectors](using-umbod/connectors.md): administrator setup, user access, and personal account authorization.
- [Files](using-umbod/files.md): private uploads, folders, sharing, and agent access.
- [S3 file-content storage](operations/s3-file-storage.md): configure Helm deployments to keep file bytes in an S3 bucket.

## Early beta

Umbod is in early beta. These guides cover installation, everyday use, operations, and connector development. Questions or feedback? [Join the community on Discord](https://discord.gg/Njy4GnurpE) or [visit the source on GitHub](https://github.com/computerlovetech/umbod).

## About the name

Umbod takes its name from Old Norse *umboð*: a mandate to act on another’s behalf. Its theme song is [MMMBop by Hanson](https://www.youtube.com/watch?v=NHozn0YXAeE).
