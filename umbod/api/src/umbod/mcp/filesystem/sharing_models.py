from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_serializer

from umbod.core.filesystem.access import Visibility
from umbod.core.filesystem.sharing import ShareNodeResult
from umbod.core.filesystem.sharing.models import default_recursive_scope
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
    recursive: bool = Field(default_factory=default_recursive_scope, strict=True, description="Directory grants apply to descendants when true. Omission preserves existing scope, defaults true for new directories; files always normalize false.")

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    node_id: UUID


class CallerShareNodeResult(ShareNodeResult):
    visible_to: Visibility


class LegacyShareNodeGroupResult(ShareNodeGroupCommand):
    recursive: bool = Field(..., strict=True)
    changed: bool
    visible_to: Visibility

    @field_serializer("permissions", when_used="json")
    def serialize_permissions(self, permissions: frozenset[Permission]) -> list[str]:
        return sorted(permission.value for permission in permissions)


SHARE_COMMAND = TypeAdapter(ShareNodeCommand | ShareNodeGroupCommand)
