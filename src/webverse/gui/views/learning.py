from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRectF, QVariantAnimation, QEasingCurve, QTimer, QRect
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QLinearGradient, QFontMetrics, QBrush
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QGridLayout,
    QPushButton, QHBoxLayout, QGraphicsDropShadowEffect, QProgressBar, QSizePolicy
)

from webverse.core.models import Lab, LearningTrack
from webverse.gui.util_avatar import lab_badge_icon, lab_circle_icon
from webverse.core.xp import base_xp_for_difficulty

class AnimatedTrackCardButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_progress = 0.0
        self._banner_label: Optional[QLabel] = None
        self._banner_base_pm: Optional[QPixmap] = None

        self.setObjectName("TrackCard")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(16)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(QColor(0, 0, 0, 0))
        self.setGraphicsEffect(self._shadow)

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)

    def set_banner_label(self, label: QLabel):
        self._banner_label = label
        try:
            pm = label.pixmap()
            if pm is not None and not pm.isNull():
                self._banner_base_pm = pm.copy()
        except Exception:
            self._banner_base_pm = None

    def _animate_to(self, value: float, duration: int = 160):
        value = max(0.0, min(1.0, float(value)))
        self._anim.stop()
        self._anim.setDuration(duration)
        self._anim.setStartValue(float(self._hover_progress))
        self._anim.setEndValue(value)
        self._anim.start()

    def _on_anim_value(self, value):
        try:
            p = float(value)
        except Exception:
            p = 0.0
        self._hover_progress = p

        self._shadow.setBlurRadius(16 + (20 * p))
        self._shadow.setOffset(0, 2 + (4 * p))
        self._shadow.setColor(QColor(245, 197, 66, int(10 + (52 * p))))

        self._apply_banner_zoom(p)
        self.update()

    def _apply_banner_zoom(self, p: float):
        if not self._banner_label or self._banner_base_pm is None:
            return
        try:
            tw = int(self._banner_label.width())
            th = int(self._banner_label.height())
            if tw <= 0 or th <= 0:
                return

            base = self._banner_base_pm
            if base.isNull():
                return

            zoom = 1.0 + (0.018 * p)
            sw = max(tw, int(round(base.width() * zoom)))
            sh = max(th, int(round(base.height() * zoom)))

            scaled = base.scaled(sw, sh, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max(0, (scaled.width() - tw) // 2)
            sy = max(0, (scaled.height() - th) // 2)
            self._banner_label.setPixmap(scaled.copy(sx, sy, tw, th))
        except Exception:
            pass

    def enterEvent(self, event):
        self._animate_to(1.0, 180)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_to(0.0, 140)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._animate_to(0.75, 90)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.underMouse():
            self._animate_to(1.0, 120)
        else:
            self._animate_to(0.0, 120)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        p_val = float(self._hover_progress)
        if p_val <= 0.001:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -2, -2)
        radius = 18

        painter.setBrush(QColor(245, 197, 66, int(8 + (18 * p_val))))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(QPen(QColor(245, 197, 66, int(40 + (90 * p_val))), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        top_rect = rect.adjusted(0, 0, 0, -int(rect.height() * 0.55))
        g = QLinearGradient(top_rect.topLeft(), top_rect.bottomLeft())
        g.setColorAt(0.0, QColor(255, 255, 255, int(22 * p_val)))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(g)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(top_rect, radius, radius)
        painter.end()

class BrowseStyleLabCardButton(QPushButton):
    """
    Custom-painted lab card that matches the Browse Labs tab card visuals
    (same spacing, typography, border, icon placement, meta row).
    """
    def __init__(self, lab: Lab, state, parent=None):
        super().__init__(parent)
        self.lab = lab
        self.state = state

        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFlat(True)

        # Match Browse Labs geometry: grid item 420x210, inner card 400x190
        self.setFixedSize(420, 210)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Cache icon
        try:
            img_path = lab.image_path()
        except Exception:
            img_path = None

        try:
            if img_path:
                self._icon = lab_badge_icon(lab.name, lab.difficulty, img_path, 96)
            else:
                self._icon = lab_circle_icon(lab.name, lab.difficulty, 96)
        except Exception:
            self._icon = None

    def enterEvent(self, ev):
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.update()
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)
        self.update()

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self.update()

    def sizeHint(self):
        return QSize(420, 210)

    def minimumSizeHint(self):
        return QSize(420, 210)

    def _status_text(self) -> str:
        try:
            if bool(getattr(self.state, "is_solved", lambda _x: False)(self.lab.id)):
                return "Solved"
        except Exception:
            pass
        return "Unsolved"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Same inner rect style as _LabCardDelegate in Browse Labs
        r = self.rect().adjusted(10, 10, -10, -10)

        hover = self.underMouse()
        pressed = self.isDown()

        bg = QColor(10, 12, 16, 178)
        bd = QColor(255, 255, 255, 18)
        if hover:
            bg = QColor(14, 18, 26, 200)
            bd = QColor(245, 197, 66, 90)
        if pressed:
            bg = QColor(16, 22, 32, 220)
            bd = QColor(245, 197, 66, 140)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(bd, 1))
        painter.drawRoundedRect(r, 22, 22)

        # icon
        icon_size = 64
        ix = r.left() + 18
        iy = r.top() + 18
        if self._icon:
            try:
                pm = self._icon.pixmap(icon_size, icon_size)
                painter.drawPixmap(ix, iy, pm)
            except Exception:
                pass

        # Typography (match Browse Labs delegate)
        title_font = QFont(self.font())
        sub_font = QFont(self.font())
        meta_font = QFont(self.font())
        try:
            base_px = title_font.pixelSize()
            if base_px <= 0:
                base_px = 15
            title_font.setPixelSize(base_px + 6)
            title_font.setBold(True)
            sub_font.setPixelSize(base_px + 2)
            meta_font.setPixelSize(base_px + 2)
        except Exception:
            title_font.setPointSize(max(14, title_font.pointSize() + 4))
            title_font.setBold(True)
            sub_font.setPointSize(max(12, sub_font.pointSize() + 2))
            meta_font.setPointSize(max(12, meta_font.pointSize() + 2))

        title_x = ix + icon_size + 16
        title_w = r.right() - title_x - 18

        title = str(getattr(self.lab, "name", "—") or "—")
        subtitle = str(getattr(self.lab, "id", "") or "")

        # title
        painter.setPen(QColor(245, 247, 255, 235))
        painter.setFont(title_font)
        fm_title = QFontMetrics(title_font)
        t_rect = QRect(title_x, iy - 2, title_w, 34)
        painter.drawText(
            t_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            fm_title.elidedText(title, Qt.ElideRight, title_w),
        )

        # subtitle (lab slug/id)
        painter.setPen(QColor(235, 241, 255, 150))
        painter.setFont(sub_font)
        fm_sub = QFontMetrics(sub_font)
        s_rect = QRect(title_x, iy + 30, title_w, 24)
        painter.drawText(
            s_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            fm_sub.elidedText(subtitle, Qt.ElideRight, title_w),
        )

        # bottom meta row
        diff = str(getattr(self.lab, "difficulty", "") or "Unknown")
        status = self._status_text()
        try:
            xp = int(base_xp_for_difficulty(diff))
        except Exception:
            xp = 0

        meta = f"{diff.title()}   •   {status}   •   {xp} XP"
        painter.setFont(meta_font)
        painter.setPen(QColor(235, 241, 255, 165))
        meta_y = r.bottom() - 34
        painter.drawText(
            QRect(r.left() + 18, meta_y, r.width() - 36, 24),
            Qt.AlignLeft | Qt.AlignVCenter,
            meta,
        )

class HoverLiftButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(self._shadow)

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(140)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hover_anim.setStartValue(0.0)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.valueChanged.connect(self._on_hover_value)

    def _mix(self, a: QColor, b: QColor, t: float) -> QColor:
        return QColor(
            int(a.red() + (b.red() - a.red()) * t),
            int(a.green() + (b.green() - a.green()) * t),
            int(a.blue() + (b.blue() - a.blue()) * t),
            int(a.alpha() + (b.alpha() - a.alpha()) * t),
        )

    def _on_hover_value(self, v):
        try:
            t = float(v)
        except Exception:
            t = 0.0
        self._shadow.setBlurRadius(18 + (18 * t))
        self._shadow.setOffset(0, 6 - (3 * t))
        self._shadow.setColor(self._mix(QColor(0, 0, 0, 120), QColor(245, 197, 66, 95), t))

    def enterEvent(self, ev):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_anim.currentValue() or 0.0)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_anim.currentValue() or 1.0)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(ev)


