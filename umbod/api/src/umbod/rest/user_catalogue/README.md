# User catalogue REST boundary

`GET /api/me/catalogue` is authenticated independently of administrator membership and personal feature enablement. Responses are no-store and contain only opaque identity, personal support, connector summaries and permitted capability display metadata.

- `routes.py`: typed read-only endpoint.
- `caller.py`: required-field typed catalogue capture of caller, strict groups, precomputed identity key and explicit personal identity resolution; raw claim handling stays here.
- `dependencies.py`: request-scoped cross-kind assembly from typed captured inputs, persisted current grants and runtime availability gates.
- `identity.py`: stable SHA256 verified identity projection and bounded local development simulation policy.
- `projection.py`: public-name ambiguity and personal namespace reservation filtering. Gateway and codemode configured-name failures suppress all tools, including otherwise healthy sources; flat mode retains provider-specific filtering. Native gateway claims include unpublished configured names. Empty normalized personal namespaces never advertise tools, while eligible personal entries remain visible.

Personal sources are resolved only when support is enabled and verified claims map to a canonical owner. Failure to map an owner does not deny shared reads. Personal observations are read without refresh, discovery or invocation; OAuth/runtime enablement gates tools independently of personal selection.
