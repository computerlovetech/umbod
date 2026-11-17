---
type: Security Policy
title: Umbod security reporting
description: Private vulnerability reporting instructions and report template.
---

# Security reporting

Do not report suspected vulnerabilities through public issues, pull requests, or Discord messages.

Use [GitHub private vulnerability reporting](https://github.com/computerlovetech/umbod/security/advisories/new) and copy the [security report template](security-report-template.md) into the report description. GitHub's private reporting form is separate from public issue forms; the template is guidance, not enforced validation.

If the private reporting form is unavailable, ask a maintainer to enable it through [Discord](https://discord.gg/Njy4GnurpE). Make only a request for a private reporting channel; do not share vulnerability details, affected deployments, exploit code, or sensitive attachments there.

Test only systems you own or have explicit permission to assess. Use synthetic data and minimal proofs of concept. Never include live credentials, tokens, personal data, or customer payloads, even in a private report.

Please keep vulnerability details private while maintainers assess the report and coordinate remediation and disclosure with you.

## Reference

This reporting approach follows the [OpenSSF vulnerability disclosure guide for maintainers](https://github.com/ossf/oss-vulnerability-guide/blob/main/maintainer-guide.md) and [GitHub's private vulnerability reporting guidance](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository).
