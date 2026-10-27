---
name: write-module-readme
description: Use when creating, editing, or reviewing module-level README.md files, or updating module indexes after files are added, renamed, moved, or removed. Enforces title frontmatter and a file table of contents only, with no prose duplicating the code.
---

# Write module README indexes

## Hard rule

A module-level `README.md` is only a navigation index, not documentation about the module. It contains YAML frontmatter with a single `title` field, followed by a Markdown bullet list of relative links to module files. Nothing else.

Agents consult this index when unsure whether a file is relevant to their search, before deciding to read it. The code is the source of information about behavior and implementation.

## Procedure

1. Inspect the module's actual files and any existing index. Read code only as needed to identify accurate link labels.
2. Set `title` to the module name.
3. List the module's direct files, excluding `README.md` itself, generated files, caches, and build artifacts. Link to each child module's `README.md` rather than flattening its files into the parent index. Do not invent links to missing indexes.
4. Use the filename as the link label. Only when the filename is ambiguous, append a few identifying words within the label to help an agent select the file. Do not add descriptions after links.
5. Remove all other content, including module overviews, architecture explanations, behavior summaries, API or symbol inventories, dependencies, workflows, setup commands, examples, and testing instructions. Do not replace it with shorter explanatory prose.
6. Verify that every relative link resolves and that added, renamed, moved, or removed files are reflected in the index.

## Required format

```markdown
---
title: Permissions
---

- [__init__.py](./__init__.py)
- [models.py](./models.py)
- [service.py](./service.py)
- [adapters](./adapters/README.md)
```

The paths above illustrate the format; use only paths that exist in the target module.

## Scope

Apply this rule to module-level indexes, not repository landing pages, product documentation, architecture decision records, or `SKILL.md` instructions. Do not move redundant code explanations into another document merely to preserve them.

## Completion check

- Frontmatter contains only `title`.
- The body contains only linked table-of-contents entries.
- Links resolve, labels are concise, and the index matches the module files.
- No prose explains information that can be found by reading the code.