class LearningView(QWidget):
    lab_selected = pyqtSignal(object)  # Lab

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._selected_track_slug: Optional[str] = None
        self._refreshing = False

        # Rebuilding the full layout on every resize event causes flicker/glitching.
        # Debounce viewport resize -> refresh.
        self._resize_refresh_timer = QTimer(self)
        self._resize_refresh_timer.setSingleShot(True)
        self._resize_refresh_timer.setInterval(40)
        self._resize_refresh_timer.timeout.connect(self.refresh)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)

        self.content = QWidget()
        self.scroll.setWidget(self.content)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 8, 0, 8)
        self.content_layout.setSpacing(16)

        try:
            self.state.learning_labs_changed.connect(self.refresh)
        except Exception:
            pass

        try:
            self.scroll.viewport().installEventFilter(self)
        except Exception:
            pass

        self.refresh()

    def eventFilter(self, obj, ev):
        try:
            from PyQt5.QtCore import QEvent
            if obj is self.scroll.viewport() and ev.type() == QEvent.Resize:
                # Debounced refresh prevents resize/rebuild thrash + visual glitching
                self._resize_refresh_timer.start()
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    def _clear(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            lay = item.layout()
            if lay is not None:
                self._delete_layout(lay)

    def _delete_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            w = child.widget()
            if w is not None:
                w.deleteLater()
            l = child.layout()
            if l is not None:
                self._delete_layout(l)
        try:
            layout.deleteLater()
        except Exception:
            pass

    def _tracks(self) -> List[LearningTrack]:
        try:
            tracks = list(getattr(self.state, 'learning_tracks', lambda: [])())
            if tracks:
                return tracks
        except Exception:
            pass
        return []

    def _find_selected_track(self, tracks: List[LearningTrack]) -> Optional[LearningTrack]:
        if not self._selected_track_slug:
            return None
        for t in tracks:
            if str(getattr(t, 'slug', '')) == str(self._selected_track_slug):
                return t
        return None

    def refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            tracks = self._tracks()
            selected = self._find_selected_track(tracks)
            if self._selected_track_slug and selected is None:
                self._selected_track_slug = None
            self._clear()

            if not tracks:
                self._render_empty()
                return

            if self._selected_track_slug:
                self._render_track_detail(self._find_selected_track(tracks))
            else:
                self._render_tracks_grid(tracks)

            self.content_layout.addStretch(1)
        finally:
            self._refreshing = False

    def _render_empty(self):
        card = QFrame()
        card.setObjectName('Card')
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        t = QLabel('No learning tracks found')
        t.setObjectName('SectionTitle')
        lay.addWidget(t)

        msg = QLabel(
            'Learning tracks are discovered from tracks/{TRACK_SLUG}/track.yml and tracks/{TRACK_SLUG}/labs/{LAB_SLUG}/lab.yml.\n\n'
            'Remote cloud installs for learning tracks are disabled for now (local tracks only).'
        )
        msg.setObjectName('SubtleText')
        msg.setWordWrap(True)
        lay.addWidget(msg)

        self.content_layout.addWidget(card)

    def _render_tracks_grid(self, tracks: List[LearningTrack]):
        intro = QFrame()
        intro.setObjectName('Card')
        intro_l = QVBoxLayout(intro)
        intro_l.setContentsMargins(14, 14, 14, 14)
        intro_l.setSpacing(6)

        h = QLabel('Track Library')
        h.setObjectName('SectionTitle')
        intro_l.addWidget(h, 0, Qt.AlignLeft)
        s = QLabel(
            'Pick a guided path to learn step by step. Each track bundles labs in a recommended order so you can build one skillset from fundamentals to harder scenarios.'
        )
        s.setObjectName('SubtleText')
        s.setWordWrap(True)
        intro_l.addWidget(s)
        self.content_layout.addWidget(intro)

        # Better copy for the track shelf (more like a "Browse Labs" section)
        s.setText('Structured mini-lab paths for one topic at a time. Start with fundamentals, build momentum, and track your progress across each track.')

        grid_wrap = QWidget()
        wrap_l = QVBoxLayout(grid_wrap)
        wrap_l.setContentsMargins(0, 0, 0, 0)
        wrap_l.setSpacing(0)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(14)
        wrap_l.addLayout(grid)

        cols = self._grid_cols(kind='tracks')
        for i, track in enumerate(tracks):
            btn = self._make_track_card(track)
            r, c = divmod(i, cols)
            grid.addWidget(btn, r, c, Qt.AlignTop | Qt.AlignLeft)
        for c in range(cols):
            grid.setColumnStretch(c, 1)

        self.content_layout.addWidget(grid_wrap)

    def _render_track_detail(self, track: Optional[LearningTrack]):
        if track is None:
            self._selected_track_slug = None
            self._render_empty()
            return

        hero = QFrame()
        hero.setObjectName('Card')
        hero_l = QVBoxLayout(hero)
        hero_l.setContentsMargins(14, 14, 14, 14)
        hero_l.setSpacing(12)

        solved, total, pct = self._track_progress(track)
        top = QHBoxLayout()
        top.setSpacing(10)

        back = QPushButton('← Back to Tracks')
        back.setObjectName('GhostButton')
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(self._go_back_to_tracks)
        top.addWidget(back, 0)
        top.addStretch(1)

        count = QLabel(f"{total} labs")
        count.setObjectName('SubtleText')
        top.addWidget(count, 0, Qt.AlignRight)
        hero_l.addLayout(top)

        # Intentionally no giant hero/banner image on track detail page
        title_lbl = QLabel(track.name)
        title_lbl.setObjectName('TrackDetailTitle')
        hero_l.addWidget(title_lbl)

        short = (track.short_description or track.description or '').strip()
        if short:
            short_lbl = QLabel(short)
            short_lbl.setWordWrap(True)
            short_lbl.setObjectName('SubtleText')
            hero_l.addWidget(short_lbl)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(10)
        prog_bar = self._make_track_progress_bar(solved, total)
        prog_row.addWidget(prog_bar, 1)
        prog_lbl = QLabel(f"{pct}% complete")
        prog_lbl.setObjectName('TrackProgressText')
        prog_row.addWidget(prog_lbl, 0, Qt.AlignRight)
        hero_l.addLayout(prog_row)

        # Removed extra meta/progress/focus text to keep the page clean
        self.content_layout.addWidget(hero)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        cols = self._grid_cols(kind='labs')
        labs = list(getattr(track, 'labs', ()) or [])
        for i, lab in enumerate(labs):
            tile = self._make_learning_lab_card(lab, compact=False)
            r, c = divmod(i, cols)
            grid.addWidget(tile, r, c, Qt.AlignTop | Qt.AlignLeft)
        for c in range(cols):
            grid.setColumnStretch(c, 1)

        self.content_layout.addLayout(grid)

    def _grid_cols(self, *, kind: str) -> int:
        try:
            w = int(self.scroll.viewport().width())
        except Exception:
            w = 1000
        if kind == 'tracks':
            # Bigger image-forward tiles: fewer columns so cards can stay large
            if w >= 1900:
                return 3
            if w >= 1260:
                return 2
            return 1
        if w >= 1550:
            return 3
        if w >= 980:
            return 2
        return 1

    def _go_back_to_tracks(self):
        self._selected_track_slug = None
        self.refresh()

    def open_tracks_home(self):
        """
        Public nav helper: show the main tracks grid.
        """
        self._selected_track_slug = None
        self.refresh()

    def open_track_by_slug(self, track_slug: str):
        """
        Public nav helper: open a specific track by slug.
        Falls back to tracks grid if not found.
        """
        slug = str(track_slug or "").strip()
        if not slug:
            self._selected_track_slug = None
            self.refresh()
            return

        for t in self._tracks():
            if str(getattr(t, "slug", "") or "") == slug:
                self._selected_track_slug = slug
                self.refresh()
                return
        self._selected_track_slug = None
        self.refresh()

    def _open_track(self, track: LearningTrack):
        self._selected_track_slug = str(getattr(track, 'slug', '') or '')
        self.refresh()

    def _track_meta_line(self, track: LearningTrack) -> str:
        parts = []
        diff = (getattr(track, 'difficulty_focus', '') or '').strip()
        if diff:
            parts.append(f"Focus: {diff}")
        tags = list(getattr(track, 'tags', ()) or [])
        if tags:
            parts.append('Tags: ' + ', '.join(tags[:5]))
        try:
            solved = 0
            for lab in getattr(track, 'labs', ()):
                if bool(getattr(self.state, 'is_solved', lambda _x: False)(lab.id)):
                    solved += 1
            if track.labs:
                parts.append(f"Progress: {solved}/{len(track.labs)} solved")
        except Exception:
            pass
        return ' • '.join(parts) if parts else 'Mini challenge track'

    def _track_progress(self, track: LearningTrack):
        total = 0
        solved = 0
        try:
            labs = list(getattr(track, 'labs', ()) or [])
            total = len(labs)
            for lab in labs:
                try:
                    if bool(getattr(self.state, 'is_solved', lambda _x: False)(lab.id)):
                        solved += 1
                except Exception:
                    pass
        except Exception:
            total = 0
            solved = 0
        pct = int(round((solved / total) * 100)) if total > 0 else 0
        return solved, total, pct

    def _make_track_progress_bar(self, solved: int, total: int) -> QProgressBar:
        bar = QProgressBar()
        bar.setObjectName('TrackProgressBar')
        bar.setTextVisible(True)
        bar.setMinimum(0)
        bar.setMaximum(max(1, int(total)))
        bar.setValue(max(0, min(int(solved), max(1, int(total)))))
        if total > 0:
            bar.setFormat("%p%  •  %v/%m solved")
        else:
            bar.setFormat("No labs yet")
        bar.setFixedHeight(18)
        return bar

    def _make_track_card(self, track: LearningTrack) -> QPushButton:
        btn = AnimatedTrackCardButton()
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumSize(620, 390)
        btn.setMaximumWidth(620)
        btn.clicked.connect(lambda _=False, t=track: self._open_track(t))

        lay = QVBoxLayout(btn)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        solved = 0
        try:
            for lab in getattr(track, 'labs', ()):
                if bool(getattr(self.state, 'is_solved', lambda _x: False)(lab.id)):
                    solved += 1
        except Exception:
            solved = 0

        banner_sub = f"{len(getattr(track, 'labs', ()))} labs • {solved} solved"

        # Fit inside card width (620 max width - 8px left margin - 8px right margin)
        cover_w = 604
        cover_h = 340  # 16:9 ratio (matches your 4000x2250 art)

        cover = self._make_banner(
            getattr(track, 'cover_path', lambda: None)(),
            width=cover_w,
            height=cover_h,
            title=track.name,
            subtitle=banner_sub,
            contain=True,
            overlay_text=False
        )
        lay.addWidget(cover)
        btn.set_banner_label(cover)

        return btn

    def _make_learning_lab_card(self, lab: Lab, compact: bool = False) -> QPushButton:
        # Ignore compact for now — user wants exact Browse Labs look
        btn = BrowseStyleLabCardButton(lab, self.state)
        btn.clicked.connect(lambda _=False, x=lab: self.lab_selected.emit(x))
        return btn

    def _make_lab_cover(self, lab: Lab, width: int, height: int) -> QLabel:
        try:
            p = lab.image_path()
        except Exception:
            p = None
        title = lab.name
        subtitle = (lab.track or 'Learning Lab')
        return self._make_banner(p, width=width, height=height, title=title, subtitle=subtitle)

    def _make_banner(self, image_path, *, width: int, height: int, title: str, subtitle: str, contain: bool = False, overlay_text: bool = True) -> QLabel:
        w = max(220, int(width))
        h = max(100, int(height))
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)

        rect = pm.rect()
        radius = 18

        rectf = QRectF(rect.adjusted(0, 0, -1, -1))

        clip = QPainterPath()
        clip.addRoundedRect(rectf, radius, radius)
        p.setClipPath(clip)

        # Paint a background first so "contain" mode can letterbox without looking broken
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0.0, QColor(20, 25, 38, 240))
        g.setColorAt(0.55, QColor(12, 16, 24, 248))
        g.setColorAt(1.0, QColor(7, 10, 16, 250))
        p.fillRect(rect, g)

        drew_image = False
        try:
            if image_path:
                src = QPixmap(str(image_path))
                if not src.isNull():
                    mode = Qt.KeepAspectRatio if contain else Qt.KeepAspectRatioByExpanding
                    scaled = src.scaled(rect.size(), mode, Qt.SmoothTransformation)
                    if contain:
                        dx = max(0, (rect.width() - scaled.width()) // 2)
                        dy = max(0, (rect.height() - scaled.height()) // 2)
                        p.drawPixmap(dx, dy, scaled)
                    else:
                        sx = max(0, (scaled.width() - rect.width()) // 2)
                        sy = max(0, (scaled.height() - rect.height()) // 2)
                        p.drawPixmap(0, 0, scaled.copy(sx, sy, rect.width(), rect.height()))
                    drew_image = True
        except Exception:
            drew_image = False

        if overlay_text:
            # dark overlay for text readability
            og = QLinearGradient(0, 0, 0, h)
            og.setColorAt(0.0, QColor(0, 0, 0, 15))
            og.setColorAt(0.55, QColor(0, 0, 0, 95))
            og.setColorAt(1.0, QColor(0, 0, 0, 165))
            p.fillRect(rect, og)

        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), radius, radius)

        if overlay_text:
            pad = 14
            p.setPen(QColor(245, 247, 255, 235))
            title_font = QFont('Inter')
            title_font.setBold(True)
            title_font.setPixelSize(18 if h >= 170 else 15)
            p.setFont(title_font)
            p.drawText(pad, h - 32, max(60, w - (pad * 2)), 22, Qt.AlignLeft | Qt.AlignVCenter, (title or '').strip())

            sub = (subtitle or '').strip()
            if sub:
                p.setPen(QColor(235, 241, 255, 170))
                sub_font = QFont('Inter')
                sub_font.setPixelSize(12)
                p.setFont(sub_font)
                p.drawText(pad, h - 14, max(60, w - (pad * 2)), 18, Qt.AlignLeft | Qt.AlignVCenter, sub)

        p.end()

        lbl = QLabel()
        lbl.setPixmap(pm)
        lbl.setFixedSize(w, h)
        lbl.setScaledContents(False)
        return lbl