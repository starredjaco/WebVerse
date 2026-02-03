from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QFrame
)


@dataclass
class InstallableLab:
    id: str
    name: str
    difficulty: str
    version: str
    size_bytes: int


def _pretty_size(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        return "—"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


class InstallLabsDialog(QDialog):
    """Simple picker for installing missing labs."""

    def __init__(self, labs: Sequence[InstallableLab], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Install new labs")
        self.setModal(True)
        self._labs = list(labs)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("New labs available")
        title.setObjectName("H2")
        root.addWidget(title)

        sub = QLabel("Select the labs you want to download and install.")
        sub.setObjectName("Muted")
        root.addWidget(sub)

        box = QFrame()
        box.setObjectName("Panel")
        box_l = QVBoxLayout(box)
        box_l.setContentsMargins(12, 12, 12, 12)
        box_l.setSpacing(8)
        root.addWidget(box, 1)

        self.list = QListWidget()
        self.list.setObjectName("InstallLabsList")
        self.list.setSelectionMode(QListWidget.NoSelection)
        box_l.addWidget(self.list, 1)

        for lab in self._labs:
            text = f"{lab.name}   •   {lab.difficulty.title()}   •   v{lab.version}   •   {_pretty_size(lab.size_bytes)}"
            it = QListWidgetItem(text)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setData(Qt.UserRole, lab.id)
            self.list.addItem(it)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        root.addLayout(btns)

        btns.addStretch(1)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("GhostButton")
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.cancel_btn)

        self.install_btn = QPushButton("Install selected")
        self.install_btn.setObjectName("PrimaryButton")
        self.install_btn.clicked.connect(self.accept)
        btns.addWidget(self.install_btn)

        self.resize(640, 420)

    def selected_ids(self) -> List[str]:
        ids: List[str] = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.Checked:
                ids.append(str(it.data(Qt.UserRole)))
        return ids
