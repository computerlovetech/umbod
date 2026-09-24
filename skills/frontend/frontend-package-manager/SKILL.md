---
name: frontend-package-manager
description: >-
  Enforce what package managers to use for this repository. Use when installing dependencies, running package scripts, adding or removing packages, lockfile updates.
---

# Repository package managers

## Rule

- Use **Bun** for all package-manager operations in `frontend/` (TypeScript; `package.json`).
- Use **uv** for all package-manager operations in `api/` (Python; `pyproject.toml`, `uv.lock`).

Always run commands from inside the respective project folder so the correct manifest and lockfile are used.

## Frontend (`frontend/`) — Bun

| Task | Use |
|------|-----|
| Install dependencies | `bun install` |
| Add dependency | `bun add <pkg>` |
| Add dev dependency | `bun add -d <pkg>` |
| Remove dependency | `bun remove <pkg>` |
| Update dependency | `bun update <pkg>` |
| Run a script | `bun run <script>` |
| Run a one-off binary | `bunx <command>` (not `npx`) |

Example:

```bash
cd frontend && bun install
cd frontend && bun run lint
```

### Do not (frontend)

- Do not use `npm`, `yarn`, `pnpm`, `npx`, or `corepack`.

## API (`api/`) — uv

| Task | Use |
|------|-----|
| Install/sync dependencies from lockfile | `uv sync` |
| Add dependency | `uv add <pkg>` |
| Add dev dependency | `uv add --dev <pkg>` |
| Remove dependency | `uv remove <pkg>` |
| Update a specific dependency | `uv lock --upgrade-package <pkg> && uv sync` |
| Update all dependencies | `uv lock --upgrade && uv sync` |
| Run a command in the project env | `uv run <command>` |

Example:

```bash
cd api && uv sync
cd api && uv add httpx
cd api && uv remove httpx
cd api && uv run pytest
```

### Do not (api)

- Do not use `pip`, `pip-tools`, `poetry`, `pipenv`, `conda`, or edit `uv.lock` by hand.
- Do not edit `pyproject.toml` dependencies manually — use `uv add` / `uv remove` so the lockfile stays in sync.

## General

If another `package.json` or `pyproject.toml` is added under this repo later, treat it the same way: **Bun only** for Node/TS projects, **uv only** for Python projects.
