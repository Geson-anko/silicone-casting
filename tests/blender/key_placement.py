"""Native GUI gesture regression for the installed extension.

Run Blender with ``--enable-event-simulate --python tests/blender/key_placement.py``.
The extension must already be enabled. This creates a separate test scene,
leaves existing scenes intact, and keeps Blender open. Inspect ``status``,
``checks`` and ``error`` on ``sys.modules["silcast_key_gui_test"]`` for results.
"""

import sys
import traceback
from types import ModuleType

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector

_state = ModuleType("silcast_key_gui_test")
_state.status = "RUNNING"
_state.checks = []
_state.error = ""
sys.modules[_state.__name__] = _state


def _check(condition: bool, description: str) -> None:
    assert condition, description
    _state.checks.append(description)
    print(f"[key GUI] PASS: {description}", flush=True)


def _run():
    window = bpy.context.window
    assert window is not None, "Run in a GUI window, without --background"
    # Dismiss the startup splash before enabling the placement tool.
    window.event_simulate(type="ESC", value="PRESS")
    window.event_simulate(type="ESC", value="RELEASE")
    yield
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    space = area.spaces.active
    assert isinstance(space, bpy.types.SpaceView3D)
    view = space.region_3d
    assert view is not None
    assert bpy.context.preferences.edit.use_global_undo, "Enable Global Undo"
    key_models = next(
        module
        for name, module in tuple(sys.modules.items())
        if name.endswith(".operators.key_models") and hasattr(module, "KeyPair")
    )
    scene = bpy.data.scenes.new("Registration Key GUI Regression")
    _state.scene_name = scene.name
    window.scene = scene
    scene.unit_settings.scale_length = 0.001
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.primitive_cube_add(size=20, location=(0, 0, -10))
        male = bpy.context.object
        male.name = "GUI test male"
        bpy.ops.mesh.primitive_cube_add(size=20, location=(0, 0, 10))
        female = bpy.context.object
        female.name = "GUI test female"
        female.hide_set(True)
        male.select_set(True)
        window.view_layer.objects.active = male
        props = scene.silicone_casting
        props.key_mate = female
        props.key_shape = "CYLINDER"
        props.key_width_mm = 4
        props.key_length_mm = 6
        props.key_height_mm = 3
        props.key_embed_mm = 1
        props.key_clearance_mm = 0.2
        props.key_depth_clearance_mm = 0.4
        props.key_taper = 0.2
        props.key_align_normal = True
        props.key_flip = False
        props.key_angle = 0
        view.view_perspective = "ORTHO"
        view.view_rotation = Quaternion((1, 0, 0, 0))
        view.view_location = (0, 0, 0)
        view.view_distance = 35
        bpy.ops.silicone_casting.start_key_placement()
        # Only the fixture receives an explicit baseline. Every subsequent
        # undo entry must come from a real user event and the operator itself.
        bpy.ops.ed.undo_push(message="Registration key GUI fixture")
    area.tag_redraw()
    yield

    def pixels(point):
        pixel = location_3d_to_region_2d(region, view, Vector(point))
        assert pixel is not None, "Test point must be visible"
        assert 0 < pixel.x < region.width and 0 < pixel.y < region.height
        # Region offsets and projection results are already physical pixels.
        return round(region.x + pixel.x), round(region.y + pixel.y)

    def mouse(point, event_type, value="NOTHING"):
        x, y = pixels(point)
        window.event_simulate(type=event_type, value=value, x=x, y=y)

    def click(point):
        mouse(point, "MOUSEMOVE")
        mouse(point, "LEFTMOUSE", "PRESS")
        mouse(point, "LEFTMOUSE", "RELEASE")

    def shortcut(operator):
        x, y = pixels((0, 0, 0))
        modifiers = {"ctrl": True, "shift": operator == "ed.redo"}
        window.event_simulate(type="Z", value="PRESS", x=x, y=y, **modifiers)
        window.event_simulate(type="Z", value="RELEASE", x=x, y=y, **modifiers)

    def pins():
        # Undo replaces RNA datablocks: resolve the current scene and helpers
        # afresh instead of retaining object references across native undo.
        return [
            obj
            for obj in window.scene.objects
            if key_models.KeyPair.from_pin(obj) is not None
        ]

    def has_pin(point):
        return any(
            (pin.matrix_world.translation - Vector(point)).length < 0.08
            for pin in pins()
        )

    first = (-4, -3, 0)
    second = (4, 3, 0)
    moved = (-4, 3, 0)
    click(first)
    yield
    _check(len(pins()) == 1 and has_pin(first), "first click adds one key")
    click(second)
    yield
    _check(len(pins()) == 2 and has_pin(second), "second click adds one more key")
    shortcut("ed.undo")
    yield
    _check(len(pins()) == 1 and has_pin(first), "one Undo removes only the second key")
    shortcut("ed.redo")
    yield
    _check(len(pins()) == 2 and has_pin(second), "Redo restores the second key")

    mouse(first, "MOUSEMOVE")
    mouse(first, "LEFTMOUSE", "PRESS")
    yield
    mouse(moved, "MOUSEMOVE")
    yield
    mouse(moved, "LEFTMOUSE", "RELEASE")
    yield
    _check(
        len(pins()) == 2 and has_pin(moved) and not has_pin(first),
        "drag moves an existing key without adding a pair",
    )
    shortcut("ed.undo")
    yield
    _check(
        len(pins()) == 2 and has_pin(first), "one Undo restores the pre-drag position"
    )
    shortcut("ed.redo")
    yield
    _check(len(pins()) == 2 and has_pin(moved), "Redo restores the dragged position")

    click(second)
    yield
    active = window.scene.silicone_casting.key_active
    _check(
        active is not None
        and (active.matrix_world.translation - Vector(second)).length < 0.08,
        "click selects the existing key",
    )
    x, y = pixels(second)
    window.event_simulate(type="DEL", value="PRESS", x=x, y=y)
    window.event_simulate(type="DEL", value="RELEASE", x=x, y=y)
    yield
    _check(len(pins()) == 1 and has_pin(moved), "Delete removes only the selected pair")
    shortcut("ed.undo")
    yield
    _check(len(pins()) == 2 and has_pin(second), "Undo restores the deleted pair")


_steps = _run()


def _tick():
    try:
        next(_steps)
    except StopIteration:
        _state.status = "PASSED"
        print(f"[key GUI] PASSED: {len(_state.checks)} checks", flush=True)
        return None
    except Exception:
        _state.status = "FAILED"
        _state.error = traceback.format_exc()
        print(f"[key GUI] FAILED\n{_state.error}", flush=True)
        return None
    return 0.3


if __name__ == "__main__":
    bpy.app.timers.register(_tick, first_interval=1.0)
