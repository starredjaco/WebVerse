from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, QPoint, QEvent, QPropertyAnimation, QEasingCurve
from PyQt5.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout, QWidget, QGraphicsDropShadowEffect


class Toast(QFrame):
	def __init__(self, parent: QWidget):
		super().__init__(parent)
		self.setObjectName("Toast")
		self.setAttribute(Qt.WA_StyledBackground, False)
		self.setWindowFlags(Qt.SubWindow)

		self.setMinimumWidth(520)
		self.setMaximumWidth(820)
		
		# Toast itself is a transparent container; the painted card is inside.
		self.setAttribute(Qt.WA_TranslucentBackground, True)

		root_outer = QVBoxLayout(self)
		root_outer.setContentsMargins(0, 0, 0, 0)
		root_outer.setSpacing(0)

		self.card = QFrame(self)
		self.card.setObjectName("ToastCard")
		self.card.setAttribute(Qt.WA_StyledBackground, True)
		self.card.setAutoFillBackground(True)
		root_outer.addWidget(self.card)

		shadow = QGraphicsDropShadowEffect(self.card)
		shadow.setBlurRadius(34)
		shadow.setOffset(0, 12)
		self.card.setGraphicsEffect(shadow)
 

		self._timer = QTimer(self)
		self._timer.setSingleShot(True)
		self._timer.timeout.connect(self._fade_out)

		self._anim_in = QPropertyAnimation(self, b"pos", self)
		self._anim_in.setDuration(240)
		self._anim_in.setEasingCurve(QEasingCurve.OutCubic)

		self._anim_out = QPropertyAnimation(self, b"windowOpacity", self)
		self._anim_out.setDuration(180)
		self._anim_out.setEasingCurve(QEasingCurve.InCubic)

		root = QHBoxLayout(self.card)
		root.setContentsMargins(18, 16, 18, 16)
		root.setSpacing(14)

		self._dot = QLabel("●")
		self._dot.setObjectName("ToastDot")
		self._dot.setFixedWidth(20)
		self._dot.setAlignment(Qt.AlignTop)
		root.addWidget(self._dot)

		col = QVBoxLayout()
		col.setSpacing(2)
		root.addLayout(col, 1)

		self.title = QLabel("Success")
		self.title.setObjectName("ToastTitle")
		col.addWidget(self.title)

		self.body = QLabel("")
		self.body.setObjectName("ToastBody")
		self.body.setWordWrap(True)
		col.addWidget(self.body)

		self.hide()

	def show_toast(self, title: str, body: str, variant: str = "success", ms: int = 1700):
		self._timer.stop()
		self._pending_ms = ms

		# Apply variant to the painted card (and keep it on container too)
		self.setProperty("variant", variant)
		self.card.setProperty("variant", variant)
		self.style().unpolish(self)
		self.style().polish(self)
		self.card.style().unpolish(self.card)
		self.card.style().polish(self.card)
		self.card.update()

		self.title.setText(title)
		self.body.setText(body)
		self.adjustSize()

		# Delay one tick so parent/overlay geometry is finalized (fixes first-toast clipping)
		QTimer.singleShot(0, self._deferred_show)

	def _deferred_show(self):
		self.adjustSize()
		target = self._target_pos()
		start = QPoint(target.x(), max(0, target.y() - 14))
		self.move(start)
		self.setWindowOpacity(0.0)
		self.show()
		self.raise_()

		# Fade in quickly
		try:
			self._anim_out.stop()
			self._anim_out.setTargetObject(self)
			self._anim_out.setPropertyName(b"windowOpacity")
			self._anim_out.setStartValue(0.0)
			self._anim_out.setEndValue(1.0)
			self._anim_out.start()
		except Exception:
			self.setWindowOpacity(1.0)

		# Slide to target
		try:
			self._anim_in.stop()
			self._anim_in.setStartValue(start)
			self._anim_in.setEndValue(target)
			self._anim_in.start()
		except Exception:
			self.move(target)

		self._timer.start(self._pending_ms)

	def _fade_out(self):
		try:
			self._anim_out.stop()
			self._anim_out.setStartValue(self.windowOpacity())
			self._anim_out.setEndValue(0.0)
			self._anim_out.finished.connect(self.hide)
			self._anim_out.start()
		except Exception:
			self.hide()

	def _target_pos(self) -> QPoint:
		p = self.parentWidget()
		if not p:
			return QPoint(0, 0)
		margin_top = 22
		x = max(16, (p.width() - self.width()) // 2)
		y = max(16, margin_top)
		return QPoint(x, y)

	def _position(self):
		# Kept for resize handling.
		self.move(self._target_pos())

class ToastHost(QWidget):
	def __init__(self, parent: QWidget):
		super().__init__(parent)
		self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
		self.setAttribute(Qt.WA_NoSystemBackground, True)
		self.toast = Toast(self)
		self._parent = parent
		self.resize(parent.size())
		# Keep overlay sized with the parent
		parent.installEventFilter(self)
		self.show()

	def resizeEvent(self, e):
		super().resizeEvent(e)
		if self.toast.isVisible():
			self.toast._position()

	def eventFilter(self, obj, event):
		if obj is self._parent and event.type() == QEvent.Resize:
			# Overlay follows parent size so Toast._position() is correct
			self.resize(self._parent.size())
			# If a toast is up while resizing, reposition on next tick (avoids transient geometry)
			if self.toast.isVisible():
				QTimer.singleShot(0, self.toast._position)
		return super().eventFilter(obj, event)

	def show_toast(self, title: str, body: str, variant: str = "success", ms: int = 1700):
		self.toast.show_toast(title, body, variant=variant, ms=ms)

	def success(self, msg: str):
		self.show_toast("Success", msg, variant="success")

	def error(self, title: str, msg: str = "", ms: int = 2000):
		# allow either error("msg") or error("Title","Body")
		if msg == "":
			self.show_toast("Error", title, variant="error", ms=ms)
		else:
			self.show_toast(title, msg, variant="error", ms=ms)

	def warn(self, title: str, msg: str = "", ms: int = 2000):
		if msg == "":
			self.show_toast("Warning", title, variant="warn", ms=ms)
		else:
			self.show_toast(title, msg, variant="warn", ms=ms)

	def info(self, title: str, msg: str = "", ms: int = 1800):
		if msg == "":
			self.show_toast("Info", title, variant="info", ms=ms)
		else:
			self.show_toast(title, msg, variant="info", ms=ms)
