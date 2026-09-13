"""Closed male keys and clearance-expanded sockets in a local face frame."""

from dataclasses import dataclass
from math import cos, isfinite, pi, sin
from typing import Self

import bpy
from mathutils import Matrix, Vector

from .units import mm_to_units

type KeyGeometry = tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]


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

    @classmethod
    def from_mm(
        cls,
        shape: str,
        width: float,
        length: float,
        height: float,
        embed: float,
        clearance: float,
        depth_clearance: float,
        *,
        scale_length: float,
        taper: float = 0.2,
    ) -> Self:
        """Convert millimetre dimensions using the scene's unit scale."""
        return cls(
            shape,
            *(
                mm_to_units(value, scale_length)
                for value in (width, length, height, embed, clearance, depth_clearance)
            ),
            taper=taper,
        )

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

    def geometry(self, *, socket: bool = False) -> KeyGeometry:
        """Build closed rings with constant root width and lateral clearance.

        Taper starts at the contact plane (Z=0) and continues beyond the
        socket tip, preserving clearance at matching heights.
        """
        self.validate()
        gap = self.clearance if socket else 0.0
        top = self.height + (self.depth_clearance if socket else 0.0)
        count = 4 if self.shape == "RECTANGLE" else 64
        vertices = [
            vertex
            for z in (-self.embed, 0.0, top)
            for vertex in self._ring(z, gap, count)
        ]
        faces: list[tuple[int, ...]] = [tuple(reversed(range(count)))]
        for ring in range(2):
            for i in range(count):
                a = ring * count + i
                b = ring * count + (i + 1) % count
                faces.append((a, b, b + count, a + count))
        faces.append(tuple(range(2 * count, 3 * count)))
        return vertices, faces

    def _ring(
        self, z: float, gap: float, count: int
    ) -> list[tuple[float, float, float]]:
        factor = 1.0
        if self.shape == "TAPERED" and z > 0:
            factor -= self.taper * z / self.height
        x = self.width * factor / 2 + gap
        y = self.length / 2 + gap
        if self.shape == "RECTANGLE":
            return [(a * x, b * y, z) for a, b in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
        return [
            (x * cos(2 * pi * i / count), x * sin(2 * pi * i / count), z)
            for i in range(count)
        ]

    def create_mesh(self, name: str, *, socket: bool = False) -> bpy.types.Mesh:
        """Allocate the closed geometry as a Blender mesh."""
        vertices, faces = self.geometry(socket=socket)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        return mesh


def key_geometry(dimensions: KeyDimensions, *, socket: bool = False) -> KeyGeometry:
    """Build a closed key; the socket adds lateral and tip clearance."""
    return dimensions.geometry(socket=socket)


def create_key_mesh(
    name: str, dimensions: KeyDimensions, *, socket: bool = False
) -> bpy.types.Mesh:
    """Allocate the closed geometry as a Blender mesh."""
    return dimensions.create_mesh(name, socket=socket)


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
