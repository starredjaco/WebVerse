from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

@dataclass(frozen=True)
class Lab:
    id: str
    name: str
    description: str
    story: str
    difficulty: str
    path: Path

    # Optional relative path to a lab image (e.g., "cover.png") from lab.yml: image: cover.png
    image: str = ""

    # docker-compose.yml file name (relative to lab path)
    compose_file: str = "docker-compose.yml"

    # Entry info from lab.yml (typically contains base_url, etc.)
    entrypoint: Dict[str, Any] = None

    # sha256 of the exact flag string (after stripping whitespace)
    flag_sha256: str = ""

    def base_url(self) -> Optional[str]:
        if isinstance(self.entrypoint, dict):
            v = self.entrypoint.get("base_url")
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    def image_path(self) -> Optional[Path]:
        """
        Resolve the lab image relative to the lab directory.
        Works in repo runs and pipx installs because lab.path is absolute.
        """
        img = (self.image or "").strip()
        if not img:
            return None

        try:
            p = Path(img)
            if not p.is_absolute():
                p = (self.path / p).resolve()
            if p.exists():
                return p
        except Exception:
            return None

        return None
