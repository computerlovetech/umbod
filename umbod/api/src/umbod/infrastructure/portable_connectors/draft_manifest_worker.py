from json import loads
from sys import stdin

from umbod.core.connectors.portable.ports import PortableExecutionError
from umbod.core.connectors.portable.validation import check_manifest_handlers, read_manifest

MAX_MANIFEST_FRAME_BYTES = 1024 * 1024
INVALID_MANIFEST_EXIT_CODE = 2


def main() -> int:
    payload = stdin.buffer.read(MAX_MANIFEST_FRAME_BYTES + 1)
    if len(payload) > MAX_MANIFEST_FRAME_BYTES:
        return INVALID_MANIFEST_EXIT_CODE
    try:
        check_manifest_handlers(read_manifest(loads(payload)))
    except (ValueError, PortableExecutionError):
        return INVALID_MANIFEST_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
