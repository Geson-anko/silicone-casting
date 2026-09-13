"""Branch an object or collection's evaluated shape through Boolean."""

from typing import Final, cast, override

import bpy

from ._operator import OperatorReturn

_OBJECT_SUFFIX: Final = ".inherit"
_MODIFIER_NAME: Final = "Inherit Shape"


def _active_mesh(context: bpy.types.Context) -> bpy.types.Object | None:
    """Return the active mesh object, if this context has one."""
    active = context.active_object
    return active if active is not None and active.type == "MESH" else None


class SILCAST_OT_inherit_shape(bpy.types.Operator):
    """Create an empty mesh referencing an object or collection union."""

    bl_idname = "silicone_casting.inherit_shape"
    bl_label = "Inherit Shape"
    bl_description = (
        "Create an empty mesh that references a mesh or collection through a Boolean "
        "modifier"
    )
    bl_options = {"REGISTER", "UNDO"}

    use_collection: bpy.props.BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Use Collection",
        description="Inherit all meshes in the selected collection",
        default=False,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        props = context.scene.silicone_casting
        return context.mode == "OBJECT" and (
            _active_mesh(context) is not None or props.inherit_collection is not None
        )

    def _source(
        self, context: bpy.types.Context
    ) -> bpy.types.Object | bpy.types.Collection | None:
        """Resolve the chosen operand and report invalid collection
        contents."""
        props = context.scene.silicone_casting
        use_collection = cast(
            bool,
            self.use_collection,  # pyright: ignore[reportUnknownMemberType]
        )
        source: bpy.types.Object | bpy.types.Collection | None = (
            props.inherit_collection if use_collection else _active_mesh(context)
        )
        if use_collection:
            if not isinstance(source, bpy.types.Collection) or not any(
                obj.type == "MESH" for obj in source.all_objects
            ):
                self.report({"ERROR"}, "Choose a collection containing meshes")
                return None
            if any(obj.type != "MESH" for obj in source.all_objects):
                self.report({"ERROR"}, "The collection must contain only mesh objects")
                return None
            if source == context.scene.collection:
                self.report({"ERROR"}, "Choose a collection below the scene root")
                return None
        if source is None:
            self.report({"ERROR"}, "Select an active mesh in Object Mode")
        return source

    def _create_inherited_object(
        self,
        context: bpy.types.Context,
        source: bpy.types.Object | bpy.types.Collection,
    ) -> bpy.types.Object:
        """Link an empty mesh outside its operand and configure its union."""
        name = f"{source.name}{_OBJECT_SUFFIX}"
        mesh = bpy.data.meshes.new(name)
        inherited = bpy.data.objects.new(name, mesh)
        if isinstance(source, bpy.types.Collection):
            # Keep the result outside its operand to avoid a dependency cycle.
            context.scene.collection.objects.link(inherited)
        else:
            context.collection.objects.link(inherited)
            inherited.matrix_world = source.matrix_world.copy()

        modifier = inherited.modifiers.new(_MODIFIER_NAME, "BOOLEAN")
        assert isinstance(modifier, bpy.types.BooleanModifier)
        modifier.operation = "UNION"
        modifier.solver = "EXACT"
        if isinstance(source, bpy.types.Collection):
            modifier.operand_type = "COLLECTION"
            modifier.collection = source
        else:
            modifier.operand_type = "OBJECT"
            modifier.object = source
        return inherited

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        source = self._source(context)
        if source is None:
            return {"CANCELLED"}
        inherited = self._create_inherited_object(context, source)
        for selected in context.selected_objects or ():
            selected.select_set(False)
        inherited.select_set(True)
        context.view_layer.objects.active = inherited

        self.report({"INFO"}, f"Inherited {source.name!r} as {inherited.name!r}")
        return {"FINISHED"}
