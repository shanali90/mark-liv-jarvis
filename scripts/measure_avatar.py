"""Measure robot-avatar load and paint cost on this machine.

Run from the repository root with the project virtual environment.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtWidgets import QApplication
    from core.avatar_robot import RobotAvatar

    app = QApplication.instance() or QApplication([])
    started = time.perf_counter()
    avatar = RobotAvatar()
    load_s = time.perf_counter() - started
    image = QImage(980, 620, QImage.Format.Format_ARGB32_Premultiplied)
    process = psutil.Process()
    process.cpu_percent(None)
    frames = 60
    elapsed_start = time.perf_counter()
    for _ in range(frames):
        avatar.step(1 / 60, 0.35, speaking=True, state="SPEAKING")
        painter = QPainter(image)
        avatar.paint(painter, 490, 260, 210, QColor("#5ee0ff"), QColor("#5ee0ff"), QColor("#050506"))
        painter.end()
    elapsed = time.perf_counter() - elapsed_start
    active_cpu = process.cpu_percent(None)
    process.cpu_percent(None)
    time.sleep(1.0)
    idle_cpu = process.cpu_percent(None)
    frame_s = elapsed / frames
    print(f"asset={Path(avatar.asset_path).name}")
    print(f"triangles={sum(len(indices) for _, indices, _ in avatar._meshes)}")
    print(f"load_seconds={load_s:.4f}")
    print(f"frame_seconds={frame_s:.4f}")
    print(f"fps={1.0 / frame_s:.2f}")
    print(f"active_cpu_percent={active_cpu:.2f}")
    print(f"idle_cpu_percent={idle_cpu:.2f}")
    app.processEvents()


if __name__ == "__main__":
    main()
