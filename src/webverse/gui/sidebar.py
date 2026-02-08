# gui/sidebar.py
from __future__ import annotations

import os
import threading

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QMessageBox
from PyQt5.QtCore import Qt, QSettings, pyqtSignal, QTimer

from webverse.gui.widgets.auth_dialog import LoginDialog, SignupDialog, try_device_login
from webverse.core import progress_db

class _ClickableFrame(QFrame):
	def mousePressEvent(self, e):
		if hasattr(self, "_on_click") and callable(self._on_click):
			self._on_click()
		return super().mousePressEvent(e)


class _NavButton(QPushButton):
	def __init__(self, text: str):
		super().__init__(text)
		self.setObjectName("NavButton")
		self.setCursor(Qt.PointingHandCursor)
		self.setProperty("active", False)
		self.setProperty("locked", False)

	def set_active(self, active: bool):
		self.setProperty("active", active)
		self.style().unpolish(self)
		self.style().polish(self)
		self.update()

	def set_locked(self, locked: bool):
		self.setProperty("locked", bool(locked))
		self.style().unpolish(self)
		self.style().polish(self)
		self.update()


class Sidebar(QFrame):
	auth_changed = pyqtSignal()

	def __init__(self, stack, parent=None, profile_index: int = -1):
		super().__init__(parent)
		self.setObjectName("Sidebar")
		self.stack = stack

		self._settings = QSettings("WebVerse", "WebVerse")
		self._profile_index = profile_index

		layout = QVBoxLayout(self)
		layout.setContentsMargins(14, 14, 14, 14)
		layout.setSpacing(10)

		self.buttons = [
			_NavButton("Home"),
			_NavButton("Browse Labs"),
			_NavButton("Progress"),
			_NavButton("Settings"),
		]

		self._page_for_button = [0, 1, 3, 4]  # Home, Browse, Progress, Settings -> stack index

		page_for_button = [0, 1, 3, 4]  # Home, Browse, Progress, Settings -> stack index
		for i, btn in enumerate(self.buttons):
			btn.clicked.connect(lambda _, x=i: self.set_page(self._page_for_button[x]))
			layout.addWidget(btn)

		layout.addStretch(1)

		# Auth block (replaces Docker badge)
		self.auth_badge = QFrame()
		self.auth_badge.setObjectName("AuthBadge")
		al = QHBoxLayout(self.auth_badge)
		al.setContentsMargins(10, 8, 10, 8)
		al.setSpacing(8)

		self.signup_btn = QPushButton("Signup")
		self.signup_btn.setObjectName("AuthBadgeBtn")
		self.signup_btn.setCursor(Qt.PointingHandCursor)

		self.login_btn = QPushButton("Login")
		self.login_btn.setObjectName("AuthBadgeBtn")
		self.login_btn.setCursor(Qt.PointingHandCursor)

		self.profile_badge = _ClickableFrame()
		self.profile_badge.setObjectName("ProfileBadge")
		self.profile_badge.setAttribute(Qt.WA_StyledBackground, True)

		pl = QVBoxLayout(self.profile_badge)
		pl.setContentsMargins(12, 10, 12, 10)
		pl.setSpacing(6)

		top = QHBoxLayout()
		self.profile_title = QLabel("Profile")
		self.profile_title.setObjectName("ProfileTitle")
		self.profile_meta = QLabel("—")
		self.profile_meta.setObjectName("ProfileMeta")
		top.addWidget(self.profile_title, 1)
		top.addWidget(self.profile_meta, 0, Qt.AlignRight)
		pl.addLayout(top)

		self.profile_xp_bar = QFrame()
		self.profile_xp_bar.setObjectName("XPBar")
		xb = QHBoxLayout(self.profile_xp_bar)
		xb.setContentsMargins(0, 0, 0, 0)
		self.profile_xp_fill = QFrame()
		self.profile_xp_fill.setObjectName("XPFill")
		xb.addWidget(self.profile_xp_fill)
		pl.addWidget(self.profile_xp_bar)

		self.profile_hint = QLabel("Click to view your stats →")
		self.profile_hint.setObjectName("ProfileHint")
		pl.addWidget(self.profile_hint)

		self.profile_badge._on_click = self._open_profile

		al.addWidget(self.signup_btn, 1)
		al.addWidget(self.login_btn, 1)
		al.addWidget(self.profile_badge, 2)
		layout.addWidget(self.auth_badge)

		self.signup_btn.clicked.connect(self._open_signup)
		self.login_btn.clicked.connect(self._open_login)

		# Backwards-compat: keep a hidden docker badge object so any existing
		# code calling set_docker_status() won't crash.
		self.docker_badge = QFrame()
		self.docker_badge.setObjectName("DockerBadge")
		self.docker_text = QLabel("Docker: —")
		self.docker_text.setObjectName("DockerBadgeText")

		# attempt device auto-login if no token yet (delay signal emit until event loop)
		_did_auto_login = False
		if not str(self._settings.value("auth/access_token", "") or "").strip():
			try:
				data = try_device_login(api_base_url=self._api_base_url())
				if isinstance(data, dict) and str(data.get("access_token") or "").strip():
					_did_auto_login = True
			except Exception:
				pass

		self._refresh_auth_ui()

		# Notify the rest of the app (Home/Profile/etc) that auth changed.
		# Use a singleShot so MainWindow has time to connect to this signal during startup.
		if _did_auto_login:
			try:
				QTimer.singleShot(0, self.auth_changed.emit)
			except Exception:
				pass

		# Apply lock AFTER auth UI is known (token/username may be filled by auto-login)
		self._apply_access_lock()

		# If a token exists but is stale, progress_db will clear it on 401 and
		# we should immediately flip UI back to Signup/Login.
		if str(self._settings.value("auth/access_token", "") or "").strip():
			self._refresh_profile_stats_async()

		self.set_page(0)

	# Public hook so ProfileView can force UI refresh after logout.
	def refresh_auth(self):
		self._refresh_auth_ui()
		self._apply_access_lock()

	def set_page(self, index: int):
		# If the device is linked to an account but the user is logged out, disable
		# certain pages (do NOT hard-block the entire GUI).
		if self._is_access_locked_for_index(index):
			# Best-effort: nudge them to login instead of navigating.
			try:
				QMessageBox.information(self, "Login required", "Login to access this page.")
			except Exception:
				pass
			return

		# index is the STACK index (not the button index)
		self.stack.setCurrentIndex(index)

		# Active state is based on "context"
		# Home -> 0
		# Browse Labs list -> 1
		# Lab detail -> 2 (NO sidebar selection)
		# Progress -> 3
		# Settings -> 4
		active_btn = None
		if index == 0:
			active_btn = 0
		elif index == 1:
			active_btn = 1
		elif index == 3:
			active_btn = 2
		elif index == 4:
			active_btn = 3

		for i, btn in enumerate(self.buttons):
			btn.set_active(active_btn is not None and i == active_btn)

	def _device_is_linked(self) -> bool:
		"""
		Only apply access lock if this device is linked to an account.
		This allows fully-offline/guest usage when a device has never been linked.
		"""
		# 1) Prefer an explicit helper in progress_db if you have one.
		for fn_name in ("is_device_linked", "device_is_linked", "is_device_linked_to_account", "device_linked"):
			try:
				fn = getattr(progress_db, fn_name, None)
				if callable(fn):
					return bool(fn())
			except Exception:
				pass

		# 2) Fallback to persisted settings flags if present.
		try:
			v = self._settings.value("auth/device_linked", None)
			if v is not None:
				if isinstance(v, str):
					return v.strip().lower() in ("1", "true", "yes", "y", "on")
				return bool(v)
		except Exception:
			pass

		# 3) Last-resort heuristic: if we have ever had a username saved, we consider it linked.
		try:
			u = str(self._settings.value("auth/username", "") or "").strip()
			return bool(u)
		except Exception:
			return False

	def _is_logged_in(self) -> bool:
		token = str(self._settings.value("auth/access_token", "") or "").strip()
		username = str(self._settings.value("auth/username", "") or "").strip()
		return bool(token and username)

	def _is_access_locked_for_index(self, stack_index: int) -> bool:
		# Lock only applies if device is linked AND user is logged out.
		if not self._device_is_linked():
			return False
		if self._is_logged_in():
			return False

		# Pages to disable when linked-but-logged-out:
		# - Browse (1), Lab Detail (2), Progress (3), Settings (4), Profile (profile_index)
		# Keep Home/Browse/Settings accessible so they can still use the app + login.
		restricted = {1, 2, 3, 4}
		if self._profile_index is not None and self._profile_index >= 0:
			restricted.add(int(self._profile_index))
		return int(stack_index) in restricted

	def _apply_access_lock(self) -> None:
		locked = (self._device_is_linked() and (not self._is_logged_in()))

		# Buttons correspond to: Home(0), Browse(1), Progress(3), Settings(4)
		# Locked: disable Browse + Progress + Settings (Home stays enabled).
		try:
			# Home
			self.buttons[0].setEnabled(True)
			self.buttons[0].set_locked(False)
			# Browse
			self.buttons[1].setEnabled(not locked)
			self.buttons[1].set_locked(locked)
			# Progress
			self.buttons[2].setEnabled(not locked)
			self.buttons[2].set_locked(locked)
			# Settings
			self.buttons[3].setEnabled(not locked)
			self.buttons[3].set_locked(locked)
		except Exception:
			pass

		# Profile badge itself should only be clickable when logged in.
		try:
			self.profile_badge.setEnabled((not locked) and self._is_logged_in())
			self.profile_badge.setProperty("locked", bool(locked))
			self.profile_badge.style().unpolish(self.profile_badge)
			self.profile_badge.style().polish(self.profile_badge)
			self.profile_badge.update()
		except Exception:
			pass

		# Tooltips so it's obvious *why* they're disabled
		tip = "Locked — login required" if locked else ""
		try:
			self.buttons[1].setToolTip(tip)
			self.buttons[2].setToolTip(tip)
			self.buttons[3].setToolTip(tip)
			self.profile_badge.setToolTip(tip)
		except Exception:
			pass

	def _api_base_url(self) -> str:
		# Prefer new env var; keep legacy var for backwards compat.
		return os.getenv(
			"WEBVERSE_API_BASE_URL",
			os.getenv("WEBVERSE_API_URL", "https://api-opensource.webverselabs.com"),
		).rstrip("/")

	def _refresh_auth_ui(self):
		token = str(self._settings.value("auth/access_token", "") or "").strip()
		username = str(self._settings.value("auth/username", "") or "").strip()
		rank = str(self._settings.value("auth/rank", "") or "").strip()
		xp = int(self._settings.value("auth/xp", 0) or 0)

		# Logged-in UI should require BOTH a token and username.
		# Token validity is enforced by progress_db: if /v1/auth/me returns 401,
		# it clears token/username and this becomes False.
		logged_in = bool(token and username)

		# Parent disable cascades. Always re-enable the whole block before toggling children.
		try:
			self.setEnabled(True)
			self.auth_badge.setEnabled(True)
		except Exception:
			pass

		# If anything previously disabled/locked this block, undo it here.
		# (Disabled state can persist even after setVisible(True).)
		try:
			self.auth_badge.setEnabled(True)
		except Exception:
			pass
		for w in (self.profile_badge, self.signup_btn, self.login_btn):
			try:
				w.setEnabled(True)
				# If you use a QSS rule like [locked="true"], make sure it's cleared.
				w.setProperty("locked", False)
				w.style().unpolish(w)
				w.style().polish(w)
				w.update()
			except Exception:
				pass

		self.signup_btn.setVisible(not logged_in)
		self.login_btn.setVisible(not logged_in)
		self.profile_badge.setVisible(logged_in)

		if logged_in:
			# HARD force: if we’re logged in, the badge must be clickable and non-grey.
			try:
				self.profile_badge.setEnabled(True)
				self.profile_badge.setProperty("locked", False)
				self.profile_badge.style().unpolish(self.profile_badge)
				self.profile_badge.style().polish(self.profile_badge)
				self.profile_badge.update()
			except Exception:
				pass

			label = f"{username}"
			if rank:
				label = f"{username} · {rank}"
			self.profile_title.setText(label)
			self.profile_meta.setText(f"{xp} XP")

			# best-effort fill width based on next threshold (rough)
			pct = 0.12
			if xp >= 12000:
				pct = 1.0
			elif xp >= 7000:
				pct = min(1.0, (xp - 7000) / 5000.0)
			elif xp >= 3500:
				pct = min(1.0, (xp - 3500) / 3500.0)
			elif xp >= 1500:
				pct = min(1.0, (xp - 1500) / 2000.0)
			elif xp >= 500:
				pct = min(1.0, (xp - 500) / 1000.0)
			else:
				pct = min(1.0, xp / 500.0)

			w = max(8, int(220 * max(0.02, min(1.0, pct))))
			self.profile_xp_fill.setFixedWidth(w)

		# Always keep locks consistent with auth UI state (runs last)
		self._apply_access_lock()

		# Final safety: if we’re logged in, never leave it disabled OR locked-styled.
		if logged_in:
			try:
				self.profile_badge.setEnabled(True)
				self.profile_badge.setProperty("locked", False)  # must override any stale lock prop

				# Also ensure children don't inherit disabled state styling
				for w in (self.profile_title, self.profile_meta, self.profile_hint, self.profile_xp_bar, self.profile_xp_fill):
					try:
						w.setEnabled(True)
					except Exception:
						pass

				self.profile_badge.style().unpolish(self.profile_badge)
				self.profile_badge.style().polish(self.profile_badge)
				self.profile_badge.update()
			except Exception:
				pass

	def _refresh_profile_stats_async(self):
		# Best-effort cloud refresh; never blocks the UI.
		def _bg():
			try:
				progress_db.get_device_stats(force=True)
				from PyQt5.QtCore import QTimer
				QTimer.singleShot(0, self._refresh_auth_ui)
			except Exception:
				pass

		threading.Thread(target=_bg, daemon=True).start()

	def _open_signup(self):
		dlg = SignupDialog(api_base_url=self._api_base_url(), parent=self)
		if dlg.exec_() == dlg.Accepted:
			QMessageBox.information(self, "Signup", "Signup successful. You're logged in.")
			self._refresh_profile_stats_async()
			self._refresh_auth_ui()

			try:
				self.auth_changed.emit()
			except Exception:
				pass

	def _open_login(self):
		dlg = LoginDialog(api_base_url=self._api_base_url(), parent=self)
		if dlg.exec_() == dlg.Accepted:
			QMessageBox.information(self, "Login", "Login successful.")
			self._refresh_profile_stats_async()
			self._refresh_auth_ui()

			try:
				self.auth_changed.emit()
			except Exception:
				pass

	def _open_profile(self):
		# Respect lock rules (linked device but logged out)
		if self._is_access_locked_for_index(self._profile_index):
			self._open_login()
			return

		if self._profile_index is not None and self._profile_index >= 0:
			# Always re-activate profile (fast refresh) on every click.
			try:
				w = self.stack.widget(self._profile_index)
				if hasattr(w, "on_activated"):
					w.on_activated()
			except Exception:
				pass
			self.set_page(self._profile_index)

	def set_docker_status(self, text: str, kind: str = "neutral"):
		# Docker badge is no longer shown; surface status as a tooltip on the auth block.
		if hasattr(self, "auth_badge") and self.auth_badge is not None:
			self.auth_badge.setToolTip(text)
			self.signup_btn.setToolTip(text)
			self.login_btn.setToolTip(text)

		palette = {
			"ok": ("rgba(34,197,94,0.14)", "rgba(34,197,94,0.30)"),
			"warn": ("rgba(245,158,11,0.14)", "rgba(245,158,11,0.30)"),
			"bad": ("rgba(239,68,68,0.14)", "rgba(239,68,68,0.30)"),
			"neutral": ("rgba(16,20,28,0.55)", "rgba(255,255,255,0.08)"),
		}
		
		bg, bd = palette.get(kind, palette["neutral"])
		if getattr(self, "docker_badge", None) is not None:
			self.docker_badge.setStyleSheet(
				f"QFrame#DockerBadge {{ background: {bg}; border: 1px solid {bd}; }}"
			)
		if getattr(self, "docker_text", None) is not None:
			self.docker_text.setText(text)
