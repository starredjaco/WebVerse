from __future__ import annotations

import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from webverse.core.models import Lab, LearningTrack

def _default_labs_dir() -> Path:
    # Prefer ./labs when running from a repo checkout (dev mode)
    cwd_labs = Path.cwd() / "labs"
    if cwd_labs.exists():
        return cwd_labs
    # Installed location: .../site-packages/webverse/labs
    return Path(__file__).resolve().parent.parent / "labs"


LABS_DIR = _default_labs_dir()

def _default_learning_labs_dir() -> Path:
    cwd_learning = Path.cwd() / "learning-labs"
    if cwd_learning.exists():
        return cwd_learning
    return Path(__file__).resolve().parent.parent / "learning-labs"

LEARNING_LABS_DIR = _default_learning_labs_dir()

def _default_tracks_dir() -> Path:
    cwd_tracks = Path.cwd() / "tracks"
    if cwd_tracks.exists():
        return cwd_tracks
    return Path(__file__).resolve().parent.parent / "tracks"


TRACKS_DIR = _default_tracks_dir()

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

def _user_learning_labs_dir() -> Path:
    p = Path(os.getenv("WEBVERSE_USER_LEARNING_LABS_DIR", str(Path.home() / ".webverse" / "learning-labs"))).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p

USER_LEARNING_LABS_DIR = _user_learning_labs_dir()

def _user_tracks_dir() -> Path:
    p = Path(os.getenv("WEBVERSE_USER_TRACKS_DIR", str(Path.home() / ".webverse" / "tracks"))).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


USER_TRACKS_DIR = _user_tracks_dir()

def _safe_str(x: Any, default: str = "") -> str:
    return str(x).strip() if x is not None else default

def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return s or "track"


def _iter_sorted_dirs(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    try:
        return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name.lower())
    except Exception:
        return []


def _discover_from_dir(labs_dir: Path, *, kind: str = "lab", track: str = "") -> List[Lab]:
    labs: List[Lab] = []
    if not labs_dir.exists():
        return labs

    for lab_dir in _iter_sorted_dirs(labs_dir):
        manifest = lab_dir / "lab.yml"
        if not manifest.exists():
            continue

        try:
            data: Dict[str, Any] = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except Exception:
            continue

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
            path=lab_dir,
            kind=(kind or _safe_str(data.get("kind"), "lab") or "lab").lower(),
            track=_safe_str(data.get("track"), track),
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
            if not lid or lid in seen:
                continue
            seen.add(lid)
            out.append(lab)
    return out

def _parse_track_manifest(track_dir: Path) -> Optional[Tuple[Dict[str, Any], Path]]:
    manifest = track_dir / "track.yml"
    if not manifest.exists():
        return None
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    labs_dir = track_dir / "labs"
    return data, labs_dir


def _discover_tracks_from_root(root: Path) -> List[LearningTrack]:
    tracks: List[LearningTrack] = []
    for track_dir in _iter_sorted_dirs(root):
        parsed = _parse_track_manifest(track_dir)
        if not parsed:
            continue
        data, labs_dir = parsed

        slug = _safe_str(data.get("slug") or data.get("id"), track_dir.name) or track_dir.name
        name = _safe_str(data.get("name"), slug.replace("-", " ").title())
        description = _safe_str(data.get("description"), "")
        short_description = _safe_str(data.get("short_description"), "")
        cover = _safe_str(data.get("cover") or data.get("image"), "")
        difficulty_focus = _safe_str(data.get("difficulty_focus"), "")
        tags_raw = data.get("tags") or []
        if not isinstance(tags_raw, list):
            tags_raw = []
        tags = tuple(_safe_str(t) for t in tags_raw if _safe_str(t))
        order = _safe_int(data.get("order"), 1000)

        labs = _discover_from_dir(labs_dir, kind="learning", track=name)
        labs.sort(key=lambda l: ((l.difficulty or "zzzz").lower(), (l.name or "").lower(), (l.id or "").lower()))

        tracks.append(LearningTrack(
            slug=slug,
            name=name,
            description=description,
            path=track_dir,
            cover=cover,
            short_description=short_description,
            order=order,
            difficulty_focus=difficulty_focus,
            tags=tags,
            labs=tuple(labs),
        ))
    return tracks


def _discover_legacy_learning_tracks() -> List[LearningTrack]:
    # Backwards compatibility: old flat learning-labs/{lab_slug}/lab.yml structure.
    merged: Dict[str, Lab] = {}

    for src in (_discover_from_dir(LEARNING_LABS_DIR, kind="learning"), _discover_from_dir(USER_LEARNING_LABS_DIR, kind="learning"),):
        for lab in src:
            if lab.id:
                merged[lab.id] = lab

    groups: Dict[str, List[Lab]] = {}
    for lab in merged.values():
        track_name = (getattr(lab, "track", "") or "General").strip() or "General"
        groups.setdefault(track_name, []).append(lab)

    tracks: List[LearningTrack] = []
    for idx, track_name in enumerate(sorted(groups.keys(), key=lambda x: x.lower())):
        labs = sorted(groups[track_name], key=lambda l: ((l.difficulty or "zzzz").lower(), (l.name or "").lower(), (l.id or "").lower()))
        tracks.append(LearningTrack(
            slug=_slugify(track_name),
            name=track_name,
            description="",
            path=LEARNING_LABS_DIR,
            cover="",
            order=1000 + idx,
            labs=tuple(labs),
        ))
    return tracks


def discover_learning_tracks() -> List[LearningTrack]:
    """Discover learning tracks from tracks/{track_slug}/track.yml + tracks/{track_slug}/labs/.

    Built-in tracks are loaded first, then user tracks (same slug overrides built-in).
    Falls back to legacy flat learning-labs discovery if no tracks are present.
    """
    merged: Dict[str, LearningTrack] = {}
    for root in (TRACKS_DIR, USER_TRACKS_DIR):
        for track in _discover_tracks_from_root(root):
            if track.slug:
                merged[track.slug] = track
                
    out = list(merged.values())
    out.sort(key=lambda t: (int(getattr(t, "order", 1000)), (t.name or "").lower(), (t.slug or "").lower()))
    if out:
        return out

    return _discover_legacy_learning_tracks()


def discover_learning_labs() -> List[Lab]:
    """Return all learning labs flattened from discovered learning tracks."""
    out: List[Lab] = []
    seen: Set[str] = set()
    for track in discover_learning_tracks():
        for lab in getattr(track, "labs", ()):
            lid = str(getattr(lab, "id", "") or "").strip()
            if not lid or lid in seen:
                continue
            seen.add(lid)
            out.append(lab)
    return out

def installed_lab_ids() -> Set[str]:
    return {str(l.id) for l in discover_labs() if getattr(l, "id", None)}

def installed_learning_lab_ids() -> Set[str]:
    return {str(l.id) for l in discover_learning_labs() if getattr(l, "id", None)}
