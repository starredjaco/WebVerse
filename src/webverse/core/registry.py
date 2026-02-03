from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from webverse.core.models import Lab

def _default_labs_dir() -> Path:
    # Prefer ./labs when running from a repo checkout (dev mode)
    cwd_labs = Path.cwd() / "labs"
    if cwd_labs.exists():
        return cwd_labs
    # Installed location: .../site-packages/webverse/labs
    return Path(__file__).resolve().parent.parent / "labs"


LABS_DIR = _default_labs_dir()

def _user_labs_dir() -> Path:
    """Directory for user-installed labs (downloaded from the OSS API).
       Defaults to ~/.webverse/labs, override with WEBVERSE_USER_LABS_DIR.
    """
    p = Path(os.getenv("WEBVERSE_USER_LABS_DIR", str(Path.home() / ".webverse" / "labs"))).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        # If this fails, discovery will simply return built-in labs.
        pass
    return p


USER_LABS_DIR = _user_labs_dir()

def _safe_str(x: Any, default: str = "") -> str:
    return str(x).strip() if x is not None else default

def _discover_from_dir(labs_dir: Path) -> List[Lab]:
    labs: List[Lab] = []
    if not labs_dir.exists():
        return labs

    for lab_dir in sorted(labs_dir.iterdir()):
        if not lab_dir.is_dir():
            continue

        manifest = lab_dir / "lab.yml"
        if not manifest.exists():
            continue

        data: Dict[str, Any] = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        entry = data.get("entrypoint") or {}
        if not isinstance(entry, dict):
            entry = {"value": entry}

        labs.append(Lab(
            id=_safe_str(data.get("id"), lab_dir.name),
            name=_safe_str(data.get("name"), lab_dir.name),
            description=_safe_str(data.get("description"), ""),
            story=_safe_str(data.get("story"), ""),
            difficulty=_safe_str(data.get("difficulty"), "unknown").lower(),
            image=_safe_str(data.get("image"), ""),
            compose_file=_safe_str(data.get("compose_file"), "docker-compose.yml"),
            entrypoint=entry,
            flag_sha256=_safe_str(data.get("flag_sha256"), ""),
            path=lab_dir
        ))
    return labs

def discover_labs(labs_dir: Optional[Path] = None) -> List[Lab]:
    """Discover labs from built-in + user-installed directories.

    Each lab folder must include:
      - lab.yml
      - docker-compose.yml (or compose_file specified in lab.yml)

    lab.yml schema (minimal):
      id: <slug>
      name: <display name>
      difficulty: easy|medium|hard|insane
      description: <text>
      story: <narrative briefing text>
      image: cover.png  # optional (path relative to lab folder)
      compose_file: docker-compose.yml
      entrypoint:
        base_url: http://something.local/
      flag_sha256: <sha256 of the flag string (strip whitespace)>
    """
    dirs: List[Path] = []
    if labs_dir is not None:
        dirs.append(labs_dir)
    else:
        # Built-in labs first, then user-installed labs.
        dirs.extend([LABS_DIR, USER_LABS_DIR])

    seen: Set[str] = set()
    out: List[Lab] = []
    for d in dirs:
        for lab in _discover_from_dir(d):
            lid = str(getattr(lab, "id", "") or "").strip()
            if not lid:
                continue
            if lid in seen:
                continue
            seen.add(lid)
            out.append(lab)
    return out


def installed_lab_ids() -> List[str]:
    """Convenience: list all installed lab ids (built-in + user-installed)."""
    return [str(x.id) for x in discover_labs()]
