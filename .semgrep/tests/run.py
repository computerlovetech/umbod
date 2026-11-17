import json
import logging
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from typing import NotRequired, TypedDict, cast
except ImportError:
    uv = shutil.which("uv")
    if uv is None:
        logging.error("uv is not installed")
        sys.exit(1)
    runner = Path(__file__).resolve()
    sys.exit(
        subprocess.run(
            [uv, "run", "--project", str(runner.parents[2] / "umbod"), "python", str(runner)],
            check=False,
        ).returncode
    )


class Case(TypedDict):
    name: str
    path: NotRequired[str]
    source: str
    expected: dict[str, dict[str, int]]


def run() -> int:
    directory = Path(__file__).resolve().parent
    cases = cast(list[Case], json.loads((directory / "cases.json").read_text()))
    executable = shutil.which("uv")
    if executable is None:
        logging.error("uv is not installed")
        return 1
    with TemporaryDirectory(prefix="semgrep-regressions-") as temporary:
        root = Path(temporary)
        expected: Counter[tuple[str, str, int]] = Counter()
        probes: set[str] = set()
        for case in cases:
            case_root = root / case["name"]
            probe = case_root / case.get("path", "api/src/probe.py")
            if not probe.resolve().is_relative_to(case_root.resolve()):
                raise ValueError(f"Invalid probe path: {case['name']}")
            probe.parent.mkdir(parents=True)
            probe.write_text(case["source"])
            relative = probe.relative_to(root).as_posix()
            if relative in probes:
                raise ValueError(f"Duplicate case: {case['name']}")
            probes.add(relative)
            for rule, lines in case["expected"].items():
                for line, count in lines.items():
                    expected[relative, rule, int(line)] = count
        result = subprocess.run(
            [
                executable,
                "run",
                "--project",
                str(directory.parent.parent / "umbod"),
                "semgrep",
                "scan",
                "--config",
                str(directory.parent / "production-design.yml"),
                "--no-rewrite-rule-ids",
                "--no-git-ignore",
                "--json",
                "--metrics=off",
                "--disable-version-check",
                str(root),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logging.error("Semgrep failed (%s): %s", result.returncode, result.stderr)
            return 1
        report = json.loads(result.stdout)
        if report.get("errors"):
            logging.error("Semgrep scan errors: %s", report["errors"])
            return 1
        scanned = {Path(path).relative_to(root).as_posix() for path in report["paths"]["scanned"]}
        if scanned != probes:
            logging.error("Scanned paths mismatch: expected=%s actual=%s", probes, scanned)
            return 1
        actual = Counter(
            (
                Path(finding["path"]).relative_to(root).as_posix(),
                finding["check_id"],
                finding["start"]["line"],
            )
            for finding in report["results"]
        )
        if actual != expected:
            logging.error("Missing findings: %s", dict(expected - actual))
            logging.error("Unexpected findings: %s", dict(actual - expected))
            return 1
    logging.info("Passed %s cases (%s expected findings)", len(cases), expected.total())
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sys.exit(run())
