"""Closed male keys and clearance-expanded sockets in a local face frame."""

from dataclasses import dataclass
from math import cos, isfinite, pi, sin

import bpy
from mathutils import Matrix, Vector


@dataclass(frozen=True)
class KeyDimensions:
    """Dimensions in scene units; clearance is measured on each side."""

    shape: str
    width: float
    length: float
    height: float
    embed: float
    clearance: float
    depth_clearance: float
    taper: float = 0.2

    def validate(self) -> None:
        """Reject degenerate solids before allocating Blender data."""
        if self.shape not in {"CYLINDER", "TAPERED", "RECTANGLE"}:
            raise ValueError("Unknown key shape")
        positive = (self.width, self.length, self.height, self.embed)
        gaps = (self.clearance, self.depth_clearance)
        if any(not isfinite(v) or v <= 0 for v in positive):
            raise ValueError("Key dimensions must be finite and positive")
        if any(not isfinite(v) or v < 0 for v in gaps):
            raise ValueError("Clearance must be finite and nonnegative")
        if not isfinite(self.taper) or not 0 <= self.taper <= 0.9:
            raise ValueError("Taper must be between 0 and 0.9")
        if self.shape == "TAPERED" and (
            1 - self.taper * (1 + self.depth_clearance / self.height) <= 0
        ):
            raise ValueError("Depth clearance exceeds the tapered tip")


def create_key_mesh(
    name: str, dimensions: KeyDimensions, *, socket: bool = False
) -> bpy.types.Mesh:
    """Build a closed key; the socket adds lateral and tip clearance.

    Taper starts at the contact plane (Z=0). Below that plane the root
    keeps its full width, ensuring a positive overlap with the male
    half. Socket taper continues beyond the tip so lateral clearance
    stays constant at matching heights.
    """
    d = dimensions
    d.validate()
    gap = d.clearance if socket else 0.0
    top = d.height + (d.depth_clearance if socket else 0.0)
    vertices: list[tuple[float, float, float]] = []
    count = 4 if d.shape == "RECTANGLE" else 64
    for z in (-d.embed, 0.0, top):
        factor = 1.0
        if d.shape == "TAPERED" and z > 0:
            factor -= d.taper * z / d.height
        x = d.width * factor / 2 + gap
        y = d.length / 2 + gap
        if d.shape == "RECTANGLE":
            vertices.extend(
                (a * x, b * y, z) for a, b in ((1, 1), (-1, 1), (-1, -1), (1, -1))
            )
        else:
            vertices.extend(
                (x * cos(2 * pi * i / count), x * sin(2 * pi * i / count), z)
                for i in range(count)
            )
    faces: list[tuple[int, ...]] = [tuple(reversed(range(count)))]
    for ring in range(2):
        for i in range(count):
            a = ring * count + i
            b = ring * count + (i + 1) % count
            faces.append((a, b, b + count, a + count))
    faces.append(tuple(range(2 * count, 3 * count)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def placement_matrix(position: Vector, normal: Vector, angle: float = 0) -> Matrix:
    """Return a rigid world frame whose Z axis follows the surface normal."""
    if normal.length_squared < 1e-20:
        raise ValueError("Surface normal must be nonzero")
    rotation = normal.normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()
    return (
        Matrix.Translation((position.x, position.y, position.z))
        @ rotation
        @ Matrix.Rotation(angle, 4, "Z")
    )
