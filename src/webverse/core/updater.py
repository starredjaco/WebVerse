# webverse/core/updater.py
from __future__ import annotations

import os
import time
import json
import requests
from dataclasses import dataclass
from packaging.version import Version, InvalidVersion

from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from webverse import __version__


@dataclass
class UpdateInfo:
    latest_version: str
    url: str
    notes: str = ""


class UpdateManager(QObject):
    update_available = pyqtSignal(object)  # UpdateInfo
    update_check_failed = pyqtSignal(str)

    def __init__(self, owner: str, repo: str, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.repo = repo

        self._timer = QTimer(self)
        self._timer.setInterval(1000 * 60 * 60 * 6)  # every 6 hours
        self._timer.timeout.connect(self.check_for_updates)

        self._last_emit_ver = None

    def start(self):
        self._timer.start()
        QTimer.singleShot(1200, self.check_for_updates)  # small delay after startup

    def check_for_updates(self):
        try:
            api = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"
            r = requests.get(
                api,
                timeout=6,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"webverse/{__version__}",
                },
            )
            if r.status_code != 200:
                self.update_check_failed.emit(f"Update check failed: HTTP {r.status_code}")
                return

            data = r.json()
            tag = (data.get("tag_name") or "").strip()
            html_url = (data.get("html_url") or "").strip()
            notes = (data.get("body") or "").strip()

            if not tag:
                return

            cur = self._parse_ver(__version__)
            latest = self._parse_ver(tag.lstrip("v"))

            if latest and cur and latest > cur:
                if self._last_emit_ver != str(latest):
                    self._last_emit_ver = str(latest)
                    self.update_available.emit(UpdateInfo(str(latest), html_url, notes))

        except Exception as e:
            self.update_check_failed.emit(str(e))

    def _parse_ver(self, s: str):
        try:
            return Version(s)
        except InvalidVersion:
            return None
