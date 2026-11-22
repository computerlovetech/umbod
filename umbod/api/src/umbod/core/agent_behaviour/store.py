from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from umbod.core.callers import CallerContext, SubjectIdentity
from umbod.core.persistence import AllFields, Database, DatabaseSession, DeleteQuery, Equals, Fields, GreaterThan, InsertCommand, LessThan, Not, Query, ReadSession, TransactionMode, Unordered, UpsertCommand

from .defaults import get_default_configuration
from .errors import AgentBehaviourError, IdempotencyConflict, ReportGone, ReportNotFound, RevisionConflict, StorageUnavailable
from .models import BehaviourConfiguration, DiagnosticReceipt, DiagnosticReport, PublishConfiguration, ReportPage, ReportQuery, ReportSummary, SubmitDiagnosticReport
from .policy import identity_key, request_hash, validate_configuration, validate_report
from .schema import CONFIGURATION_KEY, CONFIGURATION_TABLE, DEDUPE_EXPIRY, DEDUPE_KEY, DEDUPE_REPORT, DEDUPE_TABLE, LIST_EXPIRY, LIST_ID, REPORT_EXPIRY, REPORT_ID, REPORT_KEY_FIELDS, REPORT_LIST_TABLE, REPORT_TABLE, AssessmentVerdict, ConfigurationKey, ConfigurationRow, DedupeKey, DedupeRow, ReportKey, ReportListing, ReportListRow, ReportRow


