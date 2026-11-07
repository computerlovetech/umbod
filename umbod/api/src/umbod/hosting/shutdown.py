import threading
from collections.abc import Callable


class ProcessShutdownDeadline:
    def __init__(self, seconds: float, terminate: Callable[[int], object]) -> None:
        self.timer = threading.Timer(seconds, terminate, args=(1,))
        self.timer.daemon = True
        self.started = False

    def arm(self) -> None:
        if not self.started:
            self.started = True
            self.timer.start()

    def cancel(self) -> None:
        self.timer.cancel()

