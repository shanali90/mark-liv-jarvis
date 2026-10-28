"""Render real offscreen robot-avatar previews for documentation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from core.avatar_robot import RobotAvatar


def render(avatar: RobotAvatar, path: Path) -> None:
    image = QImage(980, 620, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#050506"))
    painter = QPainter(image)
    avatar.paint(painter, 490, 260, 210, QColor("#5ee0ff"), QColor("#5ee0ff"), QColor("#050506"))
    painter.end()
    image.save(str(path), "PNG")


def main() -> None:
    QApplication.instance() or QApplication([])
    output = ROOT / "docs" / "images"
    output.mkdir(parents=True, exist_ok=True)
    avatar = RobotAvatar()
    render(avatar, output / "robot_idle.png")
    avatar.step(1 / 60, 0.9, speaking=True, state="SPEAKING")
    avatar.step(1 / 60, 0.9, speaking=True, state="SPEAKING", v_open=1.0, v_level=0.9)
    render(avatar, output / "robot_speaking.png")
    avatar.set_emotion_from_text("error")
    avatar.step(1 / 60, 0.0, state="ERROR")
    render(avatar, output / "robot_error.png")
    for path in sorted(output.glob("robot_*.png")):
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
