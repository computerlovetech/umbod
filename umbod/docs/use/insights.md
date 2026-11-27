---
description: See what agents do in Umbod, read the log reports, and turn on agent diagnostics.
---

# Insights

See what agents do, and let them report problems they run into.

## See activity

| View | Shows | Where |
| --- | --- | --- |
| Your own activity | Your agents' harness and MCP activity for 7 or 30 days | **Dashboard** |
| Your own logs | Reports and queries over your own logs | **Insights → Log analytics** |
| Everyone's logs | The same reports for the whole workspace | **Administration → Insights → Log analytics** |

Log reports need agents to [send their logs](connect-agents.md#send-agent-logs-to-umbod) and, when you self-host, [collection to be enabled](../self-host/telemetry.md).

## Read a report

Choose a report and a time range, then run it. Reports do not refresh on their own. Select a session in the results to narrow the report to it.

| Report | Counts |
| --- | --- |
| **Tool calls** | Completed tool calls, by outcome: success, failure, or unknown |
| **File activity** | Calls to read and edit tools. Calls, not distinct files |
| **Skill activity** | Skill activations |
| **Log classifications** | All stored logs, by kind. Use it to inspect what was received |
| **Custom log query** | Any grouping and filter you choose, optionally per minute, hour, or day |

What the numbers mean:

- Counts are log records agents sent. They are not tokens or costs.
- An exporter that retries can send a record twice, and it is counted twice.
- An empty report means no matching logs arrived. It does not prove the agent did nothing.
- Times are UTC.

## If a report is empty

1. Check that the time range covers a period when the agent was running.
2. Check that the agent exports logs: install it [with telemetry](connect-agents.md#send-agent-logs-to-umbod).
3. Open **Log classifications** for the same range. If logs are there but unclassified, the agent's version does not send recognizable tool events.
4. An error instead of an empty table means analytics is off or failing. See [Collect telemetry](../self-host/telemetry.md).

## Agent diagnostics

With diagnostics on, an agent can file a report when it hits an obstacle in Umbod, following a playbook you write.

1. Open **Administration → System settings → Agent diagnostics**.
2. Enable reporting.
3. Enable a playbook with at least one enabled pattern.

**Check:** ask a connected agent to submit a test diagnostic report. It answers with a `report_id`.

Reports appear under **Administration → Insights**. They are deleted after 30 days. Turning reporting off stops new reports and keeps the existing ones and the playbook.
