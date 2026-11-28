from typing import cast

from pydantic import ConfigDict, Field as ModelField, RootModel

from umbod.proxies import Model
from umbod.core.persistence import Field, Fields, KeyCodec, PydanticJsonCodec, RowCodec, Table, TableIdentity, TextCodec


class ManagedConnectorKey(Model):
    draft_id: str = ModelField(repr=False)


class ManagedConnectorRow(ManagedConnectorKey):
    connector_id: str
    revision_id: str = ModelField(repr=False)
    source_sha256: str = ModelField(repr=False)
    profile_id: str
    status: str
    declared_connector_id: str
    display_name: str
    description: str
    configuration_schema_json: str = ModelField(repr=False)


_MANAGED = TableIdentity("portable_managed_connectors")
DRAFT_ID = Field[ManagedConnectorRow, str](_MANAGED, "draft_id", TextCodec())
CONNECTOR_ID = Field[ManagedConnectorRow, str](_MANAGED, "connector_id", TextCodec())
_REVISION_ID = Field[ManagedConnectorRow, str](_MANAGED, "revision_id", TextCodec())
_SOURCE_SHA = Field[ManagedConnectorRow, str](_MANAGED, "source_sha256", TextCodec())
_PROFILE_ID = Field[ManagedConnectorRow, str](_MANAGED, "profile_id", TextCodec())
_STATUS = Field[ManagedConnectorRow, str](_MANAGED, "status", TextCodec())
_DECLARED_ID = Field[ManagedConnectorRow, str](_MANAGED, "declared_connector_id", TextCodec())
_NAME = Field[ManagedConnectorRow, str](_MANAGED, "display_name", TextCodec())
_DESCRIPTION = Field[ManagedConnectorRow, str](_MANAGED, "description", TextCodec())
_CONFIGURATION_SCHEMA = Field[ManagedConnectorRow, str](_MANAGED, "configuration_schema_json", TextCodec())
MANAGED_CONNECTOR_TABLE = Table(
    _MANAGED,
    RowCodec(ManagedConnectorRow, cast(tuple[Field[ManagedConnectorRow, object], ...], (
        DRAFT_ID, CONNECTOR_ID, _REVISION_ID, _SOURCE_SHA, _PROFILE_ID, _STATUS, _DECLARED_ID, _NAME,
        _DESCRIPTION, _CONFIGURATION_SCHEMA,
    ))),
    KeyCodec(ManagedConnectorKey, cast(tuple[Field[ManagedConnectorRow, object], ...], (DRAFT_ID,))),
)


class ManagedCatalogRow(Model):
    connector_id: str
    status: str
    display_name: str
    description: str


class ManagedCatalogDetailRow(ManagedCatalogRow):
    configuration_schema_json: str = ModelField(repr=False)


_CATALOG_FIELDS = cast(tuple[Field[ManagedConnectorRow, object], ...], (CONNECTOR_ID, _STATUS, _NAME, _DESCRIPTION))
MANAGED_CATALOG_PROJECTION = Fields(ManagedCatalogRow, _CATALOG_FIELDS)
MANAGED_CATALOG_DETAIL_PROJECTION = Fields(
    ManagedCatalogDetailRow, (*_CATALOG_FIELDS, cast(Field[ManagedConnectorRow, object], _CONFIGURATION_SCHEMA)),
)


class ManagedConfigurationKey(Model):
    connector_id: str


class ManagedValues(RootModel[dict[str, str]]):
    model_config = ConfigDict(strict=True)


class ManagedConfigurationRow(ManagedConfigurationKey):
    configuration: ManagedValues = ModelField(repr=False)


_CONFIGURATIONS = TableIdentity("portable_managed_configurations")
CONFIGURATION_CONNECTOR_ID = Field[ManagedConfigurationRow, str](_CONFIGURATIONS, "connector_id", TextCodec())
_CONFIGURATION = Field(_CONFIGURATIONS, "configuration", PydanticJsonCodec(ManagedValues))
_CONFIGURATION_KEY_FIELDS = cast(tuple[Field[ManagedConfigurationRow, object], ...], (CONFIGURATION_CONNECTOR_ID,))
MANAGED_CONFIGURATION_TABLE = Table(
    _CONFIGURATIONS,
    RowCodec(ManagedConfigurationRow, (*_CONFIGURATION_KEY_FIELDS, _CONFIGURATION)),
    KeyCodec(ManagedConfigurationKey, _CONFIGURATION_KEY_FIELDS),
)
MANAGED_CONFIGURATION_KEY_PROJECTION = Fields(ManagedConfigurationKey, _CONFIGURATION_KEY_FIELDS)
