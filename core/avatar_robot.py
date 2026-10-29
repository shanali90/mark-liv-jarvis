"""Robot-head avatar support.

The renderer deliberately has no third-party GLB dependency.  It reads the
standard GLB container and projects the model with Qt's painter, which keeps
the classic avatar available on machines without WebEngine or PyOpenGL.
"""

from __future__ import annotations

import json
import math
import random
import struct
import time
from pathlib import Path

import numpy as np

ROBOT_ASSET = Path(__file__).resolve().parent.parent / "assets" / "avatar" / "robo_face.glb"
ROBOT_LITE_ASSET = ROBOT_ASSET.with_name("robo_face_lite.glb")
JAW_MAX_DEGREES = 14.0
JAW_MAX_RADIANS = math.radians(JAW_MAX_DEGREES)
EYE_COLOURS = {
    "LISTENING": "#5ee0ff",
    "SPEAKING": "#5ee0ff",
    "THINKING": "#ffb347",
    "PROCESSING": "#ffb347",
    "SLEEPING": "#5ee0ff",
    "ERROR": "#ff5c7a",
    "OFFLINE": "#ff5c7a",
}

_GROUP_RULES = {
    "jaw": ("lowerjaw_",),
    "teeth": ("teath_", "teeth_"),
    "eyes": ("psphere3_eye_",),
    "neck": ("_neck_",),
    "spine": ("_spin_",),
    "wires": ("_wire_",),
    "head": ("skull_", "_face", "_ear_", "_top_", "_back_", "_accessories_"),
}


def _group_for_name(name: str) -> str:
    lowered = name.lower()
    for group, needles in _GROUP_RULES.items():
        if any(needle in lowered for needle in needles):
            return group
    return "head"


def map_named_parts(names: list[str] | tuple[str, ...]) -> dict[str, list[str]]:
    """Map every imported node/mesh name to one animation group."""
    groups = {key: [] for key in _GROUP_RULES}
    for name in names:
        groups.setdefault(_group_for_name(name), []).append(str(name))
    return groups


def clamp_jaw_angle(degrees: float) -> float:
    return max(0.0, min(JAW_MAX_DEGREES, float(degrees)))


def _read_glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    if len(raw) < 20 or raw[:4] != b"glTF" or struct.unpack_from("<I", raw, 4)[0] != 2:
        raise ValueError("robot avatar is not a glTF 2.0 binary")
    length = struct.unpack_from("<I", raw, 8)[0]
    if length > len(raw):
        raise ValueError("robot avatar GLB is truncated")
    offset = 12
    document = None
    binary = b""
    while offset + 8 <= length:
        size, kind = struct.unpack_from("<II", raw, offset)
        chunk = raw[offset + 8:offset + 8 + size]
        if kind == 0x4E4F534A:
            document = json.loads(chunk.rstrip(b" \0").decode("utf-8"))
        elif kind == 0x004E4942:
            binary = chunk
        offset += 8 + size
    if not isinstance(document, dict) or not binary:
        raise ValueError("robot avatar GLB has no JSON or binary chunk")
    return document, binary


def inspect_robot_asset(path: Path | str = ROBOT_ASSET) -> dict[str, object]:
    """Validate the asset and return its named parts and animation groups."""
    document, _ = _read_glb(Path(path))
    names = [str(n.get("name", "")) for n in document.get("nodes", []) if n.get("name")]
    names.extend(str(m.get("name", "")) for m in document.get("meshes", []) if m.get("name"))
    return {
        "version": document.get("asset", {}).get("version"),
        "names": names,
        "groups": map_named_parts(names),
        "mesh_count": len(document.get("meshes", [])),
        "node_count": len(document.get("nodes", [])),
    }


def _accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    component = {5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}[accessor["componentType"]]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    stride = view.get("byteStride")
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    if stride:
        values = [np.frombuffer(binary[start + i * stride:start + i * stride + np.dtype(component).itemsize * width],
                                dtype=component, count=width) for i in range(accessor["count"])]
        return np.asarray(values)
    return np.frombuffer(binary, dtype=component, count=accessor["count"] * width,
                         offset=start).reshape((-1, width))


