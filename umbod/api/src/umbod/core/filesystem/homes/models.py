from pydantic import ConfigDict

from umbod.proxies import Model

from ..models import NodeId, Principal


class HomeBinding(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user: Principal
    node_id: NodeId
