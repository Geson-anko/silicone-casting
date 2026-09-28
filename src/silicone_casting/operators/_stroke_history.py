"""Undo and redo of whole drawing states inside a modal operator."""

from collections.abc import Callable


class StrokeHistory[State]:
    """Snapshots taken before each edit, walked back and forth by Ctrl-Z."""

    def __init__(self, snapshot: Callable[[State], State]) -> None:
        self._snapshot = snapshot
        self._undo: list[State] = []
        self._redo: list[State] = []

    def remember(self, state: State) -> None:
        """Record ``state`` before an edit and drop the redo branch."""
        self._undo.append(self._snapshot(state))
        self._redo.clear()

    def step(self, state: State, *, redo: bool) -> State | None:
        """Swap ``state`` for the neighboring snapshot.

        Args:
            state: The current state, kept so the step can be reversed.
            redo: Step forward instead of back.

        Returns:
            The state to continue from, or None when there is nothing to
            undo or redo (``state`` is then not recorded).
        """
        source, destination = (
            (self._redo, self._undo) if redo else (self._undo, self._redo)
        )
        if not source:
            return None
        destination.append(self._snapshot(state))
        return source.pop()
