# Connector metadata checks

This module checks the connector entry-point declarations in a project's `pyproject.toml` without importing connector code.

- `models.py` defines validated read requests, content, and check results.
- `port.py` defines the metadata read contract and read errors.
- `readers.py` provides in-memory and filesystem implementations of the read contract.
- `checker.py` validates TOML entry-point names and module/export target syntax through the read contract.
- `compatibility.py` checks declared SDK requirements and defines release metadata and compatibility ports with an in-memory release adapter.
- `registry.py` reads and validates synchronized SDK labels from core and builder OCI metadata, including supported platform manifests and blob digests.
- `registry_transport.py` provides bounded HTTP metadata reads with scoped anonymous authentication and restricted, credential-free redirects.
- `cli.py` exposes the SDK `umbod connectors check` command, with mutually exclusive `--target` and `--sdk-version` options.
- `__init__.py` exposes the public checking interface and filesystem-backed factory.

The default check is offline and metadata-only. Explicit SDK checks compare declarations without verifying an image. Target checks require published synchronized SDK labels; they do not infer SDK versions for older releases. No mode loads connectors, validates connector IDs, or proves runtime or external-service compatibility.
