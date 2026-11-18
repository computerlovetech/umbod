---
type: Software Module
title: "REST metrics infrastructure"
description: "Prometheus REST request recording and dedicated scrape listener composition."
---

# Files

- [__init__.py](./__init__.py) — Public recorder, scrape listener and composition exports.
- [composition.py](./composition.py) — Isolated recorder and scrape listener factories.
- [prometheus.py](./prometheus.py) — REST request counters, histograms and runtime collectors.
- [http_server.py](./http_server.py) — Dedicated scrape endpoint and supervised listener lifecycle.
