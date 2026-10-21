from ..contracts import DesktopContract


class PrefixUpdate(DesktopContract):
    connector_id: str
    prefix: str


class LegacyAuthorization(DesktopContract):
    legacy_id: str
    host_id: str
    endpoint_url: str
