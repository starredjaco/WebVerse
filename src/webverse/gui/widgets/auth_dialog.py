from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import (
	QCheckBox,
	QDialog,
	QFrame,
	QHBoxLayout,
	QLineEdit,
	QLabel,
	QLineEdit,
	QMessageBox,
	QPushButton,
	QVBoxLayout,
	QWidget,
)


def _post_json(url: str, payload: Dict[str, Any], timeout: int = 8) -> Dict[str, Any]:
	data = json.dumps(payload).encode("utf-8")
	req = urllib.request.Request(
		url=url,
		data=data,
		headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "WebVerse-OSS/1.0"},
		method="POST",
	)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			body = resp.read().decode("utf-8") or "{}"
			return json.loads(body)
	except urllib.error.HTTPError as e:
		try:
			body = e.read().decode("utf-8") or "{}"
			j = json.loads(body)
			msg = j.get("detail") or body
		except Exception:
			msg = str(e)
		raise RuntimeError(msg)
	except Exception as e:
		raise RuntimeError(str(e))

def _get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 8) -> Dict[str, Any]:
	req = urllib.request.Request(
		url=url,
		headers={**(headers or {}), "Accept": "application/json", "User-Agent": "WebVerse-OSS/1.0"},
		method="GET",
	)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			body = resp.read().decode("utf-8") or "{}"
			return json.loads(body)
	except Exception as e:
		raise RuntimeError(str(e))


class _BaseAuthDialog(QDialog):
	def __init__(self, *, title: str, api_base_url: str, parent=None):
		super().__init__(parent)
		self.setWindowTitle(title)
		self.api_base_url = (api_base_url or "").rstrip("/")
		self._settings = QSettings("WebVerse", "WebVerse")
		self._busy = False

		# Make the auth UI feel like a first-class product dialog.
		self.setModal(True)
		self.setMinimumWidth(520)

	def _device_id(self) -> str:
		# Use the same device_id that telemetry/progress uses.
		try:
			from webverse.core.progress_db import get_device_id
			return str(get_device_id())
		except Exception:
			did = str(self._settings.value("device/id", "") or "").strip()
			if did:
				return did
			did = str(uuid.uuid4())
			self._settings.setValue("device/id", did)
			return did

	def _save_auth(self, data: Dict[str, Any]) -> None:
		token = data.get("access_token")
		user = data.get("user") or {}
		if token:
			self._settings.setValue("auth/access_token", token)

		if user.get("email"):
			self._settings.setValue("auth/email", user.get("email"))

		if user.get("username"):
			self._settings.setValue("auth/username", user.get("username"))

		if user.get("rank"):
			self._settings.setValue("auth/rank", user.get("rank"))

		if user.get("xp") is not None:
			self._settings.setValue("auth/xp", int(user.get("xp") or 0))

		# Ensure settings are flushed immediately so any already-created views
		# can read the token right away.
		try:
			self._settings.sync()
		except Exception:
			pass

		# Invalidate cached remote state so views repaint immediately.
		try:
			from webverse.core import progress_db
			progress_db.invalidate_remote_cache()
		except Exception:
			pass

		"""try:
			from webverse.core.progress_db import invalidate_remote_cache
			invalidate_remote_cache()
		except Exception:
			pass"""

	def _field(self, label: str, widget: QWidget) -> QWidget:
		wrap = QWidget()
		wrap.setObjectName("AuthField")
		v = QVBoxLayout(wrap)
		v.setContentsMargins(0, 0, 0, 0)
		v.setSpacing(6)
		lbl = QLabel(label)
		lbl.setObjectName("AuthFieldLabel")
		v.addWidget(lbl)
		v.addWidget(widget)
		return wrap

	def _set_busy(self, busy: bool) -> None:
		self._busy = bool(busy)
		for name in ("_primary_btn", "_cancel_btn"):
			btn = getattr(self, name, None)
			if btn is not None:
				try:
					btn.setEnabled(not busy)
				except Exception:
					pass

		# Disable inputs if present.
		for name in ("username", "email", "password", "show_pw"):
			w = getattr(self, name, None)
			if w is not None:
				try:
					w.setEnabled(not busy)
				except Exception:
					pass



