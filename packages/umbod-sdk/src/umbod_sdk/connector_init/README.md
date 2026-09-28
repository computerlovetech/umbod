# Connector initialization

Creates a Hello World connector module and adds its entry point to an existing explicit Hatch src-package project. Preview is read-only; apply rechecks the project before writing. Apply is not atomic across both files; on failure, inspect the reported paths rather than relying on automatic cleanup.

- `models.py` defines the request, snapshot, and complete plan.
- `port.py` defines project file operations and refusal errors.
- `adapters.py` provides in-memory and filesystem project file operations.
- `service.py` validates metadata and builds and applies the plan.
- `cli.py` exposes the init command, registered under the connectors group by the SDK CLI.
- `__init__.py` exposes the public planning interface and filesystem factory.
