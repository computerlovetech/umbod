from typing import Protocol

from umbod.core.connectors.openapi.models import ImportedOpenApiCandidate


class OpenApiCandidateImporter(Protocol):
    def import_candidate(self, candidate: object) -> ImportedOpenApiCandidate: ...