class SignupDialog(_BaseAuthDialog):
	def __init__(self, *, api_base_url: str, parent=None):
		super().__init__(title="Signup", api_base_url=api_base_url, parent=parent)

		self.setObjectName("AuthDialog")
		root = QVBoxLayout(self)
		root.setContentsMargins(18, 18, 18, 18)
		root.setSpacing(12)

		title = QLabel("Create your WebVerse account")
		title.setObjectName("AuthTitle")
		sub = QLabel("Sync your progress, earn rank, and build streaks.")
		sub.setObjectName("AuthSub")
		root.addWidget(title)
		root.addWidget(sub)

		panel = QFrame()
		panel.setObjectName("AuthPanel")
		pv = QVBoxLayout(panel)
		pv.setContentsMargins(14, 14, 14, 14)
		pv.setSpacing(10)

		self.username = QLineEdit()
		self.username.setObjectName("AuthInput")
		self.username.setPlaceholderText("e.g. Leighlin")
		self.email = QLineEdit()
		self.email.setObjectName("AuthInput")
		self.email.setPlaceholderText("you@example.com")
		self.password = QLineEdit()
		self.password.setObjectName("AuthInput")
		self.password.setPlaceholderText("Minimum 8 characters")
		self.password.setEchoMode(QLineEdit.Password)

		pv.addWidget(self._field("Username", self.username))
		pv.addWidget(self._field("Email", self.email))
		pv.addWidget(self._field("Password", self.password))

		row = QHBoxLayout()
		self.show_pw = QCheckBox("Show password")
		self.show_pw.setObjectName("AuthCheck")
		self.show_pw.toggled.connect(lambda v: self.password.setEchoMode(QLineEdit.Normal if v else QLineEdit.Password))

		row.addWidget(self.show_pw)
		row.addStretch(1)
		pv.addLayout(row)

		root.addWidget(panel)

		btn_row = QHBoxLayout()
		btn_row.addStretch(1)
		self._cancel_btn = QPushButton("Cancel")
		self._cancel_btn.setObjectName("GhostButton")
		self._cancel_btn.clicked.connect(self.reject)

		self._primary_btn = QPushButton("Create account")
		self._primary_btn.setObjectName("PrimaryButton")
		self._primary_btn.setDefault(True)
		self._primary_btn.clicked.connect(self._submit)

		btn_row.addWidget(self._cancel_btn)
		btn_row.addWidget(self._primary_btn)
		root.addLayout(btn_row)

		# UX: Enter moves through fields, final Enter submits.
		self.username.returnPressed.connect(lambda: self.email.setFocus())
		self.email.returnPressed.connect(lambda: self.password.setFocus())
		self.password.returnPressed.connect(self._submit)

		self.username.setFocus()

	def _submit(self) -> None:
		if self._busy:
			return

		payload = {
			"username": self.username.text().strip(),
			"email": self.email.text().strip(),
			"password": self.password.text(),
			"device_id": self._device_id(),
			# keep the feature, but remove the UI option (always trust this device)
			"trust_device": True,
		}
		if not payload["username"] or not payload["email"] or not payload["password"]:
			QMessageBox.warning(self, "Signup", "Please fill out all fields.")
			return

		self._set_busy(True)
		try:
			data = _post_json(f"{self.api_base_url}/v1/auth/signup", payload)
			self._save_auth(data)
			self.accept()
		except Exception as e:
			self._set_busy(False)
			QMessageBox.critical(self, "Signup failed", str(e))


