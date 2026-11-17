---
name: frontend-package-manager
description: >
  Enforce repository package managers. Use when installing, adding, removing, updating dependencies or lockfiles, running package scripts, or invoking project tools.
---

# Repository package managers

## Outcome

All dependency and tool operations use the correct manager, project manifest, and lockfile.

## Inputs

- Required: Target project folder and requested dependency or command operation.
- Optional: Dependency version, development scope, and script arguments.
- Default: Bun for ALL Node/TS projects; uv for ALL Python projects, including future projects.

## Rules

- R1: Run every command inside its respective project folder: app paths from repository root are `umbod/frontend` and `umbod/api`; other projects use their own manifest folders.
- R2: Use only Bun for Node/TS and uv for Python. Do not hand-edit Python dependencies in `pyproject.toml` or `uv.lock`; use uv commands.
- R3: Never use `npm`, `yarn`, `pnpm`, `npx`, or `corepack` for Node/TS; never use `pip`, `pip-tools`, `poetry`, `pipenv`, or `conda` for Python.

## Workflow

1. Locate the target manifest and enter its project folder before running commands.
2. Read the operation reference and select the Bun or uv operation for that project.
3. Execute the requested operation through that manager; let it maintain dependencies and lockfiles.
4. Check command exit status and the manifest/lockfile diff; verify requested changes and preserve unrelated work.

## Decisions

| Condition | Action |
|---|---|
| Target folder or operation is unclear | Infer from the request and workspace; ask only if materially ambiguous. |
| Dependency scope is unspecified | Infer runtime or development scope from usage; ask if ambiguous rather than defaulting to runtime. |
| Command or diff verification fails | Diagnose within the same project and retry using only its approved manager. |
| Recovery fails | Report the failure; do not switch managers or hand-edit Python dependencies or uv.lock. |

## Output

Return:
- Project folder, manager, operation, and changed files.
- Command exit status and manifest/lockfile verification result.
- Unresolved failures or missing inputs.

## Completion criteria

- Requested operations succeeded inside the correct project using only Bun or uv.
- Manifest and lockfile changes are consistent; Python dependency edits use uv.

## References

- Read `references/operations.md` when choosing dependency, script, or one-off tool commands.
