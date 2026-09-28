"""Apply calculated silicone appearance to a Blender material."""

from typing import Final, cast

import bpy

from ..core.color_mixing import SimulatedSiliconeAppearance

MATERIAL_PREFIX: Final = "Silicone Mix - "
_SHADER_NODE_NAME: Final = "Silicone Casting Shader"

# Fixed shading inputs from memory/specs/color_mixing_simulator.md; the
# simulator only varies base color and transparency.
_SILICONE_IOR: Final = 1.41
_SILICONE_ROUGHNESS: Final = 0.2


def _ensure_principled_shader(node_tree: bpy.types.NodeTree) -> bpy.types.Node:
    """Return the add-on's shader node, rebuilding the tree when missing."""
    shader = node_tree.nodes.get(_SHADER_NODE_NAME)
    if shader is not None and shader.bl_idname == "ShaderNodeBsdfPrincipled":
        return shader
    node_tree.nodes.clear()
    output = node_tree.nodes.new("ShaderNodeOutputMaterial")
    shader = node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    shader.name = _SHADER_NODE_NAME
    node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return shader


def _set_float_input(shader: bpy.types.Node, name: str, value: float) -> None:
    """Set one float or factor socket's default value."""
    cast(bpy.types.NodeSocketFloat, shader.inputs[name]).default_value = value


def configure_material(
    material: bpy.types.Material,
    profile_name: str,
    appearance: SimulatedSiliconeAppearance,
) -> None:
    """Build or update the add-on-owned Principled material from an appearance.

    Args:
        material: Material to rename and configure in place.
        profile_name: Color profile name used in the material name.
        appearance: Calculated color and transparency to display.
    """
    material.name = f"{MATERIAL_PREFIX}{profile_name}"
    material.use_nodes = True
    node_tree = material.node_tree
    assert node_tree is not None
    shader = _ensure_principled_shader(node_tree)

    rgba = (*appearance.color, 1.0)
    material.diffuse_color = rgba  # pyright: ignore[reportAttributeAccessIssue]
    color_socket = cast(bpy.types.NodeSocketColor, shader.inputs["Base Color"])
    color_socket.default_value = rgba  # pyright: ignore[reportAttributeAccessIssue]
    _set_float_input(shader, "Transmission Weight", appearance.transparency)
    _set_float_input(shader, "Subsurface Weight", 0.0)
    _set_float_input(shader, "IOR", _SILICONE_IOR)
    _set_float_input(shader, "Roughness", _SILICONE_ROUGHNESS)
    _set_float_input(shader, "Alpha", 1.0)
