"""Management of the Solidify modifier this addon puts on a surface.

Everything here uses the plain data API: no ``bpy.ops``. Baking the
modifier down is done through depsgraph evaluation instead of
``object.modifier_apply``, which keeps it callable from a background
Blender and from the PyPI ``bpy`` wheel, where there is no window
manager context to override.
"""

from typing import Final

import bpy

# Name of the Solidify modifier this addon owns. It is written into user
# .blend files, so it is part of the public API: renaming it would orphan
# the modifiers already sitting in saved scenes.
MODIFIER_NAME: Final = "Silicone Casting Solidify"

# Smallest thickness the UI accepts, in millimetres (1 um). Exposed for
# `properties/settings.py` to use as the FloatProperty minimum. The functions
# below take Blender units and therefore never compare against it.
MIN_THICKNESS_MM: Final = 1e-3


def find_solidify(obj: bpy.types.Object) -> bpy.types.SolidifyModifier | None:
    """Return the addon-owned Solidify modifier on *obj*, if any.

    Args:
        obj: Object to inspect. It need not be a mesh object.

    Returns:
        The modifier named :data:`MODIFIER_NAME`, or ``None`` when *obj*
        has no such modifier or the name is taken by a modifier of some
        other type.
    """
    # Modifier names are unique per object, so the first match is the only
    # one. isinstance narrows for pyright and rejects a same-named
    # modifier of another type in one step.
    for modifier in obj.modifiers:
        if modifier.name == MODIFIER_NAME and isinstance(
            modifier, bpy.types.SolidifyModifier
        ):
            return modifier
    return None


def ensure_solidify(
    obj: bpy.types.Object,
    thickness: float,
    *,
    flip: bool = False,
    even_thickness: bool = True,
) -> bpy.types.SolidifyModifier:
    """Make sure *obj* carries the addon's Solidify modifier and configure it.

    An existing modifier is reused and updated in place, so calling this
    repeatedly never stacks up duplicates and never moves the modifier
    within the stack. Only the three properties below are touched;
    everything else keeps Blender's defaults.

    Args:
        obj: Target object. Must be a mesh object -- the caller is
            responsible for that.
        thickness: Wall thickness in **Blender units**. Converting from
            millimetres is the caller's job (see
            :func:`~silicone_casting.core.units.mm_to_units`). The value
            is not validated; the UI's property range is what bounds it.
        flip: Grow the wall inwards instead of outwards.
        even_thickness: Compensate at corners to keep the requested wall
            thickness.

    Returns:
        The modifier that was added or updated.
    """
    modifier = find_solidify(obj)
    if modifier is None:
        added = obj.modifiers.new(MODIFIER_NAME, "SOLIDIFY")
        # `modifiers.new` is typed as returning the Modifier base class;
        # the "SOLIDIFY" type argument is what makes this hold.
        assert isinstance(added, bpy.types.SolidifyModifier)
        modifier = added

    modifier.thickness = thickness
    modifier.offset = -1.0 if flip else 1.0
    modifier.use_even_offset = even_thickness
    return modifier


def apply_solidify(obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> None:
    """Bake the addon's Solidify modifier into the mesh of *obj*.

    Only the addon-owned modifier is baked: every other modifier is
    hidden for the duration of the evaluation and restored afterwards,
    matching what Blender means by applying one particular modifier.
    The evaluated result replaces ``obj.data``, and the previous mesh
    datablock is removed so its name can be handed to the new one.

    Args:
        obj: Target object. Must be a mesh object and must be linked into
            the view layer, since the result comes from evaluating it.
        depsgraph: Dependency graph to evaluate against, typically
            ``context.evaluated_depsgraph_get()``.

    Raises:
        ValueError: If *obj* has no addon-owned Solidify modifier, or if
            its mesh is shared with another object. Both are checked
            before anything is modified.
    """
    modifier = find_solidify(obj)
    if modifier is None:
        raise ValueError(f"{obj.name!r} has no {MODIFIER_NAME!r} modifier to apply")

    old_mesh = obj.data
    # Guaranteed by the caller; the assert is what narrows Object.data.
    assert isinstance(old_mesh, bpy.types.Mesh)
    if old_mesh.users > 1:
        raise ValueError(
            f"the mesh of {obj.name!r} is shared with other objects; "
            "make it single-user before applying"
        )

    # Identity comparison on RNA wrappers is unreliable, so the modifier
    # to keep enabled is singled out by its name.
    hidden = [
        (other, other.show_viewport)
        for other in obj.modifiers
        if other.name != MODIFIER_NAME
    ]
    for other, _ in hidden:
        other.show_viewport = False
    try:
        depsgraph.update()
        new_mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    finally:
        for other, was_visible in hidden:
            other.show_viewport = was_visible

    obj.modifiers.remove(modifier)
    name = old_mesh.name
    obj.data = new_mesh
    # Removing the old datablock first frees the name, so the rename does
    # not end up with a ".001" suffix.
    bpy.data.meshes.remove(old_mesh)
    new_mesh.name = name
