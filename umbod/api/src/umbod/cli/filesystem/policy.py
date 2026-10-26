from pathlib import Path

from umbod.core.filesystem import RootBootstrapSpec


class FileBootstrapPolicySource:
    def load(self, policy_file: str) -> RootBootstrapSpec:
        return RootBootstrapSpec.model_validate_json(Path(policy_file).read_bytes())
