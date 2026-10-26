import logging

from umbod.logging import log_safe_exception


class LoggingSignalFailureHandler:
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def handles(self, receiver_name: str, error: BaseException) -> None:
        log_safe_exception(self._logger, f"MCP signal receiver failed: {receiver_name}", error)
