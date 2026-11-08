class InvalidPersonalAccessToken(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid personal access token")


class UntrustedPersonalAccessTokenCaller(PermissionError):
    def __init__(self) -> None:
        super().__init__("A verified caller identity is required")


class PersonalAccessTokenCollision(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Personal access token identifier collision")
