from __future__ import annotations

from importlib import resources as ir
from pathlib import Path
from typing import Optional


def _pkg_file(*parts: str) -> Path:
	"""
	Return a real filesystem Path to a packaged resource under webverse/gui/.
	Works in normal installs (pip/pipx) and is safe for future zip-style loaders.
	"""
	root = ir.files("webverse.gui")
	node = root.joinpath(*parts)
	try:
		with ir.as_file(node) as fp:
			return Path(fp)
	except Exception:
		# Dev fallback: relative to this file
		return Path(__file__).resolve().parent.joinpath(*parts)


def load_icon(filename: str) -> "QIcon":
	"""
	Load a non-SVG icon from webverse/gui/icons/ (e.g. .ico/.png).
	"""
	from PyQt5.QtGui import QIcon

	p = _pkg_file("icons", filename)
	return QIcon(str(p))


def load_svg_icon(filename: str, size: int = 16) -> "QIcon":
	"""
	Load an SVG icon from webverse/gui/icons/ and return a QIcon rendered to a pixmap,
	so it works reliably regardless of Qt SVG plugin availability.
	"""
	from PyQt5.QtCore import Qt
	from PyQt5.QtGui import QIcon, QPixmap, QPainter

	p = _pkg_file("icons", filename)

	# Render SVG -> pixmap so we don't depend on lazy file loading or plugins.
	try:
		from PyQt5.QtSvg import QSvgRenderer

		px = QPixmap(int(size), int(size))
		px.fill(Qt.transparent)

		r = QSvgRenderer(str(p))
		qp = QPainter(px)
		r.render(qp)
		qp.end()

		return QIcon(px)
	except Exception:
		# Fallback: let Qt try to load the SVG directly (works if SVG plugin is available).
		return QIcon(str(p))
