"""Branch an object or collection's evaluated shape through Boolean."""

from typing import TYPE_CHECKING, Final, override

import bpy

from ..properties.settings import scene_settings
from ._operator import OperatorReturn

_OBJECT_SUFFIX: Final = ".inherit"
_MODIFIER_NAME: Final = "Inherit Shape"

type _Source = bpy.types.Object | bpy.types.Collection


def _active_mesh(context: bpy.types.Context) -> bpy.types.Object | None:
    """Return the active mesh object, if this context has one."""
    active = context.active_object
    return active if active is not None and active.type == "MESH" else None


def _resolve_source(context: bpy.types.Context, use_collection: bool) -> _Source:
    """Return the object or collection whose shape is inherited.

    Raises:
        ValueError: With a user-facing message when the chosen source cannot
            be inherited.
    """
    if not use_collection:
        active = _active_mesh(context)
        if active is None:
            raise ValueError("Select an active mesh in Object Mode")
        return active

    collection = scene_settings(context).inherit_collection
    objects = () if collection is None else tuple(collection.all_objects)
    if collection is None or not any(obj.type == "MESH" for obj in objects):
        raise ValueError("Choose a collection containing meshes")
    if any(obj.type != "MESH" for obj in objects):
        raise ValueError("The collection must contain only mesh objects")
    if collection == context.scene.collection:
        raise ValueError("Choose a collection below the scene root")
    return collection


def _create_inherited_object(
    context: bpy.types.Context, source: _Source
) -> bpy.types.Object:
    """Link an empty mesh whose Boolean union reproduces *source*."""
    name = f"{source.name}{_OBJECT_SUFFIX}"
    inherited = bpy.data.objects.new(name, bpy.data.meshes.new(name))

    modifier = inherited.modifiers.new(_MODIFIER_NAME, "BOOLEAN")
    assert isinstance(modifier, bpy.types.BooleanModifier)
    modifier.operation = "UNION"
    modifier.solver = "EXACT"

    if isinstance(source, bpy.types.Collection):
        # Linked beside the operand, not inside it: inside, the result would
        # feed its own Boolean and form a dependency cycle.
        for parent in _parent_collections(context, source):
            parent.objects.link(inherited)
        modifier.operand_type = "COLLECTION"
        modifier.collection = source
    else:
        for collection in source.users_collection:
            collection.objects.link(inherited)
        inherited.matrix_world = source.matrix_world.copy()
        modifier.operand_type = "OBJECT"
        modifier.object = source
    return inherited


def _parent_collections(
    context: bpy.types.Context, collection: bpy.types.Collection
) -> list[bpy.types.Collection]:
    """Return the scene collections that directly contain *collection*.

    Falls back to the scene root for a collection not linked into the
    scene.
    """
    root = context.scene.collection
    parents = [
        parent
        for parent in (root, *root.children_recursive)
        if collection.name in parent.children
    ]
    return parents or [root]


def _select_only(context: bpy.types.Context, obj: bpy.types.Object) -> None:
    """Make *obj* the sole selected and active object."""
    for selected in context.selected_objects or ():
        selected.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


class SILCAST_OT_inherit_shape(bpy.types.Operator):
    """Create an empty mesh referencing an object or collection union."""

    bl_idname = "silicone_casting.inherit_shape"
    bl_label = "Inherit Shape"
    bl_description = (
        "Create an empty mesh that references a mesh or collection through a Boolean "
        "modifier"
    )
    bl_options = {"REGISTER", "UNDO"}

    if TYPE_CHECKING:
        use_collection: bool
    else:
        use_collection: bpy.props.BoolProperty(
            name="Use Collection",
            description="Inherit all meshes in the selected collection",
            default=False,
            options={"HIDDEN", "SKIP_SAVE"},
        )

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and (
            _active_mesh(context) is not None
            or scene_settings(context).inherit_collection is not None
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        try:
            source = _resolve_source(context, self.use_collection)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        inherited = _create_inherited_object(context, source)
        _select_only(context, inherited)

        self.report({"INFO"}, f"Inherited {source.name!r} as {inherited.name!r}")
        return {"FINISHED"}
