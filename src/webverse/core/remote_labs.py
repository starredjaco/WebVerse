from __future__ import annotations

import os
import json
import hashlib
import tempfile
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import requests

from webverse import __version__
from webverse.core.registry import USER_LABS_DIR


DEFAULT_API_BASE = os.getenv("WEBVERSE_OPENSOURCE_API_BASE", "https://api-opensource.webverselabs.com").rstrip("/")


@dataclass
class RemoteLab:
    id: str
    name: str
    difficulty: str
    version: str
    sha256: str
    size_bytes: int
    download_url: str


class RemoteLabsError(RuntimeError):
    pass


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract a zip while preventing zip-slip (../) traversal."""
    dest = dest.resolve()
    for info in zf.infolist():
        name = info.filename
        if not name or name.endswith("/"):
            continue

        # Disallow absolute paths and parent traversal
        p = (dest / name).resolve()
        if not str(p).startswith(str(dest) + os.sep):
            raise RemoteLabsError("Refusing to extract unsafe zip entry")

    zf.extractall(dest)


def check_missing(installed_lab_ids: Sequence[str], *, api_base: str = DEFAULT_API_BASE, timeout: float = 6.0) -> List[RemoteLab]:
    """Ask the OSS API which labs are available that are not installed locally."""
    url = f"{api_base}/v1/labs/check"
    payload = {
        "installed": list({str(x) for x in installed_lab_ids if str(x).strip()}),
        "client": {"app_version": __version__},
    }

    try:
        r = requests.post(url, json=payload, timeout=timeout, headers={"User-Agent": f"WebVerse-OSS/{__version__}"})
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        raise RemoteLabsError(f"Failed to check for new labs: {e}")

    missing = data.get("missing") or []
    out: List[RemoteLab] = []
    for item in missing:
        try:
            out.append(RemoteLab(
                id=str(item.get("id") or "").strip(),
                name=str(item.get("name") or "").strip(),
                difficulty=str(item.get("difficulty") or "").strip().lower(),
                version=str(item.get("version") or "").strip(),
                sha256=str(item.get("sha256") or "").strip().lower(),
                size_bytes=int(item.get("size_bytes") or 0),
                download_url=str(item.get("download_url") or "").strip(),
            ))
        except Exception:
            continue

    # Filter any obviously broken entries
    out = [x for x in out if x.id and x.download_url and x.sha256]
    return out


def install_labs(labs: Sequence[RemoteLab], *, api_base: str = DEFAULT_API_BASE, timeout: float = 18.0) -> List[str]:
    """Download + install the given labs into USER_LABS_DIR.

    Returns a list of installed lab ids.
    """
    installed: List[str] = []
    USER_LABS_DIR.mkdir(parents=True, exist_ok=True)

    for lab in labs:
        # Resolve download URL (allow API to hand us a full URL or a relative path)
        dl = lab.download_url

        if dl.startswith("/"):
            dl = f"{api_base}{dl}"
        elif not dl.startswith("http://") and not dl.startswith("https://"):
            dl = f"{api_base}/{dl.lstrip('/')}"

        try:
            r = requests.get(dl, timeout=timeout, headers={"User-Agent": f"WebVerse-OSS/{__version__}"})
            r.raise_for_status()
            blob = r.content
        except Exception as e:
            raise RemoteLabsError(f"Failed to download {lab.id}: {e}")

        got = _sha256_bytes(blob)
        if got != (lab.sha256 or "").lower():
            raise RemoteLabsError(f"Checksum mismatch for {lab.id}")

        target = (USER_LABS_DIR / lab.id)
        tmpdir = Path(tempfile.mkdtemp(prefix=f"webverse_lab_{lab.id}_"))
        tmp_zip: Optional[Path] = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{lab.id}.zip") as f:
                f.write(blob)
                tmp_zip = Path(f.name)

            with zipfile.ZipFile(str(tmp_zip), "r") as zf:
                _safe_extract_zip(zf, tmpdir)

            # The zip may contain either a flat lab folder or a nested folder.
            # Detect the folder that contains lab.yml.
            lab_root: Optional[Path] = None
            if (tmpdir / "lab.yml").exists():
                lab_root = tmpdir
            else:
                for child in tmpdir.iterdir():
                    if child.is_dir() and (child / "lab.yml").exists():
                        lab_root = child
                        break

            if not lab_root:
                raise RemoteLabsError(f"Downloaded lab {lab.id} is missing lab.yml")

            # Replace existing
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)

            target.mkdir(parents=True, exist_ok=True)

            # Copy extracted lab into target
            for p in lab_root.rglob("*"):
                rel = p.relative_to(lab_root)
                dest = target / rel
                if p.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(p), str(dest))

            installed.append(lab.id)
        finally:
            try:
                if tmp_zip and tmp_zip.exists():
                    tmp_zip.unlink(missing_ok=True)
            except Exception:
                pass
            shutil.rmtree(tmpdir, ignore_errors=True)

    return installed
