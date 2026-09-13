"""Apply calculated silicone appearance to a Blender material."""

from typing import cast

import bpy

from ..core.color_mixing import SimulatedSiliconeAppearance

MATERIAL_PREFIX = "Silicone Mix - "
_SHADER_NODE_NAME = "Silicone Casting Shader"


def configure_material(
    material: bpy.types.Material,
    profile_name: str,
    appearance: SimulatedSiliconeAppearance,
) -> None:
    """Build or update the add-on-owned Principled material from calculated
    values."""
    material.name = f"{MATERIAL_PREFIX}{profile_name}"
    material.use_nodes = True
    node_tree = material.node_tree
    assert node_tree is not None

    shader = node_tree.nodes.get(_SHADER_NODE_NAME)
    if shader is None or shader.bl_idname != "ShaderNodeBsdfPrincipled":
        node_tree.nodes.clear()
        output = node_tree.nodes.new("ShaderNodeOutputMaterial")
        shader = node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        shader.name = _SHADER_NODE_NAME
        node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    rgba = (*appearance.color, 1.0)
    material.diffuse_color = rgba  # pyright: ignore[reportAttributeAccessIssue]
    color_socket = cast(bpy.types.NodeSocketColor, shader.inputs["Base Color"])
    color_socket.default_value = rgba  # pyright: ignore[reportAttributeAccessIssue]
    cast(
        bpy.types.NodeSocketFloatFactor, shader.inputs["Transmission Weight"]
    ).default_value = appearance.transparency
    cast(
        bpy.types.NodeSocketFloatFactor, shader.inputs["Subsurface Weight"]
    ).default_value = 0.0
    cast(bpy.types.NodeSocketFloat, shader.inputs["IOR"]).default_value = 1.41
    cast(
        bpy.types.NodeSocketFloatFactor, shader.inputs["Roughness"]
    ).default_value = 0.2
    cast(bpy.types.NodeSocketFloatFactor, shader.inputs["Alpha"]).default_value = 1.0
