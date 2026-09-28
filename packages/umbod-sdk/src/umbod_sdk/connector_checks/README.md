# Connector metadata checks

This module checks the connector entry-point declarations in a project's `pyproject.toml` without importing connector code.

- `models.py` defines validated read requests, content, and check results.
- `port.py` defines the metadata read contract and read errors.
- `readers.py` provides in-memory and filesystem implementations of the read contract.
- `checker.py` validates TOML entry-point names and module/export target syntax through the read contract.
- `cli.py` exposes the SDK `umbod connectors check` command.
- `__init__.py` exposes the public checking interface and filesystem-backed factory.

The check does not load connectors, validate connector IDs, or assess target-release compatibility.
