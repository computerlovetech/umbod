from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True, order=True)
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

    def release(self, increment: str) -> ReleaseVersion:
        if increment == "beta":
            if self.beta >= 0:
                return ReleaseVersion(self.major, self.minor, self.patch, self.beta + 1)
            return ReleaseVersion(self.major, self.minor, self.patch + 1, 1)
        if increment == "patch":
            if self.beta >= 0:
                return ReleaseVersion(self.major, self.minor, self.patch, -1)
            return ReleaseVersion(self.major, self.minor, self.patch + 1, -1)
        if increment == "minor":
            return ReleaseVersion(self.major, self.minor + 1, 0, -1)
        if increment == "major":
            return ReleaseVersion(self.major + 1, 0, 0, -1)
        raise ValueError(f"Unsupported increment: {increment}")

    def semver(self) -> str:
        suffix = "" if self.beta < 0 else f"-beta.{self.beta}"
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"

    def pep440(self) -> str:
        suffix = "" if self.beta < 0 else f"b{self.beta}"
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"


def resolve(current: str, increment: str, bootstrap: bool, pep440: bool) -> str:
    parsed = ReleaseVersion.parse(current)
    if bootstrap and increment == "beta" and parsed.beta < 0:
        selected = ReleaseVersion(parsed.major, parsed.minor, parsed.patch, 1)
    elif bootstrap and increment == "patch" and parsed.beta < 0:
        selected = parsed
    elif bootstrap and increment == "beta" and parsed.beta >= 0:
        selected = parsed
    else:
        selected = parsed.release(increment)
    return selected.pep440() if pep440 else selected.semver()


def main(arguments: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True)
    parser.add_argument("--increment", choices=("beta", "patch", "minor", "major"), required=True)
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--pep440", action="store_true")
    options = parser.parse_args(arguments)
    print(resolve(options.current, options.increment, options.bootstrap, options.pep440))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
