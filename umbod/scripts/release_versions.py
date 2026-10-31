from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReleaseVersion:
    major: int
    minor: int
    patch: int
    beta: int

    @classmethod
    def parse(cls, value: str) -> ReleaseVersion:
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(?:-beta\.|b)(\d+))?", value)
        if match is None:
            raise ValueError(f"Unsupported release version: {value}")
        beta = -1 if match.group(4) is None else int(match.group(4))
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)), beta)

    def semver(self) -> str:
        suffix = "" if self.beta < 0 else f"-beta.{self.beta}"
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"

    def pep440(self) -> str:
        suffix = "" if self.beta < 0 else f"b{self.beta}"
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"


def main(arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--metadata", type=Path)
    options = parser.parse_args(arguments)
    canonical_tag = r"umbod-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-beta\.(0|[1-9][0-9]*))?"
    if re.fullmatch(canonical_tag, options.tag) is None:
        parser.error(f"Unsupported release tag: {options.tag}")
    selected = ReleaseVersion.parse(options.tag.removeprefix("umbod-v"))
    if options.metadata is not None:
        expected = {
            "chartVersion": selected.semver(),
            "imageTag": selected.semver(),
            "sdkVersion": selected.pep440(),
        }
        try:
            actual = json.loads(options.metadata.read_text())
        except (OSError, ValueError) as error:
            parser.error(f"Cannot read release metadata: {error}")
        if actual != expected:
            parser.error(f"Update committed release metadata before tagging {options.tag}: expected {json.dumps(expected)}")
    print(f"sdk_version={selected.pep440()}")
    print(f"image_version={selected.semver()}")
    print(f"chart_version={selected.semver()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
