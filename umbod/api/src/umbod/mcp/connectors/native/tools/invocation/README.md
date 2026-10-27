# Native invocation

`ports.py` defines invoker and fresh execution-admission contracts. `runner.py` prepares arguments, runs the existing validation/policy pipeline, then invokes the injected admission callback immediately before native connector I/O. Admission failures remain generic and are not classified as connector-origin exceptions.

`runtime/registry.py` composes admission from freshly captured caller membership, current grants, publication, configuration readiness and activation. `registration.py` injects this callback into flat/file-tool runners as well as gateway and code-mode runners, so retained tool objects cannot bypass current authority after approval. Code mode converts failed native results into generic failed nested calls instead of successful empty values.

`arguments.py` resolves nullable arguments; `errors.py` defines public failure formatting and the failure-result adapter. Native operation exceptions alone receive connector-origin evidence.
