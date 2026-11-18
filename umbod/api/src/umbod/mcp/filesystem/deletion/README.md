---
type: Software Module
title: "Filesystem deletion"
description: "Human approval and revision-checked file deletion."
---

# Files

- [__init__.py](./__init__.py) — Public deletion tool, approval and command exports.
- [tool.py](./tool.py) — Human-approved, revision-checked removal of one file and its policies, never directories or stored bytes.
- [approval.py](./approval.py) — Mandatory human deletion confirmation through elicitation or signed, single-use continuations.
- [approval_state.py](./approval_state.py) — Expiring deletion approval bound to the authenticated caller, client, file and revision.
- [models.py](./models.py) — Deletion command, human confirmation and result contracts.
- [ports.py](./ports.py) — Mandatory human deletion approval contract.
