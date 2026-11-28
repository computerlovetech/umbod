from pydantic import ConfigDict

from umbod.proxies import Model


class SimulatedUserIdentity(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    email: str
    name: str
    membership_claim: str
    required_membership: str
    simulated_admin: bool
