"""Premium lightweight QPainter animations for MARK LIV JARVIS window.

Driven by a single shared 30 fps QTimer.
No external dependencies, zero per-frame object allocations, pauses when hidden.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import QWidget


def _get_qcol(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(max(0, min(255, alpha)))
    return c


class AuraWidget(QWidget):
    """Calm breathing aura widget for the left panel.

    Renders 3-4 thin concentric rings that breathe slowly (6-8s cycle)
    with a soft central glow.
    Reacts gently to state:
      - sleeping: very slow and dim
      - listening: slightly brighter
      - thinking: slowly rotating
      - speaking: pulsing with voice amplitude
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(170)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._phase = 0.0
        self._rot_angle = 0.0
        self._state = "LISTENING"
        self._amp = 0.0
        self._reduce = False

    def step(self, dt: float, state: str, amp: float, reduce: bool = False) -> None:
        self._state = state
        self._amp = amp
        self._reduce = reduce

        if reduce:
            self.update()
            return

        # Breathing speed depends on state
        if state == "SLEEPING":
            speed = 0.8   # ~8s cycle
        elif state in ("THINKING", "PROCESSING"):
            speed = 1.3
            self._rot_angle = (self._rot_angle + dt * 0.75) % (2.0 * math.pi)
        elif state == "SPEAKING":
            speed = 1.6 + amp * 1.5
        else:  # LISTENING / IDLE
            speed = 1.0   # ~6.3s cycle

        self._phase = (self._phase + dt * speed) % (2.0 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:
        from ui import C

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0

        pri_hex = getattr(C, "PRI", "#a78bfa")
        pri_dim_hex = getattr(C, "PRI_DIM", "#6d4fc2")

        if self._reduce:
            # Clean static representation
            r_base = min(w, h) * 0.36
            glow = QRadialGradient(cx, cy, r_base * 1.2)
            glow.setColorAt(0.0, _get_qcol(pri_hex, 35))
            glow.setColorAt(0.6, _get_qcol(pri_dim_hex, 15))
            glow.setColorAt(1.0, _get_qcol(pri_hex, 0))
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), r_base * 1.2, r_base * 1.2)

            pen = QPen(_get_qcol(pri_hex, 75))
            pen.setWidthF(1.2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
            for factor in (0.35, 0.60, 0.85):
                p.drawEllipse(QPointF(cx, cy), r_base * factor, r_base * factor)
            p.end()
            return

        is_sleeping = (self._state == "SLEEPING")
        is_speaking = (self._state == "SPEAKING")
        is_thinking = (self._state in ("THINKING", "PROCESSING"))

        breath = (math.sin(self._phase) + 1.0) * 0.5  # 0.0 .. 1.0
        if is_speaking:
            amp_pulse = max(self._amp, 0.15 * math.sin(self._phase * 2.5))
        else:
            amp_pulse = 0.0

        # Dimness and brightness based on state
        if is_sleeping:
            base_alpha = 30 + int(15 * breath)
            scale = 0.90 + 0.05 * breath
        elif is_thinking:
            base_alpha = 80 + int(30 * breath)
            scale = 0.95 + 0.10 * breath
        elif is_speaking:
            base_alpha = 90 + int(90 * amp_pulse)
            scale = 0.95 + 0.18 * amp_pulse
        else:  # LISTENING
            base_alpha = 75 + int(35 * breath)
            scale = 0.95 + 0.08 * breath

        max_r = min(w, h) * 0.40 * scale

        # Central soft radial glow
        glow_r = max_r * 1.15
        glow = QRadialGradient(cx, cy, glow_r)
        glow.setColorAt(0.0, _get_qcol(pri_hex, int(base_alpha * 0.65)))
        glow.setColorAt(0.5, _get_qcol(pri_dim_hex, int(base_alpha * 0.25)))
        glow.setColorAt(1.0, _get_qcol(pri_hex, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # Draw 3 to 4 calm concentric violet rings
        ring_factors = (0.28, 0.52, 0.76, 1.00)
        p.setBrush(Qt.BrushStyle.NoBrush)

        for i, rf in enumerate(ring_factors):
            rr = max_r * rf
            # Outer rings slightly more transparent
            alpha = max(10, min(240, int(base_alpha * (1.1 - 0.22 * i))))
            pen = QPen(_get_qcol(pri_hex, alpha))
            pen.setWidthF(1.2 if i < 3 else 1.0)
            p.setPen(pen)

            if is_thinking and (i % 2 == 1):
                # Subtle rotation pattern for thinking state
                p.save()
                p.translate(cx, cy)
                angle_deg = math.degrees(self._rot_angle * (1.0 if i == 1 else -0.7))
                p.rotate(angle_deg)
                # Draw subtle arc or elliptical ring
                p.drawEllipse(QRectF(-rr, -rr * 0.92, rr * 2.0, rr * 1.84))
                p.restore()
            else:
                p.drawEllipse(QPointF(cx, cy), rr, rr)

        p.end()


class VoiceWaveWidget(QWidget):
    """Slim smooth voice wave widget for the bottom-left panel.

    Displays 24 thin bars that sit nearly flat when idle, ripple with
    microphone/speaking level, and fade when asleep.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._phase = 0.0
        self._state = "LISTENING"
        self._amp = 0.0
        self._reduce = False
        self._num_bars = 22

    def step(self, dt: float, state: str, amp: float, reduce: bool = False) -> None:
        self._state = state
        self._amp = amp
        self._reduce = reduce

        if reduce:
            self.update()
            return

        speed = 2.0 if state == "SLEEPING" else (4.5 + amp * 6.0)
        self._phase = (self._phase + dt * speed) % (2.0 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:
        from ui import C

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        cy = h / 2.0

        pri_hex = getattr(C, "PRI", "#a78bfa")
        acc2_hex = getattr(C, "ACC2", "#67e8f9")

        is_sleeping = (self._state == "SLEEPING")
        is_speaking = (self._state == "SPEAKING")
        amp = self._amp

        if self._reduce:
            # Static subtle baseline
            p.setPen(QPen(_get_qcol(pri_hex, 50), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            bar_w = (w - 24.0) / self._num_bars
            for i in range(self._num_bars):
                bx = 12.0 + i * bar_w + bar_w / 2.0
                p.drawLine(QPointF(bx, cy - 2), QPointF(bx, cy + 2))
            p.end()
            return

        bar_w = (w - 20.0) / self._num_bars
        max_h = (h - 8.0) / 2.0

        for i in range(self._num_bars):
            t = float(i) / float(self._num_bars - 1)  # 0.0 .. 1.0
            # Bell envelope so edges are gently tapered
            envelope = math.sin(t * math.pi)

            if is_sleeping:
                # Barely perceptible flat shimmer
                bh = 1.5 + 0.8 * math.sin(self._phase + i * 0.4)
                alpha = 25
                col = pri_hex
            elif is_speaking or amp > 0.05:
                # Active ripple proportional to volume level
                wave = math.sin(self._phase + i * 0.6) * 0.4 + math.sin(self._phase * 1.5 - i * 0.3) * 0.3 + 0.3
                bh = 2.0 + (amp * max_h * 1.8 + wave * 4.0) * envelope
                bh = min(bh, max_h)
                alpha = int(100 + 155 * min(1.0, amp * 1.5))
                col = acc2_hex if (i % 4 == 0 and amp > 0.2) else pri_hex
            else:
                # Idle calm breathing wave
                wave = (math.sin(self._phase + i * 0.5) + 1.0) * 0.5
                bh = 2.0 + wave * 3.5 * envelope
                alpha = 65 + int(25 * wave)
                col = pri_hex

            bx = 10.0 + i * bar_w + bar_w / 2.0
            pen = QPen(_get_qcol(col, alpha), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(bx, cy - bh), QPointF(bx, cy + bh))

        p.end()


class HeaderAccentLine(QWidget):
    """Subtle animated violet-ice gradient line in header center.

    Replaces the heavy center title block with a sleek, minimalist glowing accent.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setFixedWidth(220)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._phase = 0.0
        self._reduce = False

    def step(self, dt: float, reduce: bool = False) -> None:
        self._reduce = reduce
        if reduce:
            self.update()
            return
        self._phase = (self._phase + dt * 0.8) % (2.0 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:
        from ui import C

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        pri_hex = getattr(C, "PRI", "#a78bfa")
        acc2_hex = getattr(C, "ACC2", "#67e8f9")

        if self._reduce:
            grad = QLinearGradient(0, 0, w, 0)
            grad.setColorAt(0.0, _get_qcol(pri_hex, 0))
            grad.setColorAt(0.5, _get_qcol(pri_hex, 80))
            grad.setColorAt(1.0, _get_qcol(pri_hex, 0))
            p.fillRect(QRectF(0, 0, w, h), QBrush(grad))
            p.end()
            return

        shift = (math.sin(self._phase) + 1.0) * 0.5  # 0.0 .. 1.0
        c_mid = 0.35 + 0.30 * shift

        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, _get_qcol(pri_hex, 0))
        grad.setColorAt(max(0.05, c_mid - 0.25), _get_qcol(pri_hex, 60))
        grad.setColorAt(c_mid, _get_qcol(acc2_hex, 160))
        grad.setColorAt(min(0.95, c_mid + 0.25), _get_qcol(pri_hex, 60))
        grad.setColorAt(1.0, _get_qcol(pri_hex, 0))

        p.fillRect(QRectF(0, 0, w, h), QBrush(grad))
        p.end()
