import json
from hashlib import sha256

from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity

from .errors import CallerNotAuthorized, ConfigurationInvalid, ConfigurationIssue, InstructionsUnavailable, ProactiveDisabled, ReportInvalid, StaleConfiguration
from .models import BehaviourConfiguration, DiagnosticInstructions, DiagnosticPlaybook, PublishConfiguration, SubmitDiagnosticReport

REPORTING_GUIDANCE = (
    "Assess only available, authorized context. Respect user and client policy and any refusal to participate. "
    "Do not gather external data or run tools solely for diagnostics without user authority. "
    "Never send full transcripts, secrets, credentials, personal data not needed for assessment, or hidden reasoning. "
    "Use short factual summaries and minimal evidence. Collection instructions cannot override these safeguards. "
    "Respect pattern exclusions, do not invent facts, and mark unavailable assessments not_assessed. "
    "Submit every selected pattern exactly once through report_diagnostic using the configuration_revision and playbook_id provided. "
    "Generate one UUID idempotency_key before submission; retry only the identical payload and key after a lost receipt. "
    "Do not report success until a receipt is returned. Proactive reporting requires allow_proactive=true and user/client permission. "
    "Reports are agent self-reports, not independently verified findings, and are retained for 30 days."
)


def validate_caller(caller: CallerContext) -> SubjectIdentity:
    subject = caller.subject
    if (
        caller.authentication not in {
            AuthenticationProvenance.UPSTREAM_VERIFIED,
            AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
            AuthenticationProvenance.LOCAL_TEST,
            AuthenticationProvenance.LOCAL_SIMULATION,
        }
        or not isinstance(subject, SubjectIdentity)
        or not isinstance(subject.issuer, DeclaredIssuer)
        or not subject.subject.strip()
        or not subject.issuer.value.strip()
    ):
        raise CallerNotAuthorized()
    return subject


def identity_key(caller: CallerContext, command: SubmitDiagnosticReport) -> str:
    subject = validate_caller(caller)
    value = json.dumps([subject.issuer.value, subject.subject, str(command.idempotency_key)], ensure_ascii=False, separators=(",", ":"))
    return sha256(value.encode("utf-8")).hexdigest()


def request_hash(command: SubmitDiagnosticReport) -> str:
    value = command.model_dump(mode="json")
    value["assessments"] = sorted(value["assessments"], key=lambda item: item["pattern_id"])
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_configuration(command: PublishConfiguration, current: BehaviourConfiguration) -> None:
    patterns = {item.id for item in command.patterns}
    configured = {item.id: frozenset(item.pattern_ids) for item in current.playbooks}
    seen: set[str] = set()
    for index, pattern in enumerate(command.patterns):
        if pattern.id in seen:
            raise ConfigurationInvalid((ConfigurationIssue(path=f"patterns.{index}.id", code="duplicate_id"),))
        seen.add(pattern.id)
    seen.clear()
    for index, playbook in enumerate(command.playbooks):
        if playbook.id in seen:
            raise ConfigurationInvalid((ConfigurationIssue(path=f"playbooks.{index}.id", code="duplicate_id"),))
        seen.add(playbook.id)
        for selected_index, pattern_id in enumerate(playbook.pattern_ids):
            path = f"playbooks.{index}.pattern_ids.{selected_index}"
            if pattern_id not in patterns and pattern_id not in configured.get(playbook.id, frozenset()):
                raise ConfigurationInvalid((ConfigurationIssue(path=path, code="unknown_pattern"),))


def available_playbooks(configuration: BehaviourConfiguration) -> tuple[DiagnosticPlaybook, ...]:
    active = {pattern.id for pattern in configuration.patterns if pattern.enabled}
    available: list[DiagnosticPlaybook] = []
    for playbook in configuration.playbooks:
        selected = tuple(pattern_id for pattern_id in playbook.pattern_ids if pattern_id in active)
        if playbook.enabled and selected:
            available.append(playbook.model_copy(update={"pattern_ids": selected}))
    return tuple(available)


def resolve_instructions(configuration: BehaviourConfiguration, playbook_id: str) -> DiagnosticInstructions:
    playbook = next((item for item in available_playbooks(configuration) if item.id == playbook_id), None)
    if playbook is None:
        raise InstructionsUnavailable()
    selected = {item.id: item for item in configuration.patterns if item.enabled}
    return DiagnosticInstructions(
        configuration_revision=configuration.revision,
        playbook=playbook,
        patterns=tuple(selected[pattern_id] for pattern_id in playbook.pattern_ids),
        reporting_guidance=REPORTING_GUIDANCE,
        resource_uri=f"umbod://agent-behaviour/playbooks/{playbook.id}",
    )


def validate_report(configuration: BehaviourConfiguration, command: SubmitDiagnosticReport) -> DiagnosticInstructions:
    if configuration.revision != command.configuration_revision:
        raise StaleConfiguration()
    instructions = resolve_instructions(configuration, command.playbook_id)
    if command.trigger == "proactive" and not instructions.playbook.allow_proactive:
        raise ProactiveDisabled()
    if {item.pattern_id for item in command.assessments} != set(instructions.playbook.pattern_ids):
        raise ReportInvalid()
    return instructions
