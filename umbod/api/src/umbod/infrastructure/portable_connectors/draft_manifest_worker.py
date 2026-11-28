from json import loads
from sys import stdin, stdout

from umbod.core.connectors.portable.draft_validation.models import ValidatedManifestSnapshot
from umbod.core.connectors.portable.ports import PortableExecutionError
from umbod.core.connectors.portable.validation import check_manifest_handlers, json_snapshot, read_manifest

MAX_MANIFEST_FRAME_BYTES = 1024 * 1024
INVALID_MANIFEST_EXIT_CODE = 2


def main() -> int:
    payload = stdin.buffer.read(MAX_MANIFEST_FRAME_BYTES + 1)
    if len(payload) > MAX_MANIFEST_FRAME_BYTES:
        return INVALID_MANIFEST_EXIT_CODE
    try:
        manifest = read_manifest(loads(payload))
        check_manifest_handlers(manifest)
        snapshot = ValidatedManifestSnapshot(
            manifest_version=manifest["manifest_version"],
            connector_id=manifest["connector_id"],
            display_name=manifest["display_name"],
            description=manifest["description"],
            configuration_schema_json=json_snapshot(manifest["configuration_schema"]),
        )
        frame = json_snapshot(snapshot.model_dump()).encode("ascii")
    except (ValueError, PortableExecutionError):
        return INVALID_MANIFEST_EXIT_CODE
    if len(frame) > MAX_MANIFEST_FRAME_BYTES:
        return INVALID_MANIFEST_EXIT_CODE
    stdout.buffer.write(frame)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
