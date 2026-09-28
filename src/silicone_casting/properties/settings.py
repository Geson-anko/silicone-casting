"""Typed scene settings and ownership of mixture and color profiles."""

from math import atan, pi, tan
from typing import TYPE_CHECKING, Literal, cast

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
)

from ..core.solidify import MIN_THICKNESS_MM
from ..core.surface_cut import MIN_SURFACE_CUT_THICKNESS_MM
from ._distance import distance_property
from .color import SiliconeCastingColorProfile
from .mixture import SiliconeCastingMixture

type BooleanSolver = Literal["MANIFOLD", "EXACT", "FLOAT"]

_BOOLEAN_SOLVERS = (
    (
        "MANIFOLD",
        "Manifold",
        "Fastest solver for manifold meshes",
    ),
    (
        "EXACT",
        "Exact",
        "Best results for overlapping and coplanar geometry",
    ),
    (
        "FLOAT",
        "Float",
        "Simple fast solver without overlapping geometry support",
    ),
)


class SiliconeCastingProperties(bpy.types.PropertyGroup):
    """Processing settings and saved recipes stored on
    ``Scene.silicone_casting``."""

    def active_color_profile(self) -> SiliconeCastingColorProfile | None:
        """Return the selected profile when its row still exists."""
        index = self.color_profile_active_index
        return (
            self.color_profiles[index]
            if 0 <= index < len(self.color_profiles)
            else None
        )

    def add_color_profile(self) -> SiliconeCastingColorProfile:
        """Append a default named profile, select it, and create its
        preview."""
        profile = self.color_profiles.add()
        profile.profile_name = f"Profile {len(self.color_profiles)}"
        self.color_profile_active_index = len(self.color_profiles) - 1
        profile.ensure_preview_material()
        return profile

    def remove_active_color_profile(self) -> bool:
        """Remove the selected profile while retaining its applied material."""
        if self.active_color_profile() is None:
            return False
        index = self.color_profile_active_index
        self.color_profiles.remove(index)
        self.color_profile_active_index = min(index, len(self.color_profiles) - 1)
        profile = self.active_color_profile()
        if profile is not None:
            profile.ensure_preview_material()
        return True

    def _mesh_object_poll(self, obj: bpy.types.Object) -> bool:
        """Only offer mesh objects in operand and socket pickers."""
        return obj.type == "MESH"

    def _get_key_taper_angle(self) -> float:
        return atan(self.key_width_mm * self.key_taper / (2 * self.key_height_mm))

    def _set_key_taper_angle(self, value: float) -> None:
        self.key_taper = min(
            0.9, 2 * self.key_height_mm * tan(value) / self.key_width_mm
        )

    if TYPE_CHECKING:
        solidify_thickness_mm: float
        solidify_thickness: float
        solidify_flip: bool
        solidify_even_thickness: bool
        air_vent_diameter_mm: float
        air_vent_diameter: float
        key_width_mm: float
        key_length_mm: float
        key_height_mm: float
        key_embed_mm: float
        key_clearance_mm: float
        key_depth_clearance_mm: float
        key_width: float
        key_length: float
        key_height: float
        key_embed: float
        key_clearance: float
        key_depth_clearance: float
        key_active: bpy.types.Object | None
        key_axis: Literal["X", "Y", "Z"]
        key_shape: Literal["CYLINDER", "TAPERED", "RECTANGLE"]
        key_taper: float
        key_taper_angle: float
        key_angle: float
        key_align_normal: bool
        key_flip: bool
        key_mate: bpy.types.Object | None
        inherit_collection: bpy.types.Collection | None
        boolean_operand: bpy.types.Object | None
        boolean_solver: BooleanSolver
        surface_cut_thickness_mm: float
        surface_cut_thickness: float
        surface_cut_margin_mm: float
        surface_cut_input_mode: Literal["FREEHAND", "VERTEX", "EDGE"]
        surface_cut_margin: float
        volume_ml: float
        volume_measured: bool
        color_profiles: bpy.types.bpy_prop_collection_idprop[
            SiliconeCastingColorProfile
        ]
        color_profile_active_index: int
        mixture: SiliconeCastingMixture
    else:
        solidify_thickness_mm: FloatProperty(
            name="Thickness (mm)",
            description="Wall thickness in millimetres, regardless of scene units",
            default=3.0,
            min=MIN_THICKNESS_MM,
            soft_max=50.0,
            precision=2,
        )

        solidify_thickness: distance_property(
            "solidify_thickness_mm",
            "Thickness",
            "Wall thickness in scene distance units",
        )

        solidify_flip: BoolProperty(
            name="Flip Direction",
            description="Grow the wall inwards instead of outwards",
            default=False,
        )

        solidify_even_thickness: BoolProperty(
            name="Even Thickness",
            description="Keep the requested wall thickness around corners",
            default=True,
        )

        air_vent_diameter_mm: FloatProperty(
            name="Vent Diameter (mm)",
            default=2.0,
            min=0.01,
            options={"HIDDEN"},
        )

        air_vent_diameter: distance_property(
            "air_vent_diameter_mm",
            "Diameter",
            "Air channel diameter; updates the current drawing preview",
        )

        key_width_mm: FloatProperty(
            name="Width / Diameter (mm)",
            default=4,
            min=0.01,
            precision=3,
        )

        key_length_mm: FloatProperty(
            name="Length (mm)",
            default=8,
            min=0.01,
            precision=3,
        )

        key_height_mm: FloatProperty(
            name="Protrusion (mm)",
            default=3,
            min=0.01,
            precision=3,
        )

        key_embed_mm: FloatProperty(
            name="Root Overlap (mm)",
            default=1,
            min=0.01,
            precision=3,
        )

        key_clearance_mm: FloatProperty(
            name="Clearance per Side (mm)",
            default=0.15,
            min=0,
            precision=3,
        )

        key_depth_clearance_mm: FloatProperty(
            name="Tip Clearance (mm)",
            default=0.2,
            min=0,
            precision=3,
        )

        key_width: distance_property("key_width_mm", "Width / Diameter")

        key_length: distance_property("key_length_mm", "Length")

        key_height: distance_property("key_height_mm", "Protrusion")

        key_embed: distance_property("key_embed_mm", "Root Overlap")

        key_clearance: distance_property("key_clearance_mm", "Clearance per Side")

        key_depth_clearance: distance_property(
            "key_depth_clearance_mm", "Tip Clearance"
        )

        key_active: PointerProperty(
            name="Selected Key",
            type=bpy.types.Object,
        )

        key_axis: EnumProperty(
            name="Direction",
            items=(("X", "X", "World X"), ("Y", "Y", "World Y"), ("Z", "Z", "World Z")),
            default="Z",
        )

        key_shape: EnumProperty(
            name="Shape",
            items=(
                ("CYLINDER", "Round Dowel", "Cylindrical alignment pin"),
                ("TAPERED", "Tapered Dowel", "Lead-in taper for easier assembly"),
                (
                    "RECTANGLE",
                    "Rectangular Key",
                    "Anti-rotation key or elongated tongue and groove",
                ),
            ),
            default="TAPERED",
        )

        key_taper: FloatProperty(
            name="Tip Reduction",
            subtype="FACTOR",
            default=0.2,
            min=0.0,
            max=0.9,
        )

        key_taper_angle: FloatProperty(
            name="Taper Angle",
            description=(
                "Sidewall angle from the dowel axis (0 is cylindrical). "
                "Linked to tip reduction, diameter and protrusion; "
                "limited to 90% tip reduction. Changing dimensions recalculates the angle"
            ),
            subtype="ANGLE",
            unit="ROTATION",
            min=0.0,
            max=pi / 2 - 0.0001,
            precision=2,
            get=_get_key_taper_angle,
            set=_set_key_taper_angle,
        )

        key_angle: FloatProperty(
            name="Rotation",
            subtype="ANGLE",
            default=0.0,
        )

        key_align_normal: BoolProperty(
            name="Perpendicular to Face",
            default=True,
            description="Align with the nearest face normal; disable to use the selected world axis",
        )

        key_flip: BoolProperty(
            name="Flip Direction",
            default=False,
        )

        key_mate: PointerProperty(
            name="Socket Half",
            type=bpy.types.Object,
            poll=_mesh_object_poll,
        )

        inherit_collection: PointerProperty(
            name="Collection",
            description="Collection whose meshes are inherited as a Boolean union",
            type=bpy.types.Collection,
        )

        boolean_operand: PointerProperty(
            name="Operand",
            description="Mesh object used by the Boolean modifier",
            type=bpy.types.Object,
            poll=_mesh_object_poll,
        )

        boolean_solver: EnumProperty(
            name="Solver",
            description="Method used to calculate the Boolean operation",
            items=_BOOLEAN_SOLVERS,
            default="EXACT",
        )

        surface_cut_thickness_mm: FloatProperty(
            name="Thickness (mm)",
            description="Surface Cut thickness in millimetres, regardless of scene units",
            default=MIN_SURFACE_CUT_THICKNESS_MM,
            min=MIN_SURFACE_CUT_THICKNESS_MM,
            precision=3,
        )

        surface_cut_thickness: distance_property(
            "surface_cut_thickness_mm",
            "Thickness",
            "Surface Cut thickness in scene distance units",
        )

        surface_cut_margin_mm: FloatProperty(
            name="Boundary Extension (mm)",
            description=(
                "Extend the drawn cutting surface outward past its boundary by this "
                "many millimetres; 0 disables extension. Used when drawing a new surface"
            ),
            default=0.1,
            min=0.0,
            precision=3,
        )

        surface_cut_input_mode: EnumProperty(
            name="Input",
            description="How to add points to the cutting boundary while drawing",
            items=(
                (
                    "FREEHAND",
                    "Freehand",
                    "Draw on the visible surface; Ctrl-click for a line",
                ),
                (
                    "VERTEX",
                    "Vertex",
                    "Click visible mesh vertices to snap the stroke endpoints",
                ),
                ("EDGE", "Edge", "Click connected mesh edges to build the boundary"),
            ),
            default="FREEHAND",
        )

        surface_cut_margin: distance_property(
            "surface_cut_margin_mm",
            "Boundary Extension",
            "Extend the cutting surface past its boundary; updates while drawing",
        )

        volume_ml: FloatProperty(
            name="Volume (mL)",
            description=(
                "Total volume of the meshes selected when Measure Volume was last "
                "used. It is a snapshot: later changes to the scene do not update it"
            ),
            default=0.0,
            min=0.0,
            precision=2,
        )

        volume_measured: BoolProperty(
            name="Measured",
            description="Whether Volume (mL) holds the result of a measurement",
            default=False,
        )

        color_profiles: CollectionProperty(
            type=SiliconeCastingColorProfile,
        )

        color_profile_active_index: IntProperty(
            name="Active Color Profile",
            default=-1,
            min=-1,
            options={"HIDDEN"},
        )

        mixture: PointerProperty(type=SiliconeCastingMixture)


def scene_settings(context: bpy.types.Context) -> SiliconeCastingProperties:
    """Read the registered scene property group at the Blender context
    boundary."""
    return cast(SiliconeCastingProperties, context.scene.silicone_casting)