def _instant(value: datetime) -> int:
    if value.utcoffset() is None:
        raise ValueError("An aware timestamp is required")
    elapsed = value - datetime(1970, 1, 1, tzinfo=UTC)
    return (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds


async def _ensure_configuration(session: DatabaseSession) -> BehaviourConfiguration:
    row = await session.find_one(CONFIGURATION_TABLE, Query(Equals(CONFIGURATION_KEY, 1), AllFields(), Unordered()))
    if row is not None:
        return row.configuration
    configuration = get_default_configuration()
    inserted = await session.insert(CONFIGURATION_TABLE, InsertCommand(row=ConfigurationRow(singleton=1, configuration=configuration)))
    if not inserted:
        raise StorageUnavailable()
    return configuration


def _matches(listing: ReportListing, query: ReportQuery) -> bool:
    if query.playbook_id is not None and listing.summary.playbook_id != query.playbook_id:
        return False
    if query.pattern_id is None and query.status is None:
        return True
    return any(
        (query.pattern_id is None or item.pattern_id == query.pattern_id)
        and (query.status is None or item.status == query.status)
        for item in listing.assessments
    )


def _summary(report: DiagnosticReport) -> ReportSummary:
    return ReportSummary(
        report_id=report.report_id, received_at=report.received_at, expires_at=report.expires_at,
        caller=report.caller, playbook_id=report.submission.playbook_id,
        configuration_revision=report.submission.configuration_revision, trigger=report.submission.trigger,
        observed_pattern_ids=tuple(item.pattern_id for item in report.submission.assessments if item.status == "observed"),
    )


class DatabaseAgentBehaviourStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    @asynccontextmanager
    async def _read(self) -> AsyncIterator[ReadSession]:
        try:
            async with self._database.read_session() as session:
                yield session
        except AgentBehaviourError:
            raise
        except Exception:
            raise StorageUnavailable() from None

    @asynccontextmanager
    async def _write(self) -> AsyncIterator[DatabaseSession]:
        try:
            async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                yield session
        except AgentBehaviourError:
            raise
        except Exception:
            raise StorageUnavailable() from None

    async def get_configuration(self) -> BehaviourConfiguration:
        async with self._read() as session:
            row = await session.find_one(CONFIGURATION_TABLE, Query(Equals(CONFIGURATION_KEY, 1), AllFields(), Unordered()))
            if row is not None:
                return row.configuration
        async with self._write() as session:
            return await _ensure_configuration(session)

    async def publish_configuration(self, command: PublishConfiguration) -> BehaviourConfiguration:
        async with self._write() as session:
            current = await _ensure_configuration(session)
            if current.revision != command.expected_revision:
                raise RevisionConflict(current)
            validate_configuration(command, current)
            published = BehaviourConfiguration(revision=current.revision + 1, patterns=command.patterns, playbooks=command.playbooks)
            await session.upsert(CONFIGURATION_TABLE, UpsertCommand(key=ConfigurationKey(singleton=1), row=ConfigurationRow(singleton=1, configuration=published)))
            return published

    async def submit_report(self, caller: CallerContext, command: SubmitDiagnosticReport, now: datetime, report_id: UUID) -> DiagnosticReceipt:
        key = identity_key(caller, command)
        digest = request_hash(command)
        async with self._write() as session:
            previous = await session.find_one(DEDUPE_TABLE, Query(Equals(DEDUPE_KEY, key), AllFields(), Unordered()))
            if previous is not None and previous.expires_at > _instant(now):
                if previous.request_hash != digest:
                    raise IdempotencyConflict()
                if previous.deleted:
                    raise ReportGone()
                return DiagnosticReceipt(report_id=UUID(previous.report_id), received_at=datetime.fromisoformat(previous.received_at), duplicate=True)
            configuration = await _ensure_configuration(session)
            instructions = validate_report(configuration, command)
            report = DiagnosticReport(report_id=report_id, received_at=now, expires_at=now + timedelta(days=30), caller=caller, submission=command, instructions=instructions)
            listing = ReportListing(summary=_summary(report), assessments=tuple(AssessmentVerdict(pattern_id=item.pattern_id, status=item.status) for item in command.assessments))
            inserted = await session.insert(REPORT_TABLE, InsertCommand(row=ReportRow(report_id=str(report_id), expires_at=_instant(report.expires_at), report=report)))
            if not inserted:
                raise StorageUnavailable()
            indexed = await session.insert(REPORT_LIST_TABLE, InsertCommand(row=ReportListRow(report_id=str(report_id), expires_at=_instant(report.expires_at), listing=listing)))
            if not indexed:
                raise StorageUnavailable()
            await session.upsert(DEDUPE_TABLE, UpsertCommand(key=DedupeKey(key_hash=key), row=DedupeRow(key_hash=key, request_hash=digest, report_id=str(report_id), received_at=now.isoformat(), expires_at=_instant(now + timedelta(days=60)), deleted=False)))
            return DiagnosticReceipt(report_id=report_id, received_at=now, duplicate=False)

    async def list_reports(self, query: ReportQuery, now: datetime) -> ReportPage:
        return await self._list_reports(query, now, lambda summary: True)

    async def list_owned_reports(self, owner: SubjectIdentity, query: ReportQuery, now: datetime) -> ReportPage:
        return await self._list_reports(query, now, lambda summary: summary.caller.subject == owner)

    async def _list_reports(self, query: ReportQuery, now: datetime, includes: Callable[[ReportSummary], bool]) -> ReportPage:
        async with self._read() as session:
            rows = await session.find_many(REPORT_LIST_TABLE, Query(GreaterThan(LIST_EXPIRY, _instant(now)), AllFields(), Unordered()))
        summaries = sorted((row.listing.summary for row in rows if includes(row.listing.summary) and _matches(row.listing, query)), key=lambda summary: (summary.received_at, str(summary.report_id)), reverse=True)
        return ReportPage(items=tuple(summaries[query.offset:query.offset + query.limit]), total=len(summaries))

    async def get_report(self, report_id: UUID, now: datetime) -> DiagnosticReport:
        async with self._read() as session:
            row = await session.find_one(REPORT_TABLE, Query(Equals(REPORT_ID, str(report_id)), AllFields(), Unordered()))
        if row is None or row.expires_at <= _instant(now):
            raise ReportNotFound()
        return row.report

    async def get_owned_report(self, owner: SubjectIdentity, report_id: UUID, now: datetime) -> DiagnosticReport:
        report = await self.get_report(report_id, now)
        if report.caller.subject != owner:
            raise ReportNotFound()
        return report

    async def delete_report(self, report_id: UUID, now: datetime) -> None:
        async with self._write() as session:
            await session.delete(REPORT_TABLE, DeleteQuery(Equals(REPORT_ID, str(report_id))))
            await session.delete(REPORT_LIST_TABLE, DeleteQuery(Equals(LIST_ID, str(report_id))))
            rows = await session.find_many(DEDUPE_TABLE, Query(Equals(DEDUPE_REPORT, str(report_id)), AllFields(), Unordered()))
            for row in rows:
                await session.upsert(DEDUPE_TABLE, UpsertCommand(key=DedupeKey(key_hash=row.key_hash), row=row.model_copy(update={"deleted": True})))

    async def purge_expired(self, now: datetime, batch_size: int) -> int:
        if not 2 <= batch_size <= 1000:
            raise ValueError("Invalid cleanup batch size")
        async with self._write() as session:
            reports = await session.find_many(REPORT_TABLE, Query(Not(GreaterThan(REPORT_EXPIRY, _instant(now))), Fields(ReportKey, REPORT_KEY_FIELDS), Unordered(), limit=batch_size // 2))
            for row in reports:
                await session.delete(REPORT_TABLE, DeleteQuery(Equals(REPORT_ID, row.report_id)))
                await session.delete(REPORT_LIST_TABLE, DeleteQuery(Equals(LIST_ID, row.report_id)))
            receipts = await session.find_many(DEDUPE_TABLE, Query(LessThan(DEDUPE_EXPIRY, _instant(now) + 1), AllFields(), Unordered(), limit=batch_size - batch_size // 2))
            for row in receipts:
                await session.delete(DEDUPE_TABLE, DeleteQuery(Equals(DEDUPE_KEY, row.key_hash)))
            return len(reports) + len(receipts)
