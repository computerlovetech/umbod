from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit

from umbod.core.connectors.openapi.importing.parsing import Location, ValidationIssues


class OpenApiServerParser:
    def __init__(self, issues: ValidationIssues) -> None:
        self._issues = issues

    def parse(self, raw: object, location: Location) -> list[str]:
        if not isinstance(raw, list):
            self._issues.add("unsupported_server", location, "Servers must be an array")
            return []
        servers: list[str] = []
        for index, value in enumerate(raw):
            item_location = (*location, index)
            parsed = self._parse_item(value, item_location)
            if parsed is not None:
                servers.append(parsed)
        return servers

    def _parse_item(self, raw: object, location: Location) -> str | None:
        if not isinstance(raw, Mapping):
            self._issues.add("unsupported_server", location, "Server must be an object")
            return None
        if self._issues.reject_references(raw, location):
            return None
        if "variables" in raw:
            self._issues.add(
                "unsupported_server",
                (*location, "variables"),
                "Server variables are unsupported",
            )
            return None
        url = raw.get("url")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            if parsed is not None:
                _ = parsed.port
        except ValueError:
            parsed = None
        if (
            parsed is None
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "{" in cast(str, url)
            or "}" in cast(str, url)
        ):
            self._issues.add(
                "unsupported_server",
                (*location, "url"),
                "Server must be an absolute HTTPS URL without userinfo",
            )
            return None
        return cast(str, url)
