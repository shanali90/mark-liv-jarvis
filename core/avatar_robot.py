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
from pathlib import Path

import numpy as np

ROBOT_ASSET = Path(__file__).resolve().parent.parent / "assets" / "avatar" / "robo_face.glb"
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

    def __init__(self, asset_path: Path | str = ROBOT_ASSET, quality: str = "high"):
        self.asset_path = Path(asset_path)
        self.quality = quality if quality in ("high", "low") else "high"
        self.document, self.binary = _read_glb(self.asset_path)
        self.parts = inspect_robot_asset(self.asset_path)
        self.groups = self.parts["groups"]
        self._meshes = self._load_meshes()
        self._time = 0.0
        self._jaw = 0.0
        self._jaw_target = 0.0
        self._blink = 0.0
        self._next_blink = random.uniform(3.0, 7.0)
        self._state = "LISTENING"
        self._colour = EYE_COLOURS["LISTENING"]
        self._yaw = self._pitch = 0.0
        self._glance = None
        self._visible = True

    def _load_meshes(self) -> list[tuple[str, np.ndarray, np.ndarray, str]]:
        meshes = []
        nodes = self.document.get("nodes", [])
        for node in nodes:
            if "mesh" not in node:
                continue
            mesh = self.document["meshes"][node["mesh"]]
            transform = _node_matrix(node)
            for primitive in mesh.get("primitives", []):
                position = _accessor(self.document, self.binary, primitive["attributes"]["POSITION"])
                indices = _accessor(self.document, self.binary, primitive.get("indices", 0)).reshape(-1)
                hom = np.column_stack((position, np.ones(len(position), dtype=np.float32)))
                transformed = (transform @ hom.T).T[:, :3]
                meshes.append((str(node.get("name", mesh.get("name", ""))), transformed,
                               indices.astype(np.int64), _group_for_name(str(node.get("name", "")))))
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

    def set_emotion(self, *args, **kwargs) -> None:
        return None

    def set_emotion_from_text(self, text: str) -> None:
        if any(word in str(text).lower() for word in ("error", "failed", "offline")):
            self._state = "ERROR"
            self._colour = EYE_COLOURS["ERROR"]

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        self._glance = (max(-1.0, min(1.0, float(dx))), max(-1.0, min(1.0, float(dy))),
                        self._time + max(0.0, float(hold)))

    def set_visible(self, visible: bool) -> None:
        self._visible = bool(visible)

    def step(self, dt: float, amp: float, speaking: bool = False, muted: bool = False,
             state: str = "LISTENING", v_open=None, v_wide=0.0, v_level=None,
             v_seq=None, v_hop=0.02) -> None:
        if not self._visible:
            return
        dt = max(0.0, min(0.1, float(dt)))
        self._time += dt
        self._state = "SLEEPING" if muted else str(state or "LISTENING").upper()
        self._colour = EYE_COLOURS.get(self._state, "#5ee0ff")
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
            self._yaw = math.sin(self._time * 0.37) * math.radians(1.0)
            self._pitch = math.cos(self._time * 0.29) * math.radians(1.0)
            if self._state == "THINKING":
                self._pitch += math.radians(3)
            elif self._state == "SLEEPING":
                self._pitch -= math.radians(4)

    def paint(self, painter, cx: float, cy: float, radius: float, primary, accent, bg) -> None:
        """Draw a small, depth-sorted projection; Qt handles the final glow."""
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QColor, QPolygonF, QBrush, QPen
        scale = radius / 1.2
        for name, vertices, indices, group in self._meshes:
            posed = vertices.copy()
            if group in ("jaw", "teeth"):
                pivot = np.array([0.0, 1.3, 0.0], dtype=np.float32)
                relative = posed - pivot
                angle = self._jaw
                y = relative[:, 1] * math.cos(angle) - relative[:, 2] * math.sin(angle)
                z = relative[:, 1] * math.sin(angle) + relative[:, 2] * math.cos(angle)
                relative[:, 1], relative[:, 2] = y, z
                posed = relative + pivot
            elif group == "eyes":
                centre_y = float(np.mean(posed[:, 1]))
                posed[:, 1] = centre_y + (posed[:, 1] - centre_y) * (1.0 - 0.92 * self._blink)
            points = []
            for x, y, z in posed:
                xx = x * math.cos(self._yaw) - z * math.sin(self._yaw)
                zz = x * math.sin(self._yaw) + z * math.cos(self._yaw)
                yy = y * math.cos(self._pitch) - zz * math.sin(self._pitch)
                points.append(QPointF(cx + xx * scale, cy - yy * scale))
            colour = QColor(self._colour if group == "eyes" else "#a5b6c4")
            if group == "wires":
                colour = QColor("#d92f4d")
            colour.setAlpha(220 if self.quality == "high" else 185)
            painter.setBrush(QBrush(colour))
            painter.setPen(QPen(colour, 0.4))
            for i in range(0, len(indices) - 2, 3):
                tri = indices[i:i + 3]
                if len(tri) == 3:
                    painter.drawPolygon(QPolygonF([points[int(v)] for v in tri]))
