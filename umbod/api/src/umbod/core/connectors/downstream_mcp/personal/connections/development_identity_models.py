from pydantic import BaseModel, ConfigDict


class SimulatedUserIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    email: str
    name: str
    membership_claim: str
    required_membership: str
    simulated_admin: bool
