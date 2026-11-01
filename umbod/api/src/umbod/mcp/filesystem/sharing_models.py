from uuid import UUID

from pydantic import BaseModel, ConfigDict, TypeAdapter, field_serializer

from umbod.core.filesystem import Permission
from umbod.core.filesystem.sharing import GroupPolicy, ShareNodePolicy, SharingRecipientType
from umbod.core.identity_directory.user_models import SearchText


class SearchSharingRecipientsCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    node_id: UUID
    query: SearchText


class FilteredSearchSharingRecipientsCommand(SearchSharingRecipientsCommand):
    recipient_type: SharingRecipientType


SEARCH_RECIPIENTS_COMMAND = TypeAdapter(
    FilteredSearchSharingRecipientsCommand | SearchSharingRecipientsCommand,
)


class ShareNodeCommand(ShareNodePolicy):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    node_id: UUID


class ShareNodeGroupCommand(GroupPolicy):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    node_id: UUID


class LegacyShareNodeGroupResult(ShareNodeGroupCommand):
    changed: bool

    @field_serializer("permissions", when_used="json")
    def serialize_permissions(self, permissions: frozenset[Permission]) -> list[str]:
        return sorted(permission.value for permission in permissions)


SHARE_COMMAND = TypeAdapter(ShareNodeCommand | ShareNodeGroupCommand)
