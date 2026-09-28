"""Check export filenames before overwrite warnings using native GUI events."""

import tempfile
import traceback
from pathlib import Path

import bpy


def _steps():
    assert bpy.app.use_event_simulate
    window = bpy.context.window
    original_scene = window.scene
    scene = bpy.data.scenes.new("Export filename checks")
    window.scene = scene
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    last_directory_key = "_silicone_casting_last_stl_export_directory"
    manager = bpy.context.window_manager
    last_directory = manager.get(last_directory_key)
    mesh = bpy.data.meshes.new("Export filename check")
    obj = bpy.data.objects.new("existing-recipe", mesh)
    scene.collection.objects.link(obj)
    obj.select_set(True)
    window.view_layer.objects.active = obj
    try:
        with tempfile.TemporaryDirectory() as directory:
            manager[last_directory_key] = directory
            for operator, extension in (
                (bpy.ops.silicone_casting.export_stl, ".stl"),
                (bpy.ops.silicone_casting.export_recipes, ".json"),
            ):
                path = Path(directory) / f"existing-recipe{extension}"
                path.write_bytes(b"Existing file must survive filename editing")
                with bpy.context.temp_override(window=window, area=area):
                    assert operator("INVOKE_DEFAULT", filepath=str(path)) == {
                        "RUNNING_MODAL"
                    }
                yield
                browser = next(w for w in manager.windows if w != window)
                browser_area = browser.screen.areas[0]
                space = browser_area.spaces.active
                region = next(r for r in browser_area.regions if r.type == "EXECUTE")
                x = round(region.x + region.width * 0.25)
                y = round(region.y + region.height * 0.5)
                browser.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
                yield
                browser.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
                browser.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x, y=y)
                browser.event_simulate(type="A", value="PRESS", ctrl=True)
                browser.event_simulate(type="A", value="RELEASE", ctrl=True)
                for letter in "existing-recipe":
                    browser.event_simulate(type="A", value="PRESS", unicode=letter)
                    browser.event_simulate(type="A", value="RELEASE")
                browser.event_simulate(type="RET", value="PRESS")
                browser.event_simulate(type="RET", value="RELEASE")
                yield
                # Blender checks this visible filename for its overwrite warning.
                assert space.params.filename == path.name, space.params.filename
                assert space.active_operator.filepath == str(path)
                assert space.active_operator.check_existing
                assert (
                    path.read_bytes() == b"Existing file must survive filename editing"
                )
                assert not path.with_suffix("").exists()
                with bpy.context.temp_override(window=browser, area=browser_area):
                    bpy.ops.file.cancel()
                yield
    finally:
        for browser in list(manager.windows):
            for browser_area in browser.screen.areas:
                if browser_area.type == "FILE_BROWSER":
                    with bpy.context.temp_override(window=browser, area=browser_area):
                        bpy.ops.file.cancel()
                    break
        window.scene = original_scene
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        bpy.data.scenes.remove(scene)
        if last_directory is None:
            del manager[last_directory_key]
        else:
            manager[last_directory_key] = last_directory


def main():
    steps = _steps()
    result = Path(tempfile.gettempdir()) / "silcast-export-gui-result.txt"
    result.write_text("RUNNING\n")

    def tick():
        try:
            next(steps)
        except StopIteration:
            result.write_text("PASS\n")
            return None
        except Exception:
            error = traceback.format_exc()
            print(error)
            result.write_text(error)
            return None
        return 0.3

    bpy.app.timers.register(tick, first_interval=0.5)


if __name__ == "__main__":
    main()
