# OpenAPI connectors

- `management/` owns connector configuration and current catalogue replacement.
- `importing/` validates source documents and builds endpoint capabilities.
- `stores/ports.py` defines connector and catalogue persistence contracts.
- `stores/service.py` implements backend-neutral persistence. `list_operations(connector_id)` reads the current header and its complete operation records in one session without loading source documents.
- `catalog/capability_catalog.py` normalizes persisted capabilities. `StoreBackedOpenApiCapabilityCatalog.list_connector_capabilities(connector)` reuses an already-loaded connector for administration catalogue reads. Authorized catalogue resolution retains its separate permission and availability checks.
- `execution/README.md` indexes authoritative operation execution.
