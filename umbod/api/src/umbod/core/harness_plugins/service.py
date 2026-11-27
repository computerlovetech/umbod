import hashlib
from io import BytesIO
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from umbod.core.harness_plugins.ports import PackageResourceReader
from umbod.core.harness_plugins.rendering import Harness, marketplace_name, normalize_endpoint, render_package


class HarnessPackageService:
    def __init__(self, endpoint: str, resources: PackageResourceReader) -> None:
        self.endpoint = normalize_endpoint(endpoint)
        self.marketplace = marketplace_name(self.endpoint)
        self._resources = resources

    def package(self, harness: Harness) -> bytes:
        resources = self._resources.read()
        entries = render_package(
            self.endpoint, resources.license_text, harness, resources.run_diagnostics_skill,
        )
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_STORED) as archive:
            for name, content in sorted(entries.items()):
                entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, content.encode("utf-8"))
        return buffer.getvalue()

    def checksum(self, harness: Harness) -> str:
        return hashlib.sha256(self.package(harness)).hexdigest()
