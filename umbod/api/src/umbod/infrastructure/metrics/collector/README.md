---
type: Software Module
title: "Collector metrics infrastructure"
description: "Prometheus collector observation recording and telemetry application composition."
---

# Files

- [__init__.py](./__init__.py) — Public collector recorder and telemetry application composition exports.
- [composition.py](./composition.py) — Isolated telemetry recorders and optional registry sharing with REST exposition.
- [prometheus.py](./prometheus.py) — Collector request counters, latency histograms and accepted-log counts.
