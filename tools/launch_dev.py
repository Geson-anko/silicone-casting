"""Startup script for ``just dev``: launch Blender with the add-on loaded so a
human can actually try the features by hand.

Run by ``blender --python tools/launch_dev.py`` *without* ``--background``,
so Blender continues into the GUI after this returns. ``just install`` has
already installed and enabled the extension by then, so all that is left
is starting the BlenderMCP server, which is there purely so an AI can look
at the same session and answer questions about it.

Nothing here touches the scene, the window layout, or the user's
preferences -- the point is a normal Blender that happens to have the
add-on in it. Nothing here may abort startup either: a missing BlenderMCP
install is reported and skipped.
"""

import os
import sys

import addon_utils
import bpy

#: Module name of our extension once installed into the user repository.
EXTENSION_MODULE = "bl_ext.user_default.silicone_casting"

#: Module name of the BlenderMCP add-on. It is a legacy single-file add-on,
#: so the module is just the installed file's stem -- `addon.py` by default,
#: since that is what the upstream repository ships.
MCP_ADDON_MODULE = os.environ.get("BLENDER_MCP_ADDON", "addon")

MCP_SETUP_URL = "https://github.com/ahujasid/blender-mcp"

#: The GUI is not up yet when this script runs, so the server start is
#: deferred by a timer rather than called inline.
SERVER_START_DELAY_SECONDS = 1.0


def log(message: str) -> None:
    """Print a tagged line that stands out in Blender's startup noise."""
    print(f"[just dev] {message}", file=sys.stderr)


def check_extension() -> None:
    """Report whether the add-on is loaded, so a failed install is obvious."""
    _enabled, loaded = addon_utils.check(EXTENSION_MODULE)
    if loaded:
        log(f"extension loaded: {EXTENSION_MODULE}")
        log("panel: 3D View sidebar (N) -> Silicone Casting")
    else:
        log(f"WARNING: {EXTENSION_MODULE} is not loaded -- run `just install` first")


def enable_mcp_addon() -> bool:
    """Enable the BlenderMCP add-on.

    Returns whether it is available.
    """
    _enabled, loaded = addon_utils.check(MCP_ADDON_MODULE)
    if not loaded:
        addon_utils.enable(MCP_ADDON_MODULE, default_set=False)

    # bpy.ops creates arbitrary namespaces on access, even for absent add-ons.
    if "start_server" in dir(bpy.ops.blendermcp):
        return True

    log(f"WARNING: BlenderMCP add-on '{MCP_ADDON_MODULE}' not found -- MCP disabled")
    log(f"         install addon.py from {MCP_SETUP_URL}")
    log("         (override the module name with BLENDER_MCP_ADDON=<name>)")
    return False


def start_mcp_server() -> None:
    """Start the BlenderMCP server.

    One-shot timer callback.
    """
    scene = bpy.context.scene
    if getattr(scene, "blendermcp_server_running", False):
        log(f"MCP server already running on port {scene.blendermcp_port}")
        return

    bpy.ops.blendermcp.start_server()
    log(f"MCP server listening on port {scene.blendermcp_port}")


def main() -> None:
    """Report the add-on state and bring up MCP, then hand over to the GUI."""
    check_extension()
    if enable_mcp_addon():
        bpy.app.timers.register(
            start_mcp_server, first_interval=SERVER_START_DELAY_SECONDS
        )


main()
