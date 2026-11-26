from typing import cast

from umbod.core.persistence import PydanticJsonCodec

from .models import BehaviourConfiguration, DiagnosticReport

_LEGACY_FACTORY_INSTRUCTIONS = (
    "Review only the current task context and tool results you are authorized to use. Assess every selected pattern. "
    "Record a short factual summary and up to three minimal observations for each observed pattern. "
    "Use not_assessed when context is insufficient. Never collect full transcripts, credentials, personal data, or hidden reasoning."
)
_RETIRED_MODE_SUFFIX = " Report only when requested unless automatic reporting is explicitly allowed and the user and client permit it."


def _decode_playbook(value: object, *, legacy_configuration: bool) -> object:
    if not isinstance(value, dict):
        return value
    playbook = cast(dict[str, object], value).copy()
    playbook.pop("allow_proactive", None)
    if (
        legacy_configuration
        and playbook.get("id") == "behaviour-review"
        and playbook.get("collection_instructions") == _LEGACY_FACTORY_INSTRUCTIONS + _RETIRED_MODE_SUFFIX
    ):
        playbook["collection_instructions"] = _LEGACY_FACTORY_INSTRUCTIONS
    return playbook


class StoredConfigurationCodec(PydanticJsonCodec[BehaviourConfiguration]):
    def decode(self, value: object) -> BehaviourConfiguration:
        if not isinstance(value, dict):
            return super().decode(value)
        configuration = cast(dict[str, object], value).copy()
        playbooks = configuration.get("playbooks")
        if isinstance(playbooks, list):
            legacy_configuration = "reporting_enabled" not in configuration
            if legacy_configuration:
                configuration["reporting_enabled"] = any(
                    isinstance(playbook, dict) and playbook.get("enabled") is True for playbook in playbooks
                )
            configuration["playbooks"] = [
                _decode_playbook(playbook, legacy_configuration=legacy_configuration) for playbook in playbooks
            ]
        return super().decode(configuration)


class StoredReportCodec(PydanticJsonCodec[DiagnosticReport]):
    def decode(self, value: object) -> DiagnosticReport:
        if not isinstance(value, dict) or not isinstance(value.get("instructions"), dict):
            return super().decode(value)
        report = cast(dict[str, object], value).copy()
        instructions = cast(dict[str, object], report["instructions"]).copy()
        if "playbook" in instructions:
            instructions["playbook"] = _decode_playbook(instructions["playbook"], legacy_configuration=False)
        report["instructions"] = instructions
        return super().decode(report)
