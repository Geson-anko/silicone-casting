"""A Geometry Nodes modifier that cuts a mesh with a thin surface."""

from typing import Final, cast

import bpy

SURFACE_CUT_MODIFIER_NAME: Final = "Surface Cut"
MIN_SURFACE_CUT_THICKNESS_MM: Final = 0.001

# The cap copied from the source surface has duplicate boundary vertices with
# the extruded sides. Weld those exact pairs without collapsing the two faces
# of the thin cutter into each other.
_MERGE_DISTANCE_FACTOR: Final = 0.49


def _input(node: bpy.types.Node, key: str | int) -> bpy.types.NodeSocket:
    """Return a node input through the non-optional base API."""
    return node.inputs[key]


def _output(node: bpy.types.Node, name: str) -> bpy.types.NodeSocket:
    """Return a node output through the non-optional base API."""
    return node.outputs[name]


class _SurfaceCutBuilder:
    """Build the interface, cutter and solver branches of one node group."""

    def __init__(
        self,
        surface: bpy.types.Object,
        thickness: float,
        minimum_thickness: float,
    ) -> None:
        self._surface = surface
        self._group = cast(
            bpy.types.GeometryNodeTree,
            bpy.data.node_groups.new(SURFACE_CUT_MODIFIER_NAME, "GeometryNodeTree"),
        )
        self._group.is_modifier = True
        self._solver_switch = self._create_solver_switch()
        self._surface_socket = self._create_interface(
            surface, thickness, minimum_thickness
        )
        self._group_input = self._group.nodes.new("NodeGroupInput")
        self._group_output = self._group.nodes.new("NodeGroupOutput")

    def _create_solver_switch(self) -> bpy.types.GeometryNodeMenuSwitch:
        switch = cast(
            bpy.types.GeometryNodeMenuSwitch,
            self._group.nodes.new("GeometryNodeMenuSwitch"),
        )
        switch.data_type = "GEOMETRY"
        items = switch.enum_items
        items[0].name = "Manifold"
        items[0].description = "Fast solver for manifold meshes"
        items[1].name = "Exact"
        items[1].description = "Slower solver for overlapping geometry"
        return switch

    def _create_interface(
        self,
        surface: bpy.types.Object,
        thickness: float,
        minimum_thickness: float,
    ) -> bpy.types.NodeTreeInterfaceSocketObject:
        interface = self._group.interface
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
        even_socket = cast(
            bpy.types.NodeTreeInterfaceSocketBool,
            interface.new_socket(
                name="Even Thickness",
                in_out="INPUT",
                socket_type="NodeSocketBool",  # pyright: ignore[reportArgumentType]
            ),
        )
        even_socket.description = (
            "Compensate at corners to keep the requested cutter thickness"
        )
        even_socket.default_value = False
        solver_socket = cast(
            bpy.types.NodeTreeInterfaceSocketMenu,
            interface.new_socket(
                name="Solver",
                in_out="INPUT",
                socket_type="NodeSocketMenu",  # pyright: ignore[reportArgumentType]
            ),
        )
        solver_socket.from_socket(
            self._solver_switch, _input(self._solver_switch, "Menu")
        )
        solver_socket.default_value = "Manifold"
        interface.new_socket(
            name="Geometry",
            in_out="OUTPUT",
            socket_type="NodeSocketGeometry",  # pyright: ignore[reportArgumentType]
        )
        return surface_socket

    def _source_geometry(self) -> bpy.types.NodeSocket:
        object_info = cast(
            bpy.types.GeometryNodeObjectInfo,
            self._group.nodes.new("GeometryNodeObjectInfo"),
        )
        object_info.transform_space = "RELATIVE"
        # Resolve warped quads once before making both cutter caps. Independent
        # tessellation of offset caps can choose different diagonals and cross.
        triangulate = self._group.nodes.new("GeometryNodeTriangulate")
        self._group.links.new(
            _output(self._group_input, "Cutting Surface"), _input(object_info, "Object")
        )
        self._group.links.new(
            _output(object_info, "Geometry"), _input(triangulate, "Mesh")
        )
        return _output(triangulate, "Mesh")

    def _even_factor(self, normal: bpy.types.NodeSocket) -> bpy.types.NodeSocket:
        """Compensate the point normal by its alignment with each face."""
        face_normal = cast(
            bpy.types.GeometryNodeFieldOnDomain,
            self._group.nodes.new("GeometryNodeFieldOnDomain"),
        )
        face_normal.data_type = "FLOAT_VECTOR"
        face_normal.domain = "FACE"
        dot = cast(
            bpy.types.ShaderNodeVectorMath,
            self._group.nodes.new("ShaderNodeVectorMath"),
        )
        dot.operation = "DOT_PRODUCT"
        absolute = cast(
            bpy.types.ShaderNodeMath, self._group.nodes.new("ShaderNodeMath")
        )
        absolute.operation = "ABSOLUTE"
        reciprocal = cast(
            bpy.types.ShaderNodeMath, self._group.nodes.new("ShaderNodeMath")
        )
        reciprocal.operation = "DIVIDE"
        cast(bpy.types.NodeSocketFloat, _input(reciprocal, 0)).default_value = 1.0
        links = self._group.links
        links.new(normal, _input(face_normal, "Value"))
        links.new(normal, _input(dot, 0))
        links.new(_output(face_normal, "Value"), _input(dot, 1))
        links.new(_output(dot, "Value"), _input(absolute, 0))
        links.new(_output(absolute, "Value"), _input(reciprocal, 1))
        return _output(reciprocal, "Value")

    def _capture_surface(
        self, geometry: bpy.types.NodeSocket, normal: bpy.types.NodeSocket
    ) -> bpy.types.GeometryNodeCaptureAttribute:
        captured = cast(
            bpy.types.GeometryNodeCaptureAttribute,
            self._group.nodes.new("GeometryNodeCaptureAttribute"),
        )
        captured.domain = "POINT"
        captured.capture_items.clear()
        captured.capture_items.new("VECTOR", "Point Normal")
        captured.capture_items.new("FLOAT", "Even Factor")
        links = self._group.links
        links.new(geometry, _input(captured, "Geometry"))
        links.new(normal, _input(captured, "Point Normal"))
        links.new(self._even_factor(normal), _input(captured, "Even Factor"))
        return captured

    def _extrude(
        self, geometry: bpy.types.NodeSocket
    ) -> bpy.types.GeometryNodeExtrudeMesh:
        extrude = cast(
            bpy.types.GeometryNodeExtrudeMesh,
            self._group.nodes.new("GeometryNodeExtrudeMesh"),
        )
        extrude.mode = "FACES"
        cast(
            bpy.types.NodeSocketBool, _input(extrude, "Individual")
        ).default_value = False
        self._group.links.new(geometry, _input(extrude, "Mesh"))
        return extrude

    def _even_extrusion(
        self,
        captured: bpy.types.GeometryNodeCaptureAttribute,
        thickness: bpy.types.NodeSocket,
    ) -> bpy.types.NodeSocket:
        extrude = self._extrude(_output(captured, "Geometry"))
        cast(
            bpy.types.NodeSocketFloat, _input(extrude, "Offset Scale")
        ).default_value = 0.0
        offset = cast(
            bpy.types.ShaderNodeVectorMath,
            self._group.nodes.new("ShaderNodeVectorMath"),
        )
        offset.operation = "SCALE"
        displacement = cast(
            bpy.types.ShaderNodeVectorMath,
            self._group.nodes.new("ShaderNodeVectorMath"),
        )
        displacement.operation = "SCALE"
        position = self._group.nodes.new("GeometryNodeSetPosition")
        links = self._group.links
        links.new(_output(captured, "Point Normal"), _input(offset, "Vector"))
        links.new(_output(captured, "Even Factor"), _input(offset, "Scale"))
        links.new(_output(offset, "Vector"), _input(displacement, "Vector"))
        links.new(thickness, _input(displacement, "Scale"))
        links.new(_output(extrude, "Mesh"), _input(position, "Geometry"))
        links.new(_output(extrude, "Top"), _input(position, "Selection"))
        links.new(_output(displacement, "Vector"), _input(position, "Offset"))
        return _output(position, "Geometry")

    def _extruded_surface(self, geometry: bpy.types.NodeSocket) -> bpy.types.NodeSocket:
        normal = _output(self._group.nodes.new("GeometryNodeInputNormal"), "Normal")
        captured = self._capture_surface(geometry, normal)
        negative = cast(
            bpy.types.ShaderNodeMath, self._group.nodes.new("ShaderNodeMath")
        )
        negative.operation = "MULTIPLY"
        cast(bpy.types.NodeSocketFloat, _input(negative, 1)).default_value = -1.0
        thickness = _output(negative, "Value")
        uneven = self._extrude(_output(captured, "Geometry"))
        even = self._even_extrusion(captured, thickness)
        switch = cast(
            bpy.types.GeometryNodeSwitch,
            self._group.nodes.new("GeometryNodeSwitch"),
        )
        switch.input_type = "GEOMETRY"
        links = self._group.links
        links.new(_output(self._group_input, "Thickness"), _input(negative, 0))
        links.new(normal, _input(uneven, "Offset"))
        links.new(thickness, _input(uneven, "Offset Scale"))
        links.new(
            _output(self._group_input, "Even Thickness"), _input(switch, "Switch")
        )
        links.new(_output(uneven, "Mesh"), _input(switch, "False"))
        links.new(even, _input(switch, "True"))
        return _output(switch, "Output")

    def _closed_cutter(self) -> bpy.types.NodeSocket:
        geometry = self._source_geometry()
        extruded = self._extruded_surface(geometry)
        flip = self._group.nodes.new("GeometryNodeFlipFaces")
        join = self._group.nodes.new("GeometryNodeJoinGeometry")
        merge = self._group.nodes.new("GeometryNodeMergeByDistance")
        scale = cast(bpy.types.ShaderNodeMath, self._group.nodes.new("ShaderNodeMath"))
        scale.operation = "MULTIPLY"
        cast(
            bpy.types.NodeSocketFloat, _input(scale, 1)
        ).default_value = _MERGE_DISTANCE_FACTOR
        links = self._group.links
        links.new(extruded, _input(flip, "Mesh"))
        links.new(geometry, _input(join, "Geometry"))
        links.new(_output(flip, "Mesh"), _input(join, "Geometry"))
        links.new(_output(join, "Geometry"), _input(merge, "Geometry"))
        links.new(_output(self._group_input, "Thickness"), _input(scale, 0))
        links.new(_output(scale, "Value"), _input(merge, "Distance"))
        return _output(merge, "Geometry")

    def _connect_solvers(self, cutter: bpy.types.NodeSocket) -> None:
        manifold = cast(
            bpy.types.GeometryNodeMeshBoolean,
            self._group.nodes.new("GeometryNodeMeshBoolean"),
        )
        manifold.operation = "DIFFERENCE"
        manifold.solver = "MANIFOLD"
        exact = cast(
            bpy.types.GeometryNodeMeshBoolean,
            self._group.nodes.new("GeometryNodeMeshBoolean"),
        )
        exact.operation = "DIFFERENCE"
        exact.solver = "EXACT"
        links = self._group.links
        for boolean in (manifold, exact):
            links.new(_output(self._group_input, "Geometry"), _input(boolean, "Mesh 1"))
            links.new(cutter, _input(boolean, "Mesh 2"))
        links.new(_output(manifold, "Mesh"), _input(self._solver_switch, "Manifold"))
        links.new(_output(exact, "Mesh"), _input(self._solver_switch, "Exact"))
        links.new(
            _output(self._group_input, "Solver"), _input(self._solver_switch, "Menu")
        )
        links.new(
            _output(self._solver_switch, "Output"),
            _input(self._group_output, "Geometry"),
        )

    def add_modifier(self, target: bpy.types.Object) -> bpy.types.NodesModifier:
        """Finish the graph before attaching it to the target."""
        self._connect_solvers(self._closed_cutter())
        modifier = cast(
            bpy.types.NodesModifier,
            target.modifiers.new(SURFACE_CUT_MODIFIER_NAME, "NODES"),
        )
        modifier.node_group = self._group
        properties = getattr(modifier, "properties", None)
        if properties is None:
            modifier[self._surface_socket.identifier] = self._surface
        else:
            modifier_input = getattr(properties.inputs, self._surface_socket.identifier)
            modifier_input.value = self._surface
        return modifier


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
    return _SurfaceCutBuilder(surface, thickness, minimum_thickness).add_modifier(
        target
    )
