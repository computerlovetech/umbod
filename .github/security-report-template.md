---
type: Security Report Template
title: Umbod private security report
description: Structured details to include in a private vulnerability report.
---

# Security report template

Use this structure only in a [private vulnerability report](https://github.com/computerlovetech/umbod/security/advisories/new), following the [security policy](SECURITY.md). Do not submit it as a public issue.

## Summary

Describe the suspected vulnerability and the affected Umbod component.

## Affected versions and environment

Include the release or commit, chart and image versions where relevant, deployment method, and relevant configuration. State whether other versions were tested. Remove secrets and private infrastructure identifiers.

## Prerequisites and attack scenario

Describe the access, permissions, authentication state, configuration, and user interaction needed to exploit the issue.

## Reproduction or proof of concept

Provide minimal reproduction steps using synthetic data on a system you own or are authorized to test. Include sanitized requests or attachments only when necessary.

## Expected and actual security behavior

Describe the security boundary that should hold and what happens instead.

## Impact

Explain what an attacker could access or change, who is affected, and any known limitations. Distinguish demonstrated impact from suspected impact.

## Mitigation

Describe any known workaround or mitigation. If none is known, say so.

## Coordination and credit

Optionally state your preferred attribution, any existing disclosure timeline, and whether you have reported this elsewhere. Use the private report thread for follow-up.
