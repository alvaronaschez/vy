from dataclasses import dataclass, field
from functools import partial
from typing import Self
from weakref import WeakSet

import more_itertools
import wcwidth


@dataclass(slots=True)
class Text:
    file_path: str | None = None
    data: str = field(init=False)
    undo_stack: list[Delete | Insert] = field(init=False, default_factory=lambda: [])
    redo_stack: list[Delete | Insert] = field(init=False, default_factory=lambda: [])
    cursors: WeakSet[Cursor] = field(
        default_factory=lambda: WeakSet()
    )  # subscribers (observer pattern)

    def __post_init__(self) -> None:
        if not self.file_path:
            self.file_path = None
            self.data = ""
        else:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.data = f.read()
            except FileNotFoundError as e:
                # TODO: create new file?
                # self.data = ""
                raise e
            except IsADirectoryError as e:
                raise e

    def _delete(self, begin: int, end: int) -> None:
        self.redo_stack = []
        self.undo_stack.append(Insert.fromDelete(begin, end, self.data))
        last_char_len = len(next(wcwidth.iter_graphemes(self.data, end)))
        self.data = self.data[:begin] + self.data[end + last_char_len :]

    def _insert(self, position: int, text: str) -> None:
        if not text:
            return
        self.redo_stack = []
        self.undo_stack.append(Delete.fromInsert(position, text))
        self.data = self.data[:position] + text + self.data[position:]

    def _apply(self, command: Delete | Insert) -> None:
        match command:
            case Delete(begin, end):
                self._delete(begin, end)
            case Insert(position, text):
                self._insert(position, text)
        for cursor in self.cursors:
            cursor.apply(command)

    def delete(self, begin: Cursor, end: Cursor) -> None:
        self._delete(begin.position, end.position)

    def insert(self, position: Cursor, text: str) -> None:
        self._insert(position.position, text)

    def undo(self) -> None:
        if not self.undo_stack:
            return
        command = self.undo_stack.pop()
        self._apply(command)

        # change must go to the redo_stack instead of to the undo_stack
        self.undo_stack.pop()
        self.redo_stack.append(command)

    def redo(self) -> None:
        if not self.redo_stack:
            return
        command = self.redo_stack.pop()
        self._apply(command)

    def save(self) -> None:
        # TODO
        pass

    def get_cursor(self) -> Cursor:
        """
        Get a new cursor and subscribe it to events sent from this Text
        """
        c = Cursor(0, self)
        self.cursors.add(c)
        return c


@dataclass(eq=False)
class Cursor:
    """
    Represents a position within a Text object that stays consistent
    as the text is modified.

    A Cursor is tied to a specific Text instance and is updated when
    edit commands are applied.

    Instances should not be created directly; use `Text.get_cursor()`
    so the Text can track and update it.

    Attributes:
        position (int): Zero-based index in the text.
        text (Text): The associated Text instance.

    Invariants:
        - The cursor position is always a valid index in the text.
    """

    position: int
    text: Text  # back reference

    def apply(self, command: Delete | Insert) -> None:
        """
        Update the cursor position in response to a text edit.

        Args:
            command: The edit operation applied to the text.

        Behavior:
            - Delete(begin, end):
                * Before range: unchanged
                * Inside range: moves to begin
                * After range: shifts left by deleted length

            - Insert(position, text):
                * Before insertion: unchanged
                * At or after insertion: shifts right by inserted length
        """
        match command:
            case Delete(begin, end):
                if self.position < begin:
                    return
                elif self.position < end:
                    self.position = begin
                else:
                    self.position -= end - begin + 1
            case Insert(position, text):
                if self.position < position:
                    return
                else:
                    self.position += len(text)


@dataclass
class Delete:
    begin: int
    end: int

    @classmethod
    def fromInsert(cls, position: int, text: str) -> Self:
        return cls(position, position + len(text) - 1)


@dataclass
class Insert:
    position: int
    text: str

    @classmethod
    def fromDelete(cls, begin: int, end: int, original_text: str) -> Self:
        last_char_len = len(next(wcwidth.iter_graphemes(original_text, end)))
        return cls(begin, original_text[begin : end + last_char_len])


# almost as fast as get_eol, without external dependencies
def newline_indexes(s: str):
    i = -1
    while True:
        i = s.find("\n", i + 1)
        if i == -1:
            break
        yield i


# fastest
get_eol = partial(more_itertools.iter_index, value="\n")


def line_length(text: str) -> int:
    return text.count("\n")
