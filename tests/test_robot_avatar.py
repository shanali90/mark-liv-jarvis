import math
import time
from pathlib import Path

import pytest

from core.avatar_robot import (
    EYE_COLOURS,
    JAW_MAX_DEGREES,
    ROBOT_LITE_ASSET,
    RobotAvatar,
    clamp_jaw_angle,
    map_named_parts,
)


def test_robot_part_mapping_covers_every_named_mesh():
    names = [
        "skull_skull__top_0", "polySurface1_face1_0", "lowerjaw_skull_jaw_0",
        "teath_teath1_0", "pSphere3_eye_0", "polySurface10_neck_0",
        "pCube12_spin_0", "pCylinder21_wire_0", "pCube1_accessories_0",
    ]
    groups = map_named_parts(names)
    assert sum(map(len, groups.values())) == len(names)
    assert groups["jaw"] == ["lowerjaw_skull_jaw_0"]
    assert groups["eyes"] == ["pSphere3_eye_0"]


def test_robot_jaw_is_clamped_to_fourteen_degrees():
    assert clamp_jaw_angle(90) == JAW_MAX_DEGREES
    assert clamp_jaw_angle(-1) == 0
    assert math.isfinite(math.radians(clamp_jaw_angle(14)))


def test_robot_state_eye_colour_table():
    assert EYE_COLOURS["LISTENING"] == "#5ee0ff"
    assert EYE_COLOURS["THINKING"] == "#ffb347"
    assert EYE_COLOURS["ERROR"] == "#ff5c7a"


def test_missing_robot_asset_triggers_classic_fallback_path(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        RobotAvatar(tmp_path / "missing.glb")


def test_robot_loads_in_under_two_seconds():
    started = time.perf_counter()
    avatar = RobotAvatar()
    assert time.perf_counter() - started < 2.0
    assert avatar.asset_path == ROBOT_LITE_ASSET


def test_robot_frame_is_under_33_ms():
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert app is not None
    avatar = RobotAvatar()
    image = QImage(980, 620, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    avatar.paint(painter, 490, 260, 210, QColor("#5ee0ff"), QColor("#5ee0ff"), QColor("#050506"))
    painter.end()
    assert avatar._last_frame_seconds < 0.033


def test_robot_fallback_triggers_after_slow_frames():
    avatar = RobotAvatar()
    for _ in range(avatar.SLOW_FRAME_LIMIT):
        avatar.note_frame_time(0.034)
    assert avatar.fallback_requested
