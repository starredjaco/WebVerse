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
from webverse.core.registry import USER_LABS_DIR, USER_LEARNING_LABS_DIR


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
    collection: str = "labs"


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


def check_missing(installed_lab_ids: Sequence[str], *, api_base: str = DEFAULT_API_BASE, timeout: float = 6.0, collection: str = "labs") -> List[RemoteLab]:
    """Ask the OSS API which labs are available that are not installed locally."""
    url = f"{api_base}/v1/{collection}/check"
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
                collection=collection,
            ))
        except Exception:
            continue

    # Filter any obviously broken entries
    out = [x for x in out if x.id and x.download_url and x.sha256]
    return out


def install_labs(labs: Sequence[RemoteLab], *, api_base: str = DEFAULT_API_BASE, timeout: float = 18.0) -> List[str]:
    """Download + install the given labs into the appropriate local collection directory.

    Returns a list of installed lab ids.
    """
    installed: List[str] = []
    USER_LABS_DIR.mkdir(parents=True, exist_ok=True)
    USER_LEARNING_LABS_DIR.mkdir(parents=True, exist_ok=True)

    for lab in labs:
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
        if got.lower() != (lab.sha256 or "").lower():
            raise RemoteLabsError(f"Checksum mismatch for {lab.id} (expected {lab.sha256}, got {got})")

        target_root = USER_LEARNING_LABS_DIR if getattr(lab, "collection", "labs") == "learning-labs" else USER_LABS_DIR
        target = (target_root / lab.id)
        tmp_parent = Path(tempfile.mkdtemp(prefix=f"wv_install_{lab.id}_"))
        tmp_extract = tmp_parent / "extract"
        tmp_extract.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(Path(tmp_parent / "lab.zip"), "w") as _:
                pass
            lab_zip_path = tmp_parent / "lab.zip"
            lab_zip_path.write_bytes(blob)

            with zipfile.ZipFile(lab_zip_path, "r") as zf:
                _safe_extract_zip(zf, tmp_extract)

            if not (tmp_extract / "lab.yml").exists():
                raise RemoteLabsError(f"Invalid lab package for {lab.id}: missing lab.yml")

            if target.exists():
                shutil.rmtree(target, ignore_errors=True)

            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(tmp_extract, target)

            installed.append(lab.id)
        except RemoteLabsError:
            raise
        except Exception as e:
            raise RemoteLabsError(f"Failed to install {lab.id}: {e}")
        finally:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    return installed

def check_missing_learning(installed_lab_ids: Sequence[str], *, api_base: str = DEFAULT_API_BASE, timeout: float = 6.0) -> List[RemoteLab]:
    return check_missing(installed_lab_ids, api_base=api_base, timeout=timeout, collection="learning-labs")