def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float32).reshape((4, 4), order="F")
    t = np.asarray(node.get("translation", [0, 0, 0]), dtype=np.float32)
    s = np.asarray(node.get("scale", [1, 1, 1]), dtype=np.float32)
    q = np.asarray(node.get("rotation", [0, 0, 0, 1]), dtype=np.float32)
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), t[0]],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), t[1]],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), t[2]],
        [0, 0, 0, 1],
    ], dtype=np.float32) @ np.diag([s[0], s[1], s[2], 1])


class RobotAvatar:
    """GLB-backed avatar with the same driver surface as :class:`HoloAvatar`."""

    SPAN = 2.4
    FRAME_LIMIT_SECONDS = 0.033
    SLOW_FRAME_LIMIT = 5

    def __init__(self, asset_path: Path | str | None = None, quality: str = "high"):
        self.asset_path = Path(asset_path or (ROBOT_LITE_ASSET if ROBOT_LITE_ASSET.exists() else ROBOT_ASSET))
        self.quality = quality if quality in ("high", "low") else "high"
        self.document, self.binary = _read_glb(self.asset_path)
        names = [str(n.get("name", "")) for n in self.document.get("nodes", []) if n.get("name")]
        names.extend(str(m.get("name", "")) for m in self.document.get("meshes", []) if m.get("name"))
        self.parts = {
            "version": self.document.get("asset", {}).get("version"),
            "names": names,
            "groups": map_named_parts(names),
            "mesh_count": len(self.document.get("meshes", [])),
            "node_count": len(self.document.get("nodes", [])),
        }
        self.groups = self.parts["groups"]
        self._meshes = self._load_meshes()
        self._time = 0.0
        self._jaw = 0.0
        self._jaw_target = 0.0
        self._blink = 0.0
        self._next_blink = random.uniform(3.0, 7.0)
        self._state = "LISTENING"
        self._expression = "neutral"
        self._colour = EYE_COLOURS["LISTENING"]
        self._yaw = self._pitch = 0.0
        self._glance = None
        self._visible = True
        self._last_frame_seconds = 0.0
        self._slow_frames = 0
        self._fallback_requested = False
        self._lighting_key = np.array([-0.35, 0.7, 0.65], dtype=np.float32)
        self._lighting_fill = np.array([0.55, 0.2, 0.35], dtype=np.float32)
        self._cache_size = 480
        self._static_layer = self._render_layer({"head", "neck", "spine", "wires"}, 0.0)
        self._jaw_layers = [
            self._render_layer({"jaw", "teeth"}, JAW_MAX_RADIANS * fraction)
            for fraction in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]
        self._eye_layer = self._render_layer({"eyes"}, 0.0)

    def _load_meshes(self) -> list[tuple[str, np.ndarray, np.ndarray, str]]:
        meshes = []
        nodes = self.document.get("nodes", [])
        worlds: dict[int, np.ndarray] = {}

        def world_matrix(index: int) -> np.ndarray:
            if index in worlds:
                return worlds[index]
            node = nodes[index]
            local = _node_matrix(node)
            parent = next((i for i, candidate in enumerate(nodes)
                           if index in candidate.get("children", [])), None)
            worlds[index] = world_matrix(parent) @ local if parent is not None else local
            return worlds[index]

        for node_index, node in enumerate(nodes):
            if "mesh" not in node:
                continue
            mesh = self.document["meshes"][node["mesh"]]
            transform = world_matrix(node_index)
            for primitive in mesh.get("primitives", []):
                position = _accessor(self.document, self.binary, primitive["attributes"]["POSITION"])
                indices = _accessor(self.document, self.binary, primitive.get("indices", 0)).reshape(-1)
                hom = np.column_stack((position, np.ones(len(position), dtype=np.float32)))
                transformed = (transform @ hom.T).T[:, :3]
                meshes.append((transformed, indices.astype(np.int64).reshape((-1, 3)),
                               _group_for_name(str(node.get("name", "")))))
        if not meshes:
            raise ValueError("robot avatar contains no drawable POSITION primitives")
        return meshes

    @property
    def jaw_angle_degrees(self) -> float:
        return math.degrees(self._jaw)

    @property
    def blink_amount(self) -> float:
        return self._blink

    @property
    def eye_colour(self) -> str:
        return self._colour

    def set_emotion(self, joy: float = 0.0, anger: float = 0.0,
                    shyness: float = 0.0, curiosity: float = 0.0,
                    neutral: float = 1.0) -> None:
        values = {
            "happy": float(joy),
            "thinking": float(curiosity),
            "surprised": float(anger),
            "listening": float(shyness),
            "neutral": float(neutral),
        }
        self._expression = max(values, key=values.get)

    def set_emotion_from_text(self, text: str) -> None:
        lowered = str(text).lower()
        if any(word in lowered for word in ("error", "failed", "offline")):
            self._state = "ERROR"
            self._colour = EYE_COLOURS["ERROR"]
        elif any(word in lowered for word in ("happy", "great", "glad")):
            self._expression = "happy"
        elif any(word in lowered for word in ("think", "consider")):
            self._expression = "thinking"

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        self._glance = (max(-1.0, min(1.0, float(dx))), max(-1.0, min(1.0, float(dy))),
                        self._time + max(0.0, float(hold)))

    def set_visible(self, visible: bool) -> None:
        self._visible = bool(visible)

    @property
    def fallback_requested(self) -> bool:
        return self._fallback_requested

    def note_frame_time(self, seconds: float) -> None:
        self._last_frame_seconds = max(0.0, float(seconds))
        if self._last_frame_seconds > self.FRAME_LIMIT_SECONDS:
            self._slow_frames += 1
            if self._slow_frames >= self.SLOW_FRAME_LIMIT:
                self._fallback_requested = True
        else:
            self._slow_frames = 0

    def step(self, dt: float, amp: float, speaking: bool = False, muted: bool = False,
             state: str = "LISTENING", v_open=None, v_wide=0.0, v_level=None,
             v_seq=None, v_hop=0.02) -> None:
        if not self._visible:
            return
        dt = max(0.0, min(0.1, float(dt)))
        self._time += dt
        self._state = "SLEEPING" if muted else str(state or "LISTENING").upper()
        self._colour = EYE_COLOURS.get(self._state, "#5ee0ff")
        if self._state in ("THINKING", "PROCESSING"):
            self._expression = "thinking"
        elif self._state == "SPEAKING":
            self._expression = "happy" if amp > 0.55 else "neutral"
        elif self._state == "LISTENING":
            self._expression = "listening"
        elif self._state in ("ERROR", "OFFLINE"):
            self._expression = "surprised"
        target = clamp_jaw_angle((float(v_level if v_level is not None else amp) *
                                  (1.0 if v_open is None else max(0.0, float(v_open)))) *
                                 JAW_MAX_DEGREES) if speaking and self._state != "SLEEPING" else 0.0
        self._jaw_target = math.radians(target)
        tau = 0.04 if self._jaw_target > self._jaw else 0.09
        self._jaw += (self._jaw_target - self._jaw) * (1.0 - math.exp(-dt / tau)) if dt else 0.0
        if self._state != "SLEEPING":
            if self._blink <= 0.0 and self._time >= self._next_blink:
                self._blink = 1.0
            if self._blink > 0.0:
                self._blink = max(0.0, self._blink - dt / 0.12)
                if self._blink == 0.0:
                    self._next_blink = self._time + random.uniform(3.0, 7.0)
        else:
            self._blink = 0.0
        if self._glance and self._time < self._glance[2]:
            self._yaw = self._glance[0] * math.radians(12)
            self._pitch = self._glance[1] * math.radians(12)
        else:
            self._glance = None
            if self._state == "SLEEPING":
                self._yaw = 0.0
                self._pitch = -math.radians(4)
            else:
                self._yaw = math.sin(self._time * 0.37) * math.radians(1.0)
                self._pitch = math.cos(self._time * 0.29) * math.radians(1.0)
            if self._state == "THINKING":
                self._pitch += math.radians(3)

    def _render_layer(self, groups: set[str], jaw_angle: float):
        from PyQt6.QtGui import QImage, QPainter, QColor, QBrush, QPen, QPolygonF
        from PyQt6.QtCore import QPointF

        image = QImage(self._cache_size, self._cache_size,
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        canvas = QPainter(image)
        canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_meshes(canvas, self._cache_size / 2, self._cache_size / 2,
                           self._cache_size * 0.42, groups, jaw_angle,
                           QPointF, QColor, QBrush, QPen, QPolygonF)
        canvas.end()
        return image

    def _paint_meshes(self, painter, cx, cy, radius, groups, jaw_angle,
                      QPointF, QColor, QBrush, QPen, QPolygonF) -> None:
        scale = radius / 1.2
        yaw_c, yaw_s = math.cos(self._yaw), math.sin(self._yaw)
        pitch_c, pitch_s = math.cos(self._pitch), math.sin(self._pitch)
        rotation = np.array([
            [yaw_c, 0.0, -yaw_s],
            [pitch_s * yaw_s, pitch_c, pitch_s * yaw_c],
            [pitch_c * yaw_s, -pitch_s, pitch_c * yaw_c],
        ], dtype=np.float32)
        for vertices, indices, group in self._meshes:
            if group not in groups:
                continue
            posed = vertices.copy()
            if group in ("jaw", "teeth"):
                pivot = np.array([0.0, 1.3, 0.0], dtype=np.float32)
                relative = posed - pivot
                angle = jaw_angle
                y = relative[:, 1] * math.cos(angle) - relative[:, 2] * math.sin(angle)
                z = relative[:, 1] * math.sin(angle) + relative[:, 2] * math.cos(angle)
                relative[:, 1], relative[:, 2] = y, z
                posed = relative + pivot
            elif group == "eyes":
                centre_y = float(np.mean(posed[:, 1]))
                posed[:, 1] = centre_y + (posed[:, 1] - centre_y) * (1.0 - 0.92 * self._blink)
            projected = posed @ rotation.T
            xy = np.column_stack((cx + projected[:, 0] * scale,
                                  cy - (projected[:, 1] - 1.2) * scale))
            depth = projected[:, 2][indices].mean(axis=1)
            order = np.argsort(depth)
            triangles = posed[indices]
            normals = np.cross(triangles[:, 1] - triangles[:, 0],
                               triangles[:, 2] - triangles[:, 0])
            lengths = np.linalg.norm(normals, axis=1)
            normals = normals / np.maximum(lengths[:, None], 1e-6)
            lighting = np.clip(
                np.maximum(0.0, normals @ self._lighting_key) * 0.75
                + np.maximum(0.0, normals @ self._lighting_fill) * 0.25,
                0.0, 1.0,
            )
            base = {
                "head": (118, 145, 164),
                "jaw": (103, 128, 148),
                "teeth": (210, 220, 220),
                "neck": (76, 96, 112),
                "spine": (61, 76, 90),
                "wires": (177, 37, 61),
                "eyes": QColor(self._colour),
            }.get(group, (118, 145, 164))
            if group == "eyes":
                painter.setBrush(QBrush(base))
                painter.setPen(QPen(base, 0.4))
            for triangle, light in zip(indices[order], lighting[order]):
                if group != "eyes":
                    r, g, b = base
                    factor = 0.52 + 0.48 * float(light)
                    colour = QColor(
                        min(255, int(r * factor)),
                        min(255, int(g * factor)),
                        min(255, int(b * factor)),
                        220 if self.quality == "high" else 185,
                    )
                    painter.setBrush(QBrush(colour))
                    painter.setPen(QPen(colour, 0.4))
                painter.drawPolygon(QPolygonF([
                    QPointF(float(xy[index, 0]), float(xy[index, 1]))
                    for index in triangle
                ]))

    def paint(self, painter, cx: float, cy: float, radius: float, primary, accent, bg) -> None:
        """Draw cached layers; only cheap Qt transforms happen per frame."""
        from PyQt6.QtGui import QColor, QPainter

        started = time.perf_counter()
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-math.degrees(self._yaw))
        painter.translate(0, math.sin(self._time * 0.8) * 2.0
                          if self._state != "SLEEPING" else 0.0)
        painter.scale(radius / (self._cache_size * 0.42),
                      radius / (self._cache_size * 0.42))
        painter.translate(-self._cache_size / 2, -self._cache_size / 2)
        painter.drawImage(0, 0, self._static_layer)
        jaw_index = min(4, max(0, int(round(
            self._jaw / JAW_MAX_RADIANS * 4
        ))))
        jaw = self._jaw_layers[jaw_index]
        painter.drawImage(0, 0, jaw)

        eye = self._eye_layer
        if self._colour != "#5ee0ff":
            tinted = eye.copy()
            tint_painter = QPainter(tinted)
            tint_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            tint_painter.fillRect(tinted.rect(), QColor(self._colour))
            tint_painter.end()
            eye = tinted
        painter.translate(self._cache_size / 2, self._cache_size / 2)
        painter.scale(1.0, max(0.08, 1.0 - 0.92 * self._blink))
        painter.translate(-self._cache_size / 2, -self._cache_size / 2)
        painter.drawImage(0, 0, eye)
        painter.restore()
        self.note_frame_time(time.perf_counter() - started)
