from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass


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

    def ordering_key(self) -> tuple[int, int, int, bool, int]:
        return (self.major, self.minor, self.patch, self.beta < 0, self.beta)

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
    elif bootstrap and (increment == "patch" and parsed.beta < 0 or increment == "beta" and parsed.beta >= 0):
        selected = parsed
    else:
        selected = parsed.release(increment)
    return selected.pep440() if pep440 else selected.semver()


def latest(values: Sequence[str]) -> str:
    parsed: list[ReleaseVersion] = []
    for value in values:
        try:
            parsed.append(ReleaseVersion.parse(value.strip()))
        except ValueError:
            continue
    return max(parsed, key=ReleaseVersion.ordering_key).semver() if parsed else ""


def select_shared_release(
    sdk_current: str, image_current: str, sdk_checked: str, image_checked: str, increment: str
) -> ReleaseVersion:
    candidates = [
        ReleaseVersion.parse(sdk_current or sdk_checked),
        ReleaseVersion.parse(image_current or image_checked),
    ]
    current = max(candidates, key=ReleaseVersion.ordering_key)
    bootstrap = not sdk_current and not image_current
    selected = ReleaseVersion.parse(resolve(current.semver(), increment, bootstrap, False))
    if sdk_current and selected == ReleaseVersion.parse(sdk_current):
        raise ValueError(f"SDK release already published: {selected.pep440()}")
    if image_current and selected == ReleaseVersion.parse(image_current):
        raise ValueError(f"Image release already published: {selected.semver()}")
    return selected


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current")
    parser.add_argument("--increment", choices=("beta", "patch", "minor", "major"))
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--pep440", action="store_true")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--shared", action="store_true")
    parser.add_argument("--sdk-current", default="")
    parser.add_argument("--image-current", default="")
    parser.add_argument("--sdk-checked")
    parser.add_argument("--image-checked")
    options = parser.parse_args(arguments)
    if options.latest:
        print(latest(sys.stdin.read().splitlines()))
    elif options.shared:
        if not options.increment or not options.sdk_checked or not options.image_checked:
            parser.error("Shared release requires increment, SDK checked and image checked versions")
        selected = select_shared_release(
            options.sdk_current, options.image_current, options.sdk_checked, options.image_checked, options.increment
        )
        print(f"sdk_version={selected.pep440()}")
        print(f"image_version={selected.semver()}")
    else:
        if not options.current or not options.increment:
            parser.error("Current and increment are required")
        print(resolve(options.current, options.increment, options.bootstrap, options.pep440))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
