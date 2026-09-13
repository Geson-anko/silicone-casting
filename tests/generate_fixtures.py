"""Regenerate the golden meshes under ``tests/fixtures/``.

Run via ``just fixtures``. Only run this when a geometry change is
*intended* -- the whole point of the fixtures is that they do not move on
their own.
"""

from _helpers import FIXTURES_DIR


def main() -> None:
    """Write every golden fixture, reporting each path as it is written."""
    FIXTURES_DIR.mkdir(exist_ok=True)
    # No golden fixtures yet. Add generation steps here as geometry that this
    # add-on computes itself lands; `MeshData.from_mesh(mesh).write_obj(path)` from
    # `_helpers` is the writer.
    print("no golden fixtures to write")


if __name__ == "__main__":
    main()
