class InvalidAgentCredential(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid agent credential")


class InvalidAgentCredentialExpiry(ValueError):
    def __init__(self) -> None:
        super().__init__("Expiry must be in the future")


class AgentNotFound(LookupError):
    pass


class AgentGroupNotFound(LookupError):
    pass


class AgentCredentialConflict(RuntimeError):
    pass
