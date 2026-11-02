from pydantic import BaseModel, ConfigDict

from ..models import NodeId, Principal


class HomeBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user: Principal
    node_id: NodeId
