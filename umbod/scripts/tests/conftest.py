import sys
from pathlib import Path


SKILL_SCRIPTS = Path(__file__).resolve().parents[3] / "skills" / "development" / "write-module-readme" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
