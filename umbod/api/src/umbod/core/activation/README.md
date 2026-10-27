# Activation

- `domain.py`: domain contracts including narrow snapshot read ports.
- `stores/schema.py`: backend-neutral typed storage schema.
- `stores/service.py`: persistent store operations.
- `stores/reads.py`: pure planned bulk reads and execution-local activation status readers. IDs are deduplicated and sorted; each query selects at most 200 connector IDs to stay conservatively below portable parameter limits. Empty inputs register no queries. Kind predicates use the existing compound primary key instead of scanning the activation table. Snapshot readers preserve complete kind-qualified identities and never fall back to persistence.
