"""Settings overlay for JARVIS window.

Houses display preferences (24-hour clock, reduce animations) and
the About credit section.
"""

from __future__ import annotations

import json
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class SettingsOverlay(QWidget):
    """Floating Settings & About overlay."""

    settings_changed = pyqtSignal(dict)
    closed = pyqtSignal()
    _OW = 420

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        from ui import APP_VERSION, C, SETTINGS_FILE, _read_full_config

        self._settings_file = Path(SETTINGS_FILE)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(self._OW)

        self.setStyleSheet(f"""
            SettingsOverlay {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER_B};
                border-radius: 10px;
            }}
            QCheckBox {{
                color: {C.TEXT};
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {C.BORDER_B};
                border-radius: 4px;
                background: {C.DARK};
            }}
            QCheckBox::indicator:checked {{
                background: {C.PRI};
                border-color: {C.PRI};
            }}
        """)

        cfg = _read_full_config()
        self._clock_24h_val = bool(cfg.get("clock_24h", False))
        self._reduce_anim_val = bool(cfg.get("reduce_animations", False))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        # Header with title and close button
        hdr_row = QHBoxLayout()
        hdr_lbl = QLabel("⚙  SETTINGS")
        hdr_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr_row.addWidget(hdr_lbl)
        hdr_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont("Segoe UI", 10))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: none; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; background: {C.PRI_GHO}; }}
        """)
        close_btn.clicked.connect(self._close)
        hdr_row.addWidget(close_btn)
        lay.addLayout(hdr_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        # Preferences section
        pref_lbl = QLabel("DISPLAY & PREFERENCES")
        pref_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        pref_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(pref_lbl)

        # 24-hour clock checkbox
        self._cb_clock = QCheckBox("24-Hour Clock")
        self._cb_clock.setChecked(self._clock_24h_val)
        self._cb_clock.toggled.connect(self._on_clock_toggled)
        lay.addWidget(self._cb_clock)

        clock_desc = QLabel("Display 24-hour time (14:36) instead of 12-hour AM/PM")
        clock_desc.setFont(QFont("Segoe UI", 8))
        clock_desc.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding-left: 24px;")
        lay.addWidget(clock_desc)

        lay.addSpacing(4)

        # Reduce animations checkbox
        self._cb_anim = QCheckBox("Reduce Animations")
        self._cb_anim.setChecked(self._reduce_anim_val)
        self._cb_anim.toggled.connect(self._on_anim_toggled)
        lay.addWidget(self._cb_anim)

        anim_desc = QLabel("Display static visuals to minimize CPU usage")
        anim_desc.setFont(QFont("Segoe UI", 8))
        anim_desc.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding-left: 24px;")
        lay.addWidget(anim_desc)

        lay.addSpacing(6)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep2)

        # About section
        about_lbl = QLabel("ABOUT")
        about_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        about_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(about_lbl)

        ver_lbl = QLabel(f"Personal Assistant — {APP_VERSION}")
        ver_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        ver_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(ver_lbl)

        # Credit line (moved from main window footer)
        credit_lbl = QLabel("Made by Shaan Ali — Personal JARVIS Assistant")
        credit_lbl.setFont(QFont("Segoe UI", 8))
        credit_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        lay.addWidget(credit_lbl)

        lay.addSpacing(8)

        done_btn = QPushButton("DONE")
        done_btn.setFixedHeight(30)
        done_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.BORDER_B}; border-radius: 6px;
            }}
            QPushButton:hover {{
                border-color: {C.PRI}; background: {C.PANEL2};
            }}
        """)
        done_btn.clicked.connect(self._close)
        lay.addWidget(done_btn)

    def _persist(self, **kwargs) -> None:
        try:
            if self._settings_file.exists():
                data = json.loads(self._settings_file.read_text(encoding="utf-8"))
            else:
                data = {}
            data.update(kwargs)
            self._settings_file.write_text(json.dumps(data, indent=4), encoding="utf-8")
        except Exception:
            pass

    def _on_clock_toggled(self, checked: bool) -> None:
        self._clock_24h_val = checked
        self._persist(clock_24h=checked)
        self.settings_changed.emit({"clock_24h": checked, "reduce_animations": self._reduce_anim_val})

    def _on_anim_toggled(self, checked: bool) -> None:
        self._reduce_anim_val = checked
        self._persist(reduce_animations=checked)
        self.settings_changed.emit({"clock_24h": self._clock_24h_val, "reduce_animations": checked})

    def _close(self) -> None:
        self.hide()
        self.closed.emit()

    def hideEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        super().hideEvent(e)

    def closeEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        super().closeEvent(e)
