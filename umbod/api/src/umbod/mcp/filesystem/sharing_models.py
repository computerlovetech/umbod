from uuid import UUID

from pydantic import BaseModel, ConfigDict

from umbod.core.filesystem.sharing import GroupPolicy


class ListSharingGroupsCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    node_id: UUID


class ShareNodeGroupCommand(GroupPolicy):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    node_id: UUID
