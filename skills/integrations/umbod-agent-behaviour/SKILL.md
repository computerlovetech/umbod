---
name: umbod-agent-behaviour
description: Use whenever encountering difficulties.
---

Discover Umbod's agent-behaviour playbooks at `umbod://agent-behaviour/playbooks` and read the selected playbook's current instructions before self-reporting obstacles.
Call `report_diagnostic` with `trigger=proactive` only when the playbook allows proactive reporting and the user and client authorize it, otherwise do not submit a report.
Follow the current reporting schema and privacy guidance, assess every selected pattern exactly once, and include only short factual summaries without transcripts, secrets, credentials, or hidden reasoning.
Generate one UUID idempotency key before submission, retry uncertain outcomes only with the identical payload and key, and claim success only after receiving a durable receipt.
