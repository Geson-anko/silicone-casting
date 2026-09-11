"""Scene-level RNA settings and child property-group aggregation."""

from math import atan, pi, tan
from typing import cast

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
)

from ..core import MIN_SURFACE_CUT_THICKNESS_MM, MIN_THICKNESS_MM, mm_to_units
from ._color_properties import SiliconeCastingColorProfile
from ._mixture_properties import (
    MixtureSelectionState,
    SiliconeCastingMixturePart,
)

_MIN_DENSITY_G_PER_ML = 0.001
_MIN_MIXTURE_RATIO = 0.001

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


def _mesh_object_poll(
    _settings: bpy.types.PropertyGroup, obj: bpy.types.Object
) -> bool:
    """Only offer mesh objects in the Boolean operand picker."""
    return obj.type == "MESH"


class SiliconeCastingProperties(bpy.types.PropertyGroup):
    """Settings stored on the scene as ``Scene.silicone_casting``."""

    def _select_active_mixture_part(self, _context: bpy.types.Context) -> None:
        """Mirror native UI-list activation into the saved row selection."""
        state = cast(MixtureSelectionState, self)
        index = state.mixture_active_index
        if not 0 <= index < len(state.mixture_parts):
            return
        for part_index, part in enumerate(state.mixture_parts):
            part.selected = part_index == index
        state.mixture_selection_anchor = index

    # Keep legacy millimetre storage; distance inputs below convert scene units.
    solidify_thickness_mm: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Thickness (mm)",
        description="Wall thickness in millimetres, regardless of scene units",
        default=3.0,
        min=MIN_THICKNESS_MM,
        soft_max=50.0,
        precision=2,
    )

    def _get_solidify_thickness(self) -> float:
        scene = cast(bpy.types.Scene, self.id_data)
        return mm_to_units(
            cast(float, getattr(self, "solidify_thickness_mm")),
            scene.unit_settings.scale_length,
        )

    def _set_solidify_thickness(self, value: float) -> None:
        scene = cast(bpy.types.Scene, self.id_data)
        self.solidify_thickness_mm = value * scene.unit_settings.scale_length * 1000

    solidify_thickness: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Thickness",
        description="Wall thickness in scene distance units",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=_get_solidify_thickness,
        set=_set_solidify_thickness,
    )

    solidify_flip: BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Flip Direction",
        description="Grow the wall inwards instead of outwards",
        default=False,
    )

    solidify_even_thickness: BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Even Thickness",
        description="Keep the requested wall thickness around corners",
        default=True,
    )

    key_width_mm: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Width / Diameter (mm)",
        default=4,
        min=0.01,
        precision=3,
    )

    key_length_mm: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Length (mm)",
        default=8,
        min=0.01,
        precision=3,
    )

    key_height_mm: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Protrusion (mm)",
        default=3,
        min=0.01,
        precision=3,
    )

    key_embed_mm: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Root Overlap (mm)",
        default=1,
        min=0.01,
        precision=3,
    )

    key_clearance_mm: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Clearance per Side (mm)",
        default=0.15,
        min=0,
        precision=3,
    )

    key_depth_clearance_mm: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Tip Clearance (mm)",
        default=0.2,
        min=0,
        precision=3,
    )

    # Preserve saved millimetres while exposing native scene-distance inputs.
    def _get_key_width(self) -> float:
        scene = cast(bpy.types.Scene, self.id_data)
        return mm_to_units(
            cast(float, getattr(self, "key_width_mm")),
            scene.unit_settings.scale_length,
        )

    def _set_key_width(self, value: float) -> None:
        scene = cast(bpy.types.Scene, self.id_data)
        self.key_width_mm = value * scene.unit_settings.scale_length * 1000

    key_width: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Width / Diameter",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=_get_key_width,
        set=_set_key_width,
    )

    def _get_key_length(self) -> float:
        scene = cast(bpy.types.Scene, self.id_data)
        return mm_to_units(
            cast(float, getattr(self, "key_length_mm")),
            scene.unit_settings.scale_length,
        )

    def _set_key_length(self, value: float) -> None:
        scene = cast(bpy.types.Scene, self.id_data)
        self.key_length_mm = value * scene.unit_settings.scale_length * 1000

    key_length: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Length",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=_get_key_length,
        set=_set_key_length,
    )

    def _get_key_height(self) -> float:
        scene = cast(bpy.types.Scene, self.id_data)
        return mm_to_units(
            cast(float, getattr(self, "key_height_mm")),
            scene.unit_settings.scale_length,
        )

    def _set_key_height(self, value: float) -> None:
        scene = cast(bpy.types.Scene, self.id_data)
        self.key_height_mm = value * scene.unit_settings.scale_length * 1000

    key_height: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Protrusion",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=_get_key_height,
        set=_set_key_height,
    )

    def _get_key_embed(self) -> float:
        scene = cast(bpy.types.Scene, self.id_data)
        return mm_to_units(
            cast(float, getattr(self, "key_embed_mm")),
            scene.unit_settings.scale_length,
        )

    def _set_key_embed(self, value: float) -> None:
        scene = cast(bpy.types.Scene, self.id_data)
        self.key_embed_mm = value * scene.unit_settings.scale_length * 1000

    key_embed: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Root Overlap",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=_get_key_embed,
        set=_set_key_embed,
    )

    def _get_key_clearance(self) -> float:
        scene = cast(bpy.types.Scene, self.id_data)
        return mm_to_units(
            cast(float, getattr(self, "key_clearance_mm")),
            scene.unit_settings.scale_length,
        )

    def _set_key_clearance(self, value: float) -> None:
        scene = cast(bpy.types.Scene, self.id_data)
        self.key_clearance_mm = value * scene.unit_settings.scale_length * 1000

    key_clearance: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Clearance per Side",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=_get_key_clearance,
        set=_set_key_clearance,
    )

    def _get_key_depth_clearance(self) -> float:
        scene = cast(bpy.types.Scene, self.id_data)
        return mm_to_units(
            cast(float, getattr(self, "key_depth_clearance_mm")),
            scene.unit_settings.scale_length,
        )

    def _set_key_depth_clearance(self, value: float) -> None:
        scene = cast(bpy.types.Scene, self.id_data)
        self.key_depth_clearance_mm = value * scene.unit_settings.scale_length * 1000

    key_depth_clearance: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Tip Clearance",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=_get_key_depth_clearance,
        set=_set_key_depth_clearance,
    )

    key_active: PointerProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Selected Key",
        type=bpy.types.Object,
    )
    key_axis: EnumProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Direction",
        items=(("X", "X", "World X"), ("Y", "Y", "World Y"), ("Z", "Z", "World Z")),
        default="Z",
    )

    key_shape: EnumProperty(  # pyright: ignore[reportInvalidTypeForm]
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
    key_taper: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Tip Reduction",
        subtype="FACTOR",
        default=0.2,
        min=0.0,
        max=0.9,
    )

    def _get_key_taper_angle(self) -> float:
        width = cast(float, getattr(self, "key_width_mm"))
        height = cast(float, getattr(self, "key_height_mm"))
        taper = cast(float, getattr(self, "key_taper"))
        return atan(width * taper / (2 * height))

    def _set_key_taper_angle(self, value: float) -> None:
        width = cast(float, getattr(self, "key_width_mm"))
        height = cast(float, getattr(self, "key_height_mm"))
        self.key_taper = min(0.9, 2 * height * tan(value) / width)

    key_taper_angle: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
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
    key_angle: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Rotation",
        subtype="ANGLE",
        default=0.0,
    )
    key_align_normal: BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Perpendicular to Face",
        default=True,
        description="Align with the nearest face normal; disable to use the selected world axis",
    )
    key_flip: BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Flip Direction",
        default=False,
    )
    key_mate: PointerProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Socket Half",
        type=bpy.types.Object,
        poll=_mesh_object_poll,
    )
    key_preview_pin: PointerProperty(  # pyright: ignore[reportInvalidTypeForm]
        type=bpy.types.Object,
    )
    key_preview_socket: PointerProperty(  # pyright: ignore[reportInvalidTypeForm]
        type=bpy.types.Object,
    )
    key_preview_target: PointerProperty(  # pyright: ignore[reportInvalidTypeForm]
        type=bpy.types.Object,
    )
    key_preview_mate: PointerProperty(  # pyright: ignore[reportInvalidTypeForm]
        type=bpy.types.Object,
    )

    inherit_collection: PointerProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Collection",
        description="Collection whose meshes are inherited as a Boolean union",
        type=bpy.types.Collection,
    )

    boolean_operand: PointerProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Operand",
        description="Mesh object used by the Boolean modifier",
        type=bpy.types.Object,
        poll=_mesh_object_poll,
    )

    boolean_solver: EnumProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Solver",
        description="Method used to calculate the Boolean operation",
        items=_BOOLEAN_SOLVERS,
        default="EXACT",
    )

    # Retain the saved millimetre value for existing files and operators.
    surface_cut_thickness_mm: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Thickness (mm)",
        description="Surface Cut thickness in millimetres, regardless of scene units",
        default=MIN_SURFACE_CUT_THICKNESS_MM,
        min=MIN_SURFACE_CUT_THICKNESS_MM,
        precision=3,
    )

    def _get_surface_cut_thickness(self) -> float:
        scene = cast(bpy.types.Scene, self.id_data)
        return mm_to_units(
            cast(float, getattr(self, "surface_cut_thickness_mm")),
            scene.unit_settings.scale_length,
        )

    def _set_surface_cut_thickness(self, value: float) -> None:
        scene = cast(bpy.types.Scene, self.id_data)
        self.surface_cut_thickness_mm = value * scene.unit_settings.scale_length * 1000

    surface_cut_thickness: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Thickness",
        description="Surface Cut thickness in scene distance units",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=_get_surface_cut_thickness,
        set=_set_surface_cut_thickness,
    )

    surface_cut_margin_mm: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Boundary Extension (mm)",
        description=(
            "Extend the drawn cutting surface outward past its boundary by this "
            "many millimetres; 0 disables extension. Used when drawing a new surface"
        ),
        default=0.1,
        min=0.0,
        precision=3,
    )

    surface_cut_input_mode: EnumProperty(  # pyright: ignore[reportInvalidTypeForm]
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

    def _get_surface_cut_margin(self) -> float:
        scene = cast(bpy.types.Scene, self.id_data)
        return mm_to_units(
            cast(float, getattr(self, "surface_cut_margin_mm")),
            scene.unit_settings.scale_length,
        )

    def _set_surface_cut_margin(self, value: float) -> None:
        scene = cast(bpy.types.Scene, self.id_data)
        self.surface_cut_margin_mm = value * scene.unit_settings.scale_length * 1000

    # Keep saved millimetres compatible while the UI accepts scene distance units.
    surface_cut_margin: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Boundary Extension",
        description="Extend the cutting surface past its boundary; updates while drawing",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=_get_surface_cut_margin,
        set=_set_surface_cut_margin,
    )

    # Deliberately no ``unit="VOLUME"``, for the same reason as above: it
    # would make Blender render the value in the scene's unit settings, while
    # this add-on always reports volumes in millilitres.
    volume_ml: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Volume (mL)",
        description=(
            "Total volume of the meshes selected when Measure Volume was last "
            "used. It is a snapshot: later changes to the scene do not update it"
        ),
        default=0.0,
        min=0.0,
        precision=2,
    )

    volume_measured: BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Measured",
        description="Whether Volume (mL) holds the result of a measurement",
        default=False,
    )

    mixture_use_shared_density: BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Same Density for A and B",
        description="Use part A's density for both parts",
        default=True,
    )

    mixture_density_a_g_per_ml: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Density A (g/mL)",
        default=1.1,
        min=_MIN_DENSITY_G_PER_ML,
        soft_max=5.0,
        precision=3,
    )

    mixture_density_b_g_per_ml: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Density B (g/mL)",
        default=1.1,
        min=_MIN_DENSITY_G_PER_ML,
        soft_max=5.0,
        precision=3,
    )

    mixture_ratio_a: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Ratio A",
        description="Relative weight of part A",
        default=1.0,
        min=_MIN_MIXTURE_RATIO,
        soft_max=100.0,
        precision=3,
    )

    mixture_ratio_b: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Ratio B",
        description="Relative weight of part B",
        default=1.0,
        min=_MIN_MIXTURE_RATIO,
        soft_max=100.0,
        precision=3,
    )

    mixture_parts: CollectionProperty(  # pyright: ignore[reportInvalidTypeForm]
        type=SiliconeCastingMixturePart,
    )

    mixture_selection_anchor: IntProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Mixture Selection Anchor",
        default=-1,
        min=-1,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    mixture_active_index: IntProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Active Mixture Part",
        default=-1,
        min=-1,
        options={"HIDDEN", "SKIP_SAVE"},
        update=_select_active_mixture_part,
    )

    color_profiles: CollectionProperty(  # pyright: ignore[reportInvalidTypeForm]
        type=SiliconeCastingColorProfile,
    )

    color_profile_active_index: IntProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Active Color Profile",
        default=-1,
        min=-1,
        options={"HIDDEN"},
    )
