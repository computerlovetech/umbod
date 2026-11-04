from pathlib import Path

from ..config import S3ContentConfig
from .ports import MigrationSummary


async def migrate_local_content(
    source: Path, target: S3ContentConfig, dry_run: bool,
) -> MigrationSummary:
    from ..s3.edge import SDKClientProvider
    from .adapters import LocalMigrationSource, S3MigrationTarget
    from .service import migrate_content

    return await migrate_content(
        LocalMigrationSource(source), S3MigrationTarget(target, SDKClientProvider(target)), dry_run,
    )


__all__ = ["migrate_local_content"]
