from __future__ import annotations

from typing import List, Sequence

from PyQt5.QtCore import QObject, pyqtSignal

from webverse.core.registry import installed_lab_ids
from webverse.core.remote_labs import RemoteLab, RemoteLabsError, check_missing, install_labs


class RemoteLabsWorker(QObject):
    checked = pyqtSignal(object)  # list[RemoteLab]
    installed = pyqtSignal(object)  # list[str] (lab ids)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def check(self) -> None:
        try:
            labs = check_missing(installed_lab_ids())
            self.checked.emit(labs)
        except Exception as e:
            self.error.emit(str(e))

    def install(self, labs: Sequence[RemoteLab]) -> None:
        try:
            ids = install_labs(list(labs))
            self.installed.emit(ids)
        except RemoteLabsError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(str(e))
