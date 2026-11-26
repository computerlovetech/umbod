# Umbod documentation

<div class="umbod-intro" markdown>

Connect your agents to apps and files

Use an existing Umbod workspace to connect an agent, share access to apps and files, or turn on agent diagnostics.

[Choose a task :material-arrow-right:](#choose-a-task){ .md-button .md-button--primary }
[Install Umbod](getting-started/kubernetes-installation.md){ .umbod-secondary-link }

</div>

## Choose a task

<div class="grid cards" markdown>

-   :material-server-network: **Connect an agent**

    Sign in and discover tools. Use the Codex installer on supported releases, or connect your client to MCP directly.

    [Install for Codex](using-umbod/codex-plugin.md) · [Connect directly](operations/service-topology.md)

-   :material-puzzle-outline: **Connect an app**

    Publish an OpenAPI or MCP connector and give the right groups access.

    [Set up connectors :material-arrow-right:](using-umbod/connectors.md)

-   :material-folder-outline: **Share files**

    Give a group a shared workspace or grant access to just one file or folder.

    [Share files and folders :material-arrow-right:](using-umbod/files.md#share-files-and-folders)

-   :material-clipboard-check-outline: **Enable agent diagnostics**

    On releases with Agent diagnostics, set up a playbook so signed-in agents can submit reports.

    [Enable diagnostic reporting :material-arrow-right:](operations/configuration.md#diagnostic-reporting)

</div>

## Deploy and operate Umbod

- [Install on Kubernetes](getting-started/kubernetes-installation.md), then [configure sign-in and persistence](operations/configuration.md).
- [Connect clients and configure routing](operations/service-topology.md).
- [Store files in S3](operations/s3-file-storage.md), [collect agent telemetry](operations/telemetry-ingestion.md), or [schedule cleanup](operations/cleanup.md).
- [Troubleshoot service and tool failures](operations/application-diagnostics.md).

## Look up a setting or contract

[Helm values](reference/helm-values.md) · [Built-in MCP tools](reference/built-in-tools.md) · [Build a connector plugin](plugins/index.md)

## Early beta

The [installation guide](getting-started/kubernetes-installation.md) uses published chart `{{ release.chartVersion }}` and images `{{ release.imageTag }}`. Some guides describe newer features and call out when those releases lack support. The chart is for evaluation, not high availability. Questions or feedback? [Join the community on Discord](https://discord.gg/Njy4GnurpE) or [visit the source on GitHub](https://github.com/computerlovetech/umbod).