class LoginDialog(_BaseAuthDialog):
	def __init__(self, *, api_base_url: str, parent=None):
		super().__init__(title="Login", api_base_url=api_base_url, parent=parent)

		self.setObjectName("AuthDialog")
		root = QVBoxLayout(self)
		root.setContentsMargins(18, 18, 18, 18)
		root.setSpacing(12)

		title = QLabel("Welcome back")
		title.setObjectName("AuthTitle")
		sub = QLabel("Login to sync rank, streaks, and progress.")
		sub.setObjectName("AuthSub")
		root.addWidget(title)
		root.addWidget(sub)

		panel = QFrame()
		panel.setObjectName("AuthPanel")
		pv = QVBoxLayout(panel)
		pv.setContentsMargins(14, 14, 14, 14)
		pv.setSpacing(10)

		self.email = QLineEdit()
		self.email.setObjectName("AuthInput")
		self.email.setPlaceholderText("you@example.com")

		# Prefill last used email (helps feel polished).
		try:
			prev = str(self._settings.value("auth/email", "") or "").strip()
			if prev:
				self.email.setText(prev)
		except Exception:
			pass

		self.password = QLineEdit()
		self.password.setObjectName("AuthInput")
		self.password.setPlaceholderText("Your password")
		self.password.setEchoMode(QLineEdit.Password)

		pv.addWidget(self._field("Email", self.email))
		pv.addWidget(self._field("Password", self.password))

		row = QHBoxLayout()
		self.show_pw = QCheckBox("Show password")
		self.show_pw.setObjectName("AuthCheck")
		self.show_pw.toggled.connect(lambda v: self.password.setEchoMode(QLineEdit.Normal if v else QLineEdit.Password))

		row.addWidget(self.show_pw)
		row.addStretch(1)
		pv.addLayout(row)

		root.addWidget(panel)

		btn_row = QHBoxLayout()
		btn_row.addStretch(1)
		self._cancel_btn = QPushButton("Cancel")
		self._cancel_btn.setObjectName("GhostButton")
		self._cancel_btn.clicked.connect(self.reject)

		self._primary_btn = QPushButton("Login")
		self._primary_btn.setObjectName("PrimaryButton")
		self._primary_btn.setDefault(True)
		self._primary_btn.clicked.connect(self._submit)

		btn_row.addWidget(self._cancel_btn)
		btn_row.addWidget(self._primary_btn)
		root.addLayout(btn_row)

		# UX: Enter moves to password, final Enter submits.
		self.email.returnPressed.connect(lambda: self.password.setFocus())
		self.password.returnPressed.connect(self._submit)

		if self.email.text().strip():
			self.password.setFocus()
		else:
			self.email.setFocus()

	def _submit(self) -> None:
		if self._busy:
			return

		payload = {
			"email": self.email.text().strip(),
			"password": self.password.text(),
			"device_id": self._device_id(),
			# keep the feature, but remove the UI option (always trust this device)
			"trust_device": True,
		}
		if not payload["email"] or not payload["password"]:
			QMessageBox.warning(self, "Login", "Please fill out all fields.")
			return

		self._set_busy(True)
		try:
			data = _post_json(f"{self.api_base_url}/v1/auth/login", payload)
			self._save_auth(data)
			self.accept()
		except Exception as e:
			self._set_busy(False)
			QMessageBox.critical(self, "Login failed", str(e))

def try_device_login(*, api_base_url: str) -> Optional[Dict[str, Any]]:
	s = QSettings("WebVerse", "WebVerse")
	did = str(s.value("device/id", "") or "").strip()
	if not did:
		return None
	try:
		data = _post_json(f"{api_base_url.rstrip('/')}/v1/auth/device-login", {"device_id": did}, timeout=5)
		token = data.get("access_token")
		user = data.get("user") or {}
		if token:
			s.setValue("auth/access_token", token)
		if user.get("email"):
			s.setValue("auth/email", user.get("email"))
		if user.get("username"):
			s.setValue("auth/username", user.get("username"))
		if user.get("rank"):
			s.setValue("auth/rank", user.get("rank"))
		if user.get("xp") is not None:
			s.setValue("auth/xp", int(user.get("xp") or 0))

		try:
			s.sync()
		except Exception:
			pass

		return data
	except Exception:
		return None
