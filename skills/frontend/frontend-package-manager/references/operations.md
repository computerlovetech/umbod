---
type: Operational Reference
title: Package manager operations
description: Approved commands to run inside each target project's manifest folder.
---

# Package manager operations

Run every command from the respective project's manifest folder. The app folders are `umbod/frontend` for Node/TS and `umbod/api` for Python. Apply the same managers to all other and future projects.

## Bun: all Node/TS projects

| Operation | Command |
|---|---|
| Install dependencies | `bun install` |
| Add dependency | `bun add <pkg>` |
| Add development dependency | `bun add -d <pkg>` |
| Remove dependency | `bun remove <pkg>` |
| Update dependency | `bun update <pkg>` |
| Run script | `bun run <script>` |
| Run one-off binary | `bunx <command>`, never `npx` |

## uv: all Python projects

| Operation | Command |
|---|---|
| Install/sync from lockfile | `uv sync` |
| Add dependency | `uv add <pkg>` |
| Add development dependency | `uv add --dev <pkg>` |
| Remove dependency | `uv remove <pkg>` |
| Update specific dependency | `uv lock --upgrade-package <pkg> && uv sync` |
| Update all dependencies | `uv lock --upgrade && uv sync` |
| Run in project environment | `uv run <command>` |

Use Bun for Node/TS package operations and uv for Python. Do not hand-edit Python dependencies in pyproject.toml or uv.lock; use uv add or uv remove.
