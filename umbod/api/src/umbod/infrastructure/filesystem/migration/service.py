from contextlib import aclosing
from hashlib import sha256

from umbod.core.filesystem import StorageFailure

from .ports import Fingerprint, MigrationSource, MigrationStream, MigrationSummary, MigrationTarget


async def fingerprint(stream: MigrationStream) -> Fingerprint:
    digest = sha256()
    size = 0
    async with aclosing(stream):
        async for chunk in stream:
            if not isinstance(chunk, bytes):
                raise StorageFailure("Content stream must yield bytes")
            digest.update(chunk)
            size += len(chunk)
    return Fingerprint(size=size, sha256=digest.hexdigest())


async def migrate_content(
    source: MigrationSource, target: MigrationTarget, dry_run: bool,
) -> MigrationSummary:
    listing = await source.list_keys()
    copied = skipped = planned = total_bytes = 0
    for key in listing.keys:
        expected = await fingerprint(source.get(key))
        total_bytes += expected.size
        if await target.exists(key):
            if await fingerprint(target.get(key)) != expected:
                raise StorageFailure("Migration destination content conflicts with source")
            skipped += 1
        elif dry_run:
            planned += 1
        else:
            async with aclosing(source.get(key)) as stream:
                await target.write_at(key, stream)
            if await fingerprint(target.get(key)) != expected:
                raise StorageFailure("Migration destination verification failed")
            copied += 1
    return MigrationSummary(
        copied=copied, skipped=skipped, planned=planned, total_bytes=total_bytes,
    )
