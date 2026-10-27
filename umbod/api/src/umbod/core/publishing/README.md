# Publishing

- `store.py`: domain contracts including narrow snapshot read ports.
- `stores/schema.py`: backend-neutral typed storage schema.
- `stores/service.py`: persistent store operations.
- `stores/reads.py`: pure planned bulk reads and execution-local publication state readers. IDs are deduplicated and sorted; each query selects at most 200 connector IDs to stay conservatively below portable parameter limits. Empty inputs register no queries. Snapshot readers never fall back to persistence.
