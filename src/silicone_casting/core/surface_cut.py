"""A Geometry Nodes modifier that cuts a mesh with a thin surface."""

from typing import Final, Protocol, cast

import bpy

SURFACE_CUT_MODIFIER_NAME: Final = "Surface Cut"
MIN_SURFACE_CUT_THICKNESS_MM: Final = 0.001

# The cap copied from the source surface has duplicate boundary vertices with
# the extruded sides. Weld those exact pairs without collapsing the two faces
# of the thin cutter into each other.
_MERGE_DISTANCE_FACTOR: Final = 0.49


class _EnumItem(Protocol):
    name: str
    description: str


class _EnumItems(Protocol):
    def __getitem__(self, index: int) -> _EnumItem: ...


class _EnumDefinition(Protocol):
    enum_items: _EnumItems


def _input(node: bpy.types.Node, key: str | int) -> bpy.types.NodeSocket:
    """Return a node input through the non-optional base API."""
    return node.inputs[key]


def _output(node: bpy.types.Node, name: str) -> bpy.types.NodeSocket:
    """Return a node output through the non-optional base API."""
    return node.outputs[name]


def create_surface_cut(
    target: bpy.types.Object,
    surface: bpy.types.Object,
    thickness: float,
    *,
    minimum_thickness: float,
) -> bpy.types.NodesModifier:
    """Add one integrated Surface Cut modifier to *target*.

    A dedicated Geometry Nodes group turns *surface* into a closed cutter by
    extruding it along its normals, then subtracts that cutter from the input
    geometry. The modifier exposes the cutting surface, even-thickness mode,
    and Manifold/Exact solver choice. The surface object itself is only
    referenced and remains unchanged.

    Args:
        target: Mesh object that receives the modifier.
        surface: Mesh object used as the live cutting surface.
        thickness: Positive cutter thickness in Blender units.
        minimum_thickness: Lower limit exposed by the modifier, in Blender units.

    Returns:
        The newly added Geometry Nodes modifier.
    """
    node_group = cast(
        bpy.types.GeometryNodeTree,
        bpy.data.node_groups.new(SURFACE_CUT_MODIFIER_NAME, "GeometryNodeTree"),
    )
    node_group.is_modifier = True
    interface = node_group.interface
    assert interface is not None
    interface.new_socket(
        name="Geometry",
        in_out="INPUT",
        socket_type="NodeSocketGeometry",  # pyright: ignore[reportArgumentType]
    )
    surface_socket = cast(
        bpy.types.NodeTreeInterfaceSocketObject,
        interface.new_socket(
            name="Cutting Surface",
            in_out="INPUT",
            socket_type="NodeSocketObject",  # pyright: ignore[reportArgumentType]
        ),
    )
    surface_socket.description = "Mesh surface to solidify and subtract"
    surface_socket.default_value = surface
    thickness_socket = cast(
        bpy.types.NodeTreeInterfaceSocketFloat,
        interface.new_socket(
            name="Thickness",
            in_out="INPUT",
            socket_type="NodeSocketFloat",  # pyright: ignore[reportArgumentType]
        ),
    )
    thickness_socket.description = "Thickness of the solidified cutting surface"
    thickness_socket.subtype = "DISTANCE"  # pyright: ignore[reportAttributeAccessIssue]
    thickness_socket.min_value = minimum_thickness
    thickness_socket.default_value = thickness
    even_thickness_socket = cast(
        bpy.types.NodeTreeInterfaceSocketBool,
        interface.new_socket(
            name="Even Thickness",
            in_out="INPUT",
            socket_type="NodeSocketBool",  # pyright: ignore[reportArgumentType]
        ),
    )
    even_thickness_socket.description = (
        "Compensate at corners to keep the requested cutter thickness"
    )
    even_thickness_socket.default_value = False

    solver_switch = cast(
        bpy.types.GeometryNodeMenuSwitch,
        node_group.nodes.new("GeometryNodeMenuSwitch"),
    )
    solver_switch.data_type = "GEOMETRY"
    enum_definition = cast(_EnumDefinition, solver_switch.enum_definition)
    solver_items = enum_definition.enum_items
    solver_items[0].name = "Manifold"
    solver_items[0].description = "Fast solver for manifold meshes"
    solver_items[1].name = "Exact"
    solver_items[1].description = "Slower solver for overlapping geometry"
    solver_socket = cast(
        bpy.types.NodeTreeInterfaceSocketMenu,
        interface.new_socket(
            name="Solver",
            in_out="INPUT",
            socket_type="NodeSocketMenu",  # pyright: ignore[reportArgumentType]
        ),
    )
    solver_socket.from_socket(solver_switch, _input(solver_switch, "Menu"))
    solver_socket.default_value = "Manifold"
    interface.new_socket(
        name="Geometry",
        in_out="OUTPUT",
        socket_type="NodeSocketGeometry",  # pyright: ignore[reportArgumentType]
    )

    group_input = node_group.nodes.new("NodeGroupInput")
    group_output = node_group.nodes.new("NodeGroupOutput")
    object_info = cast(
        bpy.types.GeometryNodeObjectInfo,
        node_group.nodes.new("GeometryNodeObjectInfo"),
    )
    object_info.transform_space = "RELATIVE"

    # Resolve warped quads once before making both cutter caps. Independent
    # tessellation of offset caps can choose different diagonals and cross.
    triangulate = node_group.nodes.new("GeometryNodeTriangulate")

    normal = node_group.nodes.new("GeometryNodeInputNormal")
    uneven_extrude = cast(
        bpy.types.GeometryNodeExtrudeMesh,
        node_group.nodes.new("GeometryNodeExtrudeMesh"),
    )
    uneven_extrude.mode = "FACES"
    individual = cast(
        bpy.types.NodeSocketBool,
        _input(uneven_extrude, "Individual"),
    )
    individual.default_value = False
    even_extrude = cast(
        bpy.types.GeometryNodeExtrudeMesh,
        node_group.nodes.new("GeometryNodeExtrudeMesh"),
    )
    even_extrude.mode = "FACES"
    even_individual = cast(
        bpy.types.NodeSocketBool,
        _input(even_extrude, "Individual"),
    )
    even_individual.default_value = False
    even_extrude_scale = cast(
        bpy.types.NodeSocketFloat,
        _input(even_extrude, "Offset Scale"),
    )
    even_extrude_scale.default_value = 0.0
    captured_fields = cast(
        bpy.types.GeometryNodeCaptureAttribute,
        node_group.nodes.new("GeometryNodeCaptureAttribute"),
    )
    captured_fields.domain = "POINT"
    captured_fields.capture_items.clear()
    captured_fields.capture_items.new("VECTOR", "Point Normal")
    captured_fields.capture_items.new("FLOAT", "Even Factor")

    negative_thickness = cast(
        bpy.types.ShaderNodeMath,
        node_group.nodes.new("ShaderNodeMath"),
    )
    negative_thickness.operation = "MULTIPLY"
    negative_factor = cast(bpy.types.NodeSocketFloat, _input(negative_thickness, 1))
    negative_factor.default_value = -1.0

    face_normal = cast(
        bpy.types.GeometryNodeFieldOnDomain,
        node_group.nodes.new("GeometryNodeFieldOnDomain"),
    )
    face_normal.data_type = "FLOAT_VECTOR"
    face_normal.domain = "FACE"
    normal_dot = cast(
        bpy.types.ShaderNodeVectorMath,
        node_group.nodes.new("ShaderNodeVectorMath"),
    )
    normal_dot.operation = "DOT_PRODUCT"
    absolute_dot = cast(
        bpy.types.ShaderNodeMath,
        node_group.nodes.new("ShaderNodeMath"),
    )
    absolute_dot.operation = "ABSOLUTE"
    reciprocal_dot = cast(
        bpy.types.ShaderNodeMath,
        node_group.nodes.new("ShaderNodeMath"),
    )
    reciprocal_dot.operation = "DIVIDE"
    numerator = cast(bpy.types.NodeSocketFloat, _input(reciprocal_dot, 0))
    numerator.default_value = 1.0
    even_offset = cast(
        bpy.types.ShaderNodeVectorMath,
        node_group.nodes.new("ShaderNodeVectorMath"),
    )
    even_offset.operation = "SCALE"
    even_displacement = cast(
        bpy.types.ShaderNodeVectorMath,
        node_group.nodes.new("ShaderNodeVectorMath"),
    )
    even_displacement.operation = "SCALE"
    set_even_position = node_group.nodes.new("GeometryNodeSetPosition")
    solidify_switch = cast(
        bpy.types.GeometryNodeSwitch,
        node_group.nodes.new("GeometryNodeSwitch"),
    )
    solidify_switch.input_type = "GEOMETRY"

    flip = node_group.nodes.new("GeometryNodeFlipFaces")
    join = node_group.nodes.new("GeometryNodeJoinGeometry")
    merge = node_group.nodes.new("GeometryNodeMergeByDistance")
    merge_scale = cast(
        bpy.types.ShaderNodeMath,
        node_group.nodes.new("ShaderNodeMath"),
    )
    merge_scale.operation = "MULTIPLY"
    merge_factor = cast(bpy.types.NodeSocketFloat, _input(merge_scale, 1))
    merge_factor.default_value = _MERGE_DISTANCE_FACTOR

    manifold_boolean = cast(
        bpy.types.GeometryNodeMeshBoolean,
        node_group.nodes.new("GeometryNodeMeshBoolean"),
    )
    manifold_boolean.operation = "DIFFERENCE"
    manifold_boolean.solver = "MANIFOLD"
    exact_boolean = cast(
        bpy.types.GeometryNodeMeshBoolean,
        node_group.nodes.new("GeometryNodeMeshBoolean"),
    )
    exact_boolean.operation = "DIFFERENCE"
    exact_boolean.solver = "EXACT"

    links = node_group.links
    links.new(
        _output(group_input, "Cutting Surface"),
        _input(object_info, "Object"),
    )
    links.new(
        _output(object_info, "Geometry"),
        _input(triangulate, "Mesh"),
    )
    links.new(
        _output(triangulate, "Mesh"),
        _input(captured_fields, "Geometry"),
    )
    links.new(_output(normal, "Normal"), _input(captured_fields, "Point Normal"))
    links.new(
        _output(captured_fields, "Geometry"),
        _input(uneven_extrude, "Mesh"),
    )
    links.new(
        _output(captured_fields, "Geometry"),
        _input(even_extrude, "Mesh"),
    )
    links.new(
        _output(group_input, "Thickness"),
        _input(negative_thickness, 0),
    )
    links.new(_output(normal, "Normal"), _input(face_normal, "Value"))
    links.new(_output(normal, "Normal"), _input(normal_dot, 0))
    links.new(_output(face_normal, "Value"), _input(normal_dot, 1))
    links.new(_output(normal_dot, "Value"), _input(absolute_dot, 0))
    links.new(_output(absolute_dot, "Value"), _input(reciprocal_dot, 1))
    links.new(
        _output(reciprocal_dot, "Value"),
        _input(captured_fields, "Even Factor"),
    )
    links.new(
        _output(captured_fields, "Point Normal"),
        _input(even_offset, "Vector"),
    )
    links.new(
        _output(captured_fields, "Even Factor"),
        _input(even_offset, "Scale"),
    )
    links.new(
        _output(even_offset, "Vector"),
        _input(even_displacement, "Vector"),
    )
    links.new(
        _output(negative_thickness, "Value"),
        _input(even_displacement, "Scale"),
    )
    links.new(
        _output(even_extrude, "Mesh"),
        _input(set_even_position, "Geometry"),
    )
    links.new(
        _output(even_extrude, "Top"),
        _input(set_even_position, "Selection"),
    )
    links.new(
        _output(even_displacement, "Vector"),
        _input(set_even_position, "Offset"),
    )
    links.new(
        _output(group_input, "Even Thickness"),
        _input(solidify_switch, "Switch"),
    )
    links.new(
        _output(uneven_extrude, "Mesh"),
        _input(solidify_switch, "False"),
    )
    links.new(
        _output(set_even_position, "Geometry"),
        _input(solidify_switch, "True"),
    )
    links.new(
        _output(normal, "Normal"),
        _input(uneven_extrude, "Offset"),
    )
    links.new(
        _output(negative_thickness, "Value"),
        _input(uneven_extrude, "Offset Scale"),
    )
    links.new(_output(solidify_switch, "Output"), _input(flip, "Mesh"))
    links.new(_output(triangulate, "Mesh"), _input(join, "Geometry"))
    links.new(_output(flip, "Mesh"), _input(join, "Geometry"))
    links.new(_output(join, "Geometry"), _input(merge, "Geometry"))
    links.new(_output(group_input, "Thickness"), _input(merge_scale, 0))
    links.new(_output(merge_scale, "Value"), _input(merge, "Distance"))
    for boolean in (manifold_boolean, exact_boolean):
        links.new(_output(group_input, "Geometry"), _input(boolean, "Mesh 1"))
        links.new(_output(merge, "Geometry"), _input(boolean, "Mesh 2"))
    links.new(
        _output(manifold_boolean, "Mesh"),
        _input(solver_switch, "Manifold"),
    )
    links.new(
        _output(exact_boolean, "Mesh"),
        _input(solver_switch, "Exact"),
    )
    links.new(_output(group_input, "Solver"), _input(solver_switch, "Menu"))
    links.new(_output(solver_switch, "Output"), _input(group_output, "Geometry"))

    modifier = cast(
        bpy.types.NodesModifier,
        target.modifiers.new(SURFACE_CUT_MODIFIER_NAME, "NODES"),
    )
    modifier.node_group = node_group
    properties = getattr(modifier, "properties", None)
    if properties is None:
        modifier[surface_socket.identifier] = surface
    else:
        modifier_input = getattr(properties.inputs, surface_socket.identifier)
        modifier_input.value = surface
    return modifier
