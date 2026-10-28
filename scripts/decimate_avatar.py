"""Create the lightweight robot avatar asset from the supplied GLB."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.avatar_robot import _accessor, _read_glb


SOURCE = ROOT / "assets" / "avatar" / "robo_face.glb"
TARGET = ROOT / "assets" / "avatar" / "robo_face_lite.glb"
MAX_TRIANGLES = 15000


def main() -> None:
    document, binary = _read_glb(SOURCE)
    node_names = {
        node.get("mesh"): str(node.get("name", ""))
        for node in document.get("nodes", []) if "mesh" in node
    }
    primitives = []
    total = sum(
        len(_accessor(document, binary, primitive["indices"]).reshape(-1)) // 3
        for mesh_index, mesh in enumerate(document.get("meshes", []))
        if "_wire_" not in node_names.get(mesh_index, "").lower()
        for primitive in mesh.get("primitives", [])
    )
    budget = min(MAX_TRIANGLES, total)
    remaining = budget
    for mesh_index, mesh in enumerate(document.get("meshes", [])):
        if "_wire_" in node_names.get(mesh_index, "").lower():
            primitives.append([])
            continue
        mesh_primitives = []
        for primitive in mesh.get("primitives", []):
            positions = _accessor(document, binary, primitive["attributes"]["POSITION"]).astype(np.float32)
            indices = _accessor(document, binary, primitive["indices"]).reshape(-1).astype(np.uint32)
            triangles = indices.reshape((-1, 3))
            count = len(triangles)
            take = min(count, max(1, round(count * remaining / max(1, total))))
            chosen = np.linspace(0, count - 1, take, dtype=np.int64)
            mesh_primitives.append((positions, triangles[chosen].reshape(-1)))
            remaining -= take
            total -= count
        primitives.append(mesh_primitives)

    out_bin = bytearray()
    out_meshes = []
    buffer_views = []
    accessors = []

    def add_array(array: np.ndarray, component_type: int, kind: str) -> int:
        raw = array.tobytes()
        while len(out_bin) % 4:
            out_bin.append(0)
        offset = len(out_bin)
        out_bin.extend(raw)
        view_index = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw)})
        accessor_index = len(accessors)
        accessors.append({
            "bufferView": view_index,
            "componentType": component_type,
            "count": len(array) if kind == "SCALAR" else len(array),
            "type": kind,
        })
        if kind == "VEC3":
            accessors[-1]["min"] = array.min(axis=0).tolist()
            accessors[-1]["max"] = array.max(axis=0).tolist()
        return accessor_index

    for mesh_primitives in primitives:
        new_primitives = []
        for positions, indices in mesh_primitives:
            position_accessor = add_array(positions, 5126, "VEC3")
            index_accessor = add_array(indices, 5125, "SCALAR")
            new_primitives.append({
                "attributes": {"POSITION": position_accessor},
                "indices": index_accessor,
                "mode": 4,
            })
        out_meshes.append({"primitives": new_primitives})

    out_doc = {
        "asset": {"version": "2.0", "generator": "Mark-LIV avatar decimator"},
        "scene": document.get("scene", 0),
        "scenes": document.get("scenes", [{"nodes": list(range(len(document.get("nodes", []))))}]),
        "nodes": document.get("nodes", []),
        "meshes": out_meshes,
        "buffers": [{"byteLength": len(out_bin)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    encoded = json.dumps(out_doc, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    payload = bytes(out_bin)
    header_length = 12 + 8 + len(encoded) + 8 + len(payload)
    with TARGET.open("wb") as handle:
        handle.write(struct.pack("<4sII", b"glTF", 2, header_length))
        handle.write(struct.pack("<II", len(encoded), 0x4E4F534A))
        handle.write(encoded)
        handle.write(struct.pack("<II", len(payload), 0x004E4942))
        handle.write(payload)
    print(f"wrote {TARGET} ({sum(len(i[1]) // 3 for m in primitives for i in m)} triangles)")


if __name__ == "__main__":
    main()
