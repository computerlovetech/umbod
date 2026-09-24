from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.capabilities.descriptions import CapabilityDescription
from umbod.mcp.connectors.tools.discovery.search import ConnectorToolSearchCandidate


class ConnectorCapabilityDomain(BaseModel):
    model_config = ConfigDict(frozen=True)

    connector_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    capability_description: CapabilityDescription
    operation_count: int = Field(ge=1)


class ConnectorCapabilityManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    domains: tuple[ConnectorCapabilityDomain, ...]


class ConnectorCapabilityManifestService:
    def derive(
        self, candidates: Sequence[ConnectorToolSearchCandidate]
    ) -> ConnectorCapabilityManifest:
        metadata: dict[str, tuple[str, str]] = {}
        counts: dict[str, int] = {}
        for candidate in candidates:
            candidate_metadata = (
                candidate.connector_display_name,
                candidate.connector_capability_description,
            )
            existing = metadata.get(candidate.connector_id)
            if existing is not None and existing != candidate_metadata:
                raise ValueError(
                    f"conflicting capability metadata for connector {candidate.connector_id}"
                )
            metadata[candidate.connector_id] = candidate_metadata
            counts[candidate.connector_id] = counts.get(candidate.connector_id, 0) + 1
        domains = tuple(
            ConnectorCapabilityDomain(
                connector_id=connector_id,
                display_name=display_name,
                capability_description=capability_description,
                operation_count=counts[connector_id],
            )
            for connector_id, (display_name, capability_description) in sorted(
                metadata.items(), key=lambda entry: (entry[1][0].casefold(), entry[0])
            )
        )
        return ConnectorCapabilityManifest(domains=domains)


class ConnectorCapabilityManifestFormatter:
    def __init__(self, character_budget: int) -> None:
        if character_budget < 1:
            raise ValueError("character_budget must be positive")
        self._character_budget = character_budget

    def format(self, base_description: str, manifest: ConnectorCapabilityManifest) -> str:
        bounded_base = base_description[: self._character_budget]
        if not manifest.domains or len(bounded_base) == self._character_budget:
            return bounded_base
        prefix = " Available connector domains: "
        description = bounded_base
        for domain in manifest.domains:
            entry = (
                f"{domain.display_name}: {domain.capability_description} "
                f"({domain.operation_count} operations)"
            )
            separator = prefix if description == bounded_base else "; "
            if len(description) + len(separator) + len(entry) > self._character_budget:
                break
            description = f"{description}{separator}{entry}"
        return description
