class SettingsPermissionDenied(PermissionError):
    def __init__(self) -> None:
        super().__init__("System settings require an administrator")


class SettingsStorageUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("System settings storage is unavailable")
