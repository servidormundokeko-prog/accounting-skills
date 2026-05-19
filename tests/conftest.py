"""Make each skill's scripts/ importable in tests without packaging."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

for skill_dir in SKILLS.iterdir():
    scripts = skill_dir / "scripts"
    if scripts.is_dir():
        sys.path.insert(0, str(scripts))
