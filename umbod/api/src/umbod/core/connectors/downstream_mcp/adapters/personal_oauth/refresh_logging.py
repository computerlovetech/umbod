import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


_refresh_logging_active: ContextVar[bool] = ContextVar("personal_oauth_refresh_logging_active", default=False)


class _RefreshNetworkLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _refresh_logging_active.get()


_filter = _RefreshNetworkLogFilter()


@contextmanager
def private_refresh_network_logs() -> Iterator[None]:
    for name in ("httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy", "httpcore.socks"):
        logger = logging.getLogger(name)
        if _filter not in logger.filters:
            logger.addFilter(_filter)
    token = _refresh_logging_active.set(True)
    try:
        yield
    finally:
        _refresh_logging_active.reset(token)
