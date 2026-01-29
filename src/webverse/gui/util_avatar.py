# gui/util_avatar.py
from __future__ import annotations

from typing import Dict, Tuple
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QIcon
from PyQt5.QtCore import Qt

_cache: Dict[Tuple[str, str, int], QIcon] = {}

def _initials(name: str) -> str:
	s = (name or "").strip()
	if not s:
		return "?"
	parts = [p for p in s.replace("-", " ").split() if p]
	if len(parts) == 1:
		return parts[0][:2].upper()
	return (parts[0][0] + parts[1][0]).upper()

def _ring_color(difficulty):
	"""
	Returns a QColor.

	Accepts difficulty as:
	  - string: "easy"/"medium"/"hard"/"master"
	  - int: 1..5 (or 0..4)
	"""
	# Normalize difficulty into a label
	if difficulty is None:
		d = ""
	elif isinstance(difficulty, (int, float)):
		n = int(difficulty)
		# common tier mapping
		if n <= 1:
			d = "easy"
		elif n == 2:
			d = "medium"
		elif n == 3:
			d = "hard"
		else:
			d = "master"
	else:
		d = str(difficulty).lower().strip()

	# Map to QColor
	if d in ("easy", "beginner", "1"):
		return QColor("#22c55e")  # green
	if d in ("medium", "intermediate", "2"):
		return QColor("#f5c542")  # amber
	if d in ("hard", "advanced", "3"):
		return QColor("#ef4444")  # red
	if d in ("master", "insane", "expert", "4", "5"):
		return QColor("#a855f7")  # violet

	return QColor("#64748b")      # muted slate

def lab_circle_icon(lab_name: str, difficulty: str, size: int = 44) -> QIcon:
	key = (lab_name or "", difficulty or "", size)
	if key in _cache:
		return _cache[key]

	px = QPixmap(size, size)
	px.fill(Qt.transparent)

	ring = _ring_color(difficulty)
	inner = QColor(16, 20, 28, int(0.75 * 255))
	text = QColor(235, 241, 255, int(0.92 * 255))

	p = QPainter(px)
	p.setRenderHint(QPainter.Antialiasing, True)

	# outer ring
	p.setPen(Qt.NoPen)
	p.setBrush(QColor(ring.red(), ring.green(), ring.blue(), int(0.85 * 255)))
	p.drawEllipse(0, 0, size, size)

	# inner circle
	inset = 4
	p.setBrush(inner)
	p.drawEllipse(inset, inset, size - inset*2, size - inset*2)

	# subtle highlight
	p.setBrush(QColor(255, 255, 255, 12))
	p.drawEllipse(inset + 1, inset + 1, size - (inset+1)*2, size - (inset+1)*2)

	# initials
	p.setPen(text)
	f = QFont("Inter")
	f.setBold(True)
	f.setPointSize(max(9, int(size * 0.24)))
	p.setFont(f)
	p.drawText(px.rect(), Qt.AlignCenter, _initials(lab_name))

	p.end()

	# Prevent Qt/style from tinting/recoloring the icon when the item is Selected/Active.
	# We pin the exact same pixmap into all modes.
	icon = QIcon()
	icon.addPixmap(px, QIcon.Normal, QIcon.Off)
	icon.addPixmap(px, QIcon.Active, QIcon.Off)
	icon.addPixmap(px, QIcon.Selected, QIcon.Off)
	icon.addPixmap(px, QIcon.Disabled, QIcon.Off)

	_cache[key] = icon
	return icon

def lab_badge_icon(lab_name: str, difficulty: str, image_path=None, size: int = 44) -> QIcon:
	"""Circular badge icon.

	If image_path is provided and loads successfully, it will be clipped into the inner circle.
	Otherwise, falls back to initials.
	"""
	img_key = ""
	mtime = 0
	try:
		if image_path:
			img_key = str(image_path)
			import os
			if os.path.exists(img_key):
				mtime = int(os.path.getmtime(img_key))
	except Exception:
		img_key = str(image_path or "")
		mtime = 0

	key = (lab_name or "", str(difficulty or ""), size, img_key, mtime)
	if key in _cache:
		return _cache[key]

	px = QPixmap(size, size)
	px.fill(Qt.transparent)

	ring = _ring_color(difficulty)
	inner = QColor(16, 20, 28, int(0.78 * 255))

	p = QPainter(px)
	p.setRenderHint(QPainter.Antialiasing, True)

	# outer ring
	p.setPen(Qt.NoPen)
	p.setBrush(QColor(ring.red(), ring.green(), ring.blue(), int(0.90 * 255)))
	p.drawEllipse(0, 0, size, size)

	# inner circle (clip area)
	inset = 4
	inner_rect = px.rect().adjusted(inset, inset, -inset, -inset)

	# base inner
	p.setBrush(inner)
	p.drawEllipse(inner_rect)

	drawn_image = False
	try:
		if image_path:
			pm = QPixmap(str(image_path))
			if not pm.isNull():
				target = inner_rect.size()
				scaled = pm.scaled(target, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
				sx = max(0, (scaled.width() - target.width()) // 2)
				sy = max(0, (scaled.height() - target.height()) // 2)
				cropped = scaled.copy(sx, sy, target.width(), target.height())

				from PyQt5.QtGui import QPainterPath
				from PyQt5.QtCore import QRectF

				path = QPainterPath()
				path.addEllipse(QRectF(inner_rect))
				p.save()
				p.setClipPath(path)
				p.drawPixmap(inner_rect.topLeft(), cropped)
				p.restore()

				drawn_image = True
	except Exception:
		drawn_image = False

	# subtle highlight ring
	p.setPen(Qt.NoPen)
	p.setBrush(QColor(255, 255, 255, 10))
	p.drawEllipse(inner_rect.adjusted(1, 1, -1, -1))

	# fallback initials
	if not drawn_image:
		text = QColor(235, 241, 255, int(0.92 * 255))
		p.setPen(text)
		f = QFont("Inter")
		f.setBold(True)
		f.setPointSize(max(9, int(size * 0.24)))
		p.setFont(f)
		p.drawText(px.rect(), Qt.AlignCenter, _initials(lab_name))

	p.end()

	icon = QIcon()
	icon.addPixmap(px, QIcon.Normal, QIcon.Off)
	icon.addPixmap(px, QIcon.Active, QIcon.Off)
	icon.addPixmap(px, QIcon.Selected, QIcon.Off)
	icon.addPixmap(px, QIcon.Disabled, QIcon.Off)

	_cache[key] = icon
	return icon

