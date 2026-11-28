class InvalidAgentCredential(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid agent credential")


class AgentNotFound(LookupError):
    pass


class AgentGroupNotFound(LookupError):
    pass


class AgentCredentialConflict(RuntimeError):
    pass
