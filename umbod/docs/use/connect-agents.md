---
description: Connect Codex, Claude Code, or any MCP client to Umbod and check that tools appear.
---

# Connect an agent

Each user connects their own agent. There are two ways: the installer for Codex and Claude Code, or the MCP endpoint for any other client.

## With the installer

1. Open **Getting started** in the workspace.
2. Choose your platform, then **Codex** or **Claude Code**.
3. Copy the command and run it in a terminal.
4. Restart the agent, open `/mcp`, and sign in with your Umbod account.

**Check:** the agent lists a tool your group has access to.

The installer adds the Umbod MCP connection and the `run-diagnostics` skill. It needs no administrator rights and stores no credentials.

| Platform | Requires |
| --- | --- |
| macOS, Linux, WSL | Bash, curl, Python 3.8 or newer |
| Windows | PowerShell 5.1 or newer |

To upgrade, run the current command from **Getting started** again and restart the agent.

## With any MCP client

Add this URL as a remote HTTP MCP server and sign in when the client asks:

```text
https://<your-umbod-host>/mcp
```

## Send agent logs to Umbod

If **Set up telemetry** is shown in the installer, choose **With telemetry** before you copy the command. The command then contains a one-time credential, so do not share it. The terminal shows the exporter settings and asks before it saves them.

An administrator must [enable collection](../self-host/telemetry.md) first.

## If it does not work

| Symptom | Fix |
| --- | --- |
| Sign-in fails | Ask your administrator to check the public addresses and [sign-in routes](../self-host/install.md#3-put-a-sign-in-gateway-in-front) |
| No tools appear | Your group has no access yet. See [why a user cannot see a tool](connectors.md#when-a-user-cannot-see-or-use-a-tool) |
| The skill is missing | Start a new session and check that the plugin is enabled in `/plugins` |
| The installer stops with a conflict | An older Umbod connection or plugin exists. Remove it as the installer describes, then run the command again |
| `codex plugin` is not a command | Update Codex. The installer was verified with Codex CLI 0.167.0 |
