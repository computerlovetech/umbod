from umbod.core.administrator import AdministratorAccess
from umbod.core.groups.stores.reads import DatabaseGroupInstanceLookup
from umbod.core.persistence import Database

from .generation import SecureAgentCredentialGenerator, SystemAgentCredentialClock
from .service import AgentCredentialService, AgentCredentialVerifier
from .store import DatabaseAgentCredentialStore


def create_agent_credential_service(
    database: Database,
    access: AdministratorAccess,
) -> AgentCredentialService:
    return AgentCredentialService(
        access=access,
        groups=DatabaseGroupInstanceLookup(database),
        store=DatabaseAgentCredentialStore(database),
        clock=SystemAgentCredentialClock(),
        generator=SecureAgentCredentialGenerator(),
    )


def create_agent_credential_verifier(database: Database) -> AgentCredentialVerifier:
    return AgentCredentialVerifier(
        groups=DatabaseGroupInstanceLookup(database),
        store=DatabaseAgentCredentialStore(database),
        clock=SystemAgentCredentialClock(),
    )
