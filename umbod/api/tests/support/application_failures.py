from umbod.core.diagnostics import ApplicationFailure


class CapturingApplicationFailures:
    def __init__(self) -> None:
        self.events: list[ApplicationFailure] = []

    def send(self, event: ApplicationFailure) -> None:
        self.events.append(event)
