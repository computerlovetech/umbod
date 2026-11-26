from typing import cast

from pydantic import BaseModel

from umbod.core.persistence import BooleanCodec, Field, IntegerCodec, KeyCodec, PydanticJsonCodec, RowCodec, Table, TableIdentity, TextCodec

from .legacy import StoredConfigurationCodec, StoredReportCodec
from .models import AssessmentStatus, BehaviourConfiguration, BehaviourModel, DiagnosticReport, ReportSummary


class ConfigurationKey(BehaviourModel):
    singleton: int


class ConfigurationRow(ConfigurationKey):
    configuration: BehaviourConfiguration


class ReportKey(BehaviourModel):
    report_id: str


class AssessmentVerdict(BehaviourModel):
    pattern_id: str
    status: AssessmentStatus


class ReportListing(BehaviourModel):
    summary: ReportSummary
    assessments: tuple[AssessmentVerdict, ...]


class ReportListRow(ReportKey):
    expires_at: int
    listing: ReportListing


class ReportRow(ReportKey):
    expires_at: int
    report: DiagnosticReport


class DedupeKey(BehaviourModel):
    key_hash: str


class DedupeRow(DedupeKey):
    request_hash: str
    report_id: str
    received_at: str
    expires_at: int
    deleted: bool


CONFIGURATION_IDENTITY = TableIdentity("agent_behaviour_configuration")
CONFIGURATION_KEY = Field[ConfigurationRow, int](CONFIGURATION_IDENTITY, "singleton", IntegerCodec())
CONFIGURATION_VALUE = Field[ConfigurationRow, BehaviourConfiguration](CONFIGURATION_IDENTITY, "configuration", StoredConfigurationCodec(BehaviourConfiguration))
CONFIGURATION_FIELDS = cast(tuple[Field[ConfigurationRow, object], ...], (CONFIGURATION_KEY, CONFIGURATION_VALUE))
CONFIGURATION_TABLE = Table(CONFIGURATION_IDENTITY, RowCodec(ConfigurationRow, CONFIGURATION_FIELDS), KeyCodec(ConfigurationKey, cast(tuple[Field[ConfigurationRow, object], ...], (CONFIGURATION_KEY,))))

REPORT_IDENTITY = TableIdentity("agent_behaviour_reports")
REPORT_ID = Field[ReportRow, str](REPORT_IDENTITY, "report_id", TextCodec())
REPORT_EXPIRY = Field[ReportRow, int](REPORT_IDENTITY, "expires_at", IntegerCodec())
REPORT_VALUE = Field[ReportRow, DiagnosticReport](REPORT_IDENTITY, "report", StoredReportCodec(DiagnosticReport))
REPORT_FIELDS = cast(tuple[Field[ReportRow, object], ...], (REPORT_ID, REPORT_EXPIRY, REPORT_VALUE))
REPORT_KEY_FIELDS = cast(tuple[Field[ReportRow, object], ...], (REPORT_ID,))
REPORT_TABLE = Table(REPORT_IDENTITY, RowCodec(ReportRow, REPORT_FIELDS), KeyCodec(ReportKey, REPORT_KEY_FIELDS))

LIST_IDENTITY = TableIdentity("agent_behaviour_report_index")
LIST_ID = Field[ReportListRow, str](LIST_IDENTITY, "report_id", TextCodec())
LIST_EXPIRY = Field[ReportListRow, int](LIST_IDENTITY, "expires_at", IntegerCodec())
LIST_VALUE = Field[ReportListRow, ReportListing](LIST_IDENTITY, "listing", PydanticJsonCodec(ReportListing))
LIST_FIELDS = cast(tuple[Field[ReportListRow, object], ...], (LIST_ID, LIST_EXPIRY, LIST_VALUE))
REPORT_LIST_TABLE = Table(LIST_IDENTITY, RowCodec(ReportListRow, LIST_FIELDS), KeyCodec(ReportKey, cast(tuple[Field[ReportListRow, object], ...], (LIST_ID,))))

DEDUPE_IDENTITY = TableIdentity("agent_behaviour_receipts")
DEDUPE_KEY = Field[DedupeRow, str](DEDUPE_IDENTITY, "key_hash", TextCodec())
DEDUPE_REQUEST = Field[DedupeRow, str](DEDUPE_IDENTITY, "request_hash", TextCodec())
DEDUPE_REPORT = Field[DedupeRow, str](DEDUPE_IDENTITY, "report_id", TextCodec())
DEDUPE_RECEIVED = Field[DedupeRow, str](DEDUPE_IDENTITY, "received_at", TextCodec())
DEDUPE_EXPIRY = Field[DedupeRow, int](DEDUPE_IDENTITY, "expires_at", IntegerCodec())
DEDUPE_DELETED = Field[DedupeRow, bool](DEDUPE_IDENTITY, "deleted", BooleanCodec())
DEDUPE_FIELDS = cast(tuple[Field[DedupeRow, object], ...], (DEDUPE_KEY, DEDUPE_REQUEST, DEDUPE_REPORT, DEDUPE_RECEIVED, DEDUPE_EXPIRY, DEDUPE_DELETED))
DEDUPE_TABLE = Table(DEDUPE_IDENTITY, RowCodec(DedupeRow, DEDUPE_FIELDS), KeyCodec(DedupeKey, cast(tuple[Field[DedupeRow, object], ...], (DEDUPE_KEY,))))
AGENT_BEHAVIOUR_TABLES = cast(tuple[Table[BaseModel, BaseModel], ...], (CONFIGURATION_TABLE, REPORT_TABLE, REPORT_LIST_TABLE, DEDUPE_TABLE))
