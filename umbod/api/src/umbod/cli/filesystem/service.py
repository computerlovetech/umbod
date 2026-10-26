from umbod.core.filesystem import RootBootstrapSpec
from umbod.core.persistence import PersistenceRuntimeProvider
from umbod.infrastructure import create_root_provisioning


async def bootstrap_root(
    spec: RootBootstrapSpec,
    provider: PersistenceRuntimeProvider,
) -> None:
    runtime = provider.create()
    try:
        await runtime.readiness.ensure_ready()
        await create_root_provisioning(database=runtime.database).provision(spec)
    finally:
        await runtime.shutdown()
