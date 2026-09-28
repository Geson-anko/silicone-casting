"""Closed male keys and clearance-expanded sockets in a local face frame."""

from dataclasses import dataclass
from math import cos, isfinite, pi, sin
from typing import Final, NamedTuple, Self

import bpy
from mathutils import Matrix, Vector

from .units import mm_to_units

type Vertex = tuple[float, float, float]
type Face = tuple[int, ...]

_SHAPES: Final = frozenset({"CYLINDER", "TAPERED", "RECTANGLE"})
# Polygon count that keeps round keys visually smooth at typical key sizes.
_ROUND_SEGMENTS: Final = 64
# Leaves at least a 10% tip so a tapered key never collapses to a point.
MAX_TAPER: Final = 0.9
_DEFAULT_TAPER: Final = 0.2
# Below this squared length a normal has no usable direction.
_MIN_NORMAL_LENGTH_SQUARED: Final = 1e-20


def validate_normal(normal: Vector) -> None:
    """Reject a surface normal that cannot define a key direction.

    Args:
        normal: Surface normal in any space; it need not be normalized.

    Raises:
        ValueError: If the normal is (numerically) zero.
    """
    if normal.length_squared < _MIN_NORMAL_LENGTH_SQUARED:
        raise ValueError("Surface normal must be nonzero")


class KeyGeometry(NamedTuple):
    """Closed key solid as vertices and outward-facing polygons."""

    vertices: list[Vertex]
    faces: list[Face]

    def edges(self) -> set[tuple[int, int]]:
        """Return each polygon edge once, as an ordered vertex index pair."""
        return {
            (min(a, b), max(a, b))
            for face in self.faces
            for a, b in zip(face, face[1:] + face[:1])
        }


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
    taper: float = _DEFAULT_TAPER

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
        taper: float = _DEFAULT_TAPER,
    ) -> Self:
        """Convert millimetre dimensions using the scene's unit scale.

        Args:
            shape: ``CYLINDER``, ``TAPERED`` or ``RECTANGLE``.
            width: Root width (diameter for round keys) in millimetres.
            length: Rectangle length in millimetres; ignored by round keys.
            height: Protrusion above the contact plane in millimetres.
            embed: Depth below the contact plane in millimetres.
            clearance: Socket gap on each side in millimetres.
            depth_clearance: Extra socket depth beyond the tip in millimetres.
            scale_length: The scene's ``unit_settings.scale_length``.
            taper: Fraction of the width lost from the contact plane to the tip.

        Returns:
            Unvalidated dimensions in scene units.
        """
        return cls(
            shape,
            *(
                mm_to_units(value, scale_length)
                for value in (width, length, height, embed, clearance, depth_clearance)
            ),
            taper=taper,
        )

    def validate(self) -> None:
        """Reject degenerate solids before allocating Blender data.

        Raises:
            ValueError: If the shape is unknown, a size is not finite and
                positive, a clearance is negative, or the taper is out of range
                or would close before the socket tip.
        """
        if self.shape not in _SHAPES:
            raise ValueError("Unknown key shape")
        sizes = (self.width, self.length, self.height, self.embed)
        gaps = (self.clearance, self.depth_clearance)
        if any(not isfinite(size) or size <= 0 for size in sizes):
            raise ValueError("Key dimensions must be finite and positive")
        if any(not isfinite(gap) or gap < 0 for gap in gaps):
            raise ValueError("Clearance must be finite and nonnegative")
        if not isfinite(self.taper) or not 0 <= self.taper <= MAX_TAPER:
            raise ValueError("Taper must be between 0 and 0.9")
        if self.shape == "TAPERED" and self._taper_factor(self._socket_top()) <= 0:
            raise ValueError("Depth clearance exceeds the tapered tip")

    def geometry(self, *, socket: bool = False) -> KeyGeometry:
        """Build the closed pin or socket solid in the key's local frame.

        The solid is three rings (embed bottom, contact plane at Z=0, tip)
        of constant root width. Taper starts at the contact plane and continues
        past the pin tip into the socket, so clearance holds at every height.

        Args:
            socket: Build the socket, expanded by clearance and depth clearance.

        Returns:
            Vertices and outward-facing faces of one watertight solid.

        Raises:
            ValueError: If the dimensions are invalid.
        """
        self.validate()
        gap = self.clearance if socket else 0.0
        top = self._socket_top() if socket else self.height
        count = 4 if self.shape == "RECTANGLE" else _ROUND_SEGMENTS
        vertices = [
            vertex
            for z in (-self.embed, 0.0, top)
            for vertex in self._ring(z, gap, count)
        ]
        return KeyGeometry(vertices, self._faces(count))

    def create_mesh(self, name: str, *, socket: bool = False) -> bpy.types.Mesh:
        """Allocate the closed pin or socket geometry as a Blender mesh.

        Args:
            name: Name of the new mesh datablock.
            socket: Build the socket instead of the pin.

        Returns:
            A new mesh; it is removed again if filling it fails.

        Raises:
            ValueError: If the dimensions are invalid; no mesh is allocated.
        """
        vertices, faces = self.geometry(socket=socket)
        mesh = bpy.data.meshes.new(name)
        try:
            mesh.from_pydata(vertices, [], faces)
            mesh.update()
        except (ValueError, RuntimeError):
            bpy.data.meshes.remove(mesh)
            raise
        return mesh

    def _socket_top(self) -> float:
        return self.height + self.depth_clearance

    def _taper_factor(self, z: float) -> float:
        """Width fraction at height ``z``; only a tapered tip narrows."""
        if self.shape != "TAPERED" or z <= 0:
            return 1.0
        return 1.0 - self.taper * z / self.height

    def _ring(self, z: float, gap: float, count: int) -> list[Vertex]:
        half_width = self.width * self._taper_factor(z) / 2 + gap
        half_length = self.length / 2 + gap
        if self.shape == "RECTANGLE":
            corners = ((1, 1), (-1, 1), (-1, -1), (1, -1))
            return [(sx * half_width, sy * half_length, z) for sx, sy in corners]
        return [
            (
                half_width * cos(2 * pi * index / count),
                half_width * sin(2 * pi * index / count),
                z,
            )
            for index in range(count)
        ]

    @staticmethod
    def _faces(count: int) -> list[Face]:
        """Cap the bottom and top rings and join the three rings with quads."""
        faces: list[Face] = [tuple(reversed(range(count)))]
        for ring in range(2):
            start = ring * count
            for index in range(count):
                a = start + index
                b = start + (index + 1) % count
                faces.append((a, b, b + count, a + count))
        faces.append(tuple(range(2 * count, 3 * count)))
        return faces


def placement_matrix(position: Vector, normal: Vector, angle: float = 0) -> Matrix:
    """Return a rigid world frame whose Z axis follows the surface normal.

    Args:
        position: World-space contact point, which becomes the frame origin.
        normal: Direction the key protrudes; it need not be normalized.
        angle: In-plane rotation around the normal, in radians.

    Returns:
        A 4x4 rotation plus translation without scale.

    Raises:
        ValueError: If the normal is zero.
    """
    validate_normal(normal)
    rotation = normal.normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()
    return (
        Matrix.Translation((position.x, position.y, position.z))
        @ rotation
        @ Matrix.Rotation(angle, 4, "Z")
    )
