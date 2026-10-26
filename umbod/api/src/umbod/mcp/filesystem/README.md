# MCP filesystem

Thin MCP adapters for core filesystem browsing and empty node creation. All five tools remain available at the root endpoint in flat, gateway, and codemode connector exposure modes. Connector-scoped proxy paths neither list nor admit filesystem tools; request-local scope checks do not change node authorization.

## Module index

- `authorization.py`: root-only per-tool visibility and invocation admission using the existing request connector scope.
- `registration.py`: publishes five tools through `McpObservedToolRegistrar`, preserving schema validation, metrics, audit, and framework error handling.
- `ports.py`: caller capture, group claim field source, and operation-local service factory protocols.
- `caller.py`: captures one access token per invocation and assembles one immutable caller snapshot.
- `claim_fields.py`: runtime source reads the active permission state's claim fields on every capture; static source supplies the configured fallback when composition has no runtime state.
- `factory.py`: creates fresh core services through public infrastructure factories over the prepared application database.
- `models.py`: children response envelope and strict transport metadata input.
- `errors.py`: fixed public error translation, including subclasses of expected domain errors.

## Tool contracts

`get_filesystem_root` takes no arguments. `get_filesystem_node` requires `node_id: UUID`. `list_filesystem_children` requires `parent_id: UUID` and returns `{nodes: [NodeSummary, ...]}`.

`create_filesystem_file` and `create_filesystem_directory` require `parent_id: UUID`, `name: str`, and `metadata: NodeMetadata`. Creation produces empty private nodes. Caller identity, ownership, grants, and content are not accepted tool inputs. Unknown tool arguments and undeclared metadata fields are rejected before invocation. Metadata attributes remain ordinary string data and never confer authority.

Root, node, and creation results are safe `NodeSummary` objects with no content storage keys, ownership, or grants. Browsing tools are read-only and idempotent; creation tools are non-idempotent and do not overwrite existing nodes.

## Errors

Missing and denied nodes both produce `filesystem_permission_denied: Filesystem access denied`. Other expected errors produce `filesystem_invalid_name: Invalid filesystem name`, `filesystem_name_collision: Filesystem name already exists`, `filesystem_wrong_node_kind: Invalid filesystem node kind`, or `filesystem_storage_failure: Filesystem storage unavailable`. These messages never include exception details. Unexpected exceptions, including arbitrary service-raised ToolError values, produce `filesystem_operation_failed: Filesystem operation failed`. The entire invocation operation is guarded, including caller capture and service construction; cancellation propagates unchanged.

## Snapshot and lifetime

Each invocation reads the current token exactly once. Caller provenance comes from the actual server authentication provider, never token claims. Membership uses the shared runtime group capture wrapper and the explicit claim field source. Core's verified identity resolver retains authority; local-test, deployment-only, and unavailable identities remain denied.

Registration retains only infrastructure, factories, and capture adapters. Application services, callers, and database sessions are never cached across invocations. Core owns authorization, list filtering, name validation, ownership, and persistence. No content driver or content configuration is needed.

## Bootstrap limitation

These tools neither provision a root nor grant access. An operator must bootstrap the system-owned root and initial discover/write grants through the separate provisioning boundary before clients can use the tools. There is no public MCP bootstrap tool.
