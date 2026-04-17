from copy import copy
from dataclasses import dataclass, field
from functools import partial, wraps
from os.path import expanduser, expandvars, realpath
from typing import Callable, Concatenate, ParamSpec, Self, TypeVar
from weakref import WeakSet

import more_itertools
import wcwidth


@dataclass(slots=True)
class Text:
    # TODO: poll file updates
    # ask if reload when changed from outside
    # os.stat(filename).st_mtime? watchdog?
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
            self.file_path = realpath(expandvars(expanduser(self.file_path)))
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.data = f.read()
            except FileNotFoundError as e:
                # TODO: create new file?
                # self.data = ""
                raise e
            except IsADirectoryError as e:
                raise e

    def _delete(self, begin: int, count: int) -> None:
        assert count >= 0
        assert 0 <= begin <= len(self.data)

        if not self.data or count == 0 or begin == len(self.data):
            return

        self.redo_stack = []
        self.undo_stack.append(Insert.fromDelete(begin, count, self.data))

        # delete
        self.data = self.data[:begin] + self.data[begin + count :]

    def _insert(self, position: int, text: str) -> None:
        assert 0 <= position <= len(self.data)
        if not text:
            return

        self.redo_stack = []
        self.undo_stack.append(Delete.fromInsert(position, text))

        # insert
        self.data = self.data[:position] + text + self.data[position:]

    def _apply(self, command: Delete | Insert) -> None:
        match command:
            case Delete(begin, end):
                self._delete(begin, end)
            case Insert(position, text):
                self._insert(position, text)
        for cursor in self.cursors:
            cursor.apply(command)

    def delete(self, begin: Cursor, end: Cursor, closed_open: bool = False) -> None:
        """
        closed interval [begin, end]
        closed-open interval [begin, end)
        """
        if not closed_open:
            end = copy(end)
            end.next()
        count = end.position - begin.position
        self._delete(begin.position, count)

    def insert(self, position: Cursor, text: str) -> None:
        self._insert(position.position, text)
        # self._apply(Insert(position.position, text))

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
        if self.file_path is None:
            return
        with open(self.file_path, "w") as file:
            file.write(self.data)

    def get_cursor(self) -> Cursor:
        """
        Get a new cursor and subscribe it to events sent from this Text
        """
        c = Cursor(self)
        self.cursors.add(c)
        return c

    def get_lines(self, begin: int, end: int) -> list[str]:
        return self.data.splitlines(keepends=True)[begin:end]


P = ParamSpec("P")
R = TypeVar("R")


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
        position (int): Zero-based cursor position in the text. This
            represents a position *between* characters, not a character
            itself. Valid values range from 0 to len(text), inclusive.
        text (Text): The associated Text instance.

    Invariants:
        - 0 <= position <= len(text)
    """

    text: Text  # back reference
    position: int = 0
    line: int = 0

    @staticmethod
    def update_line(
        func: Callable[Concatenate[Cursor, P], R],
    ) -> Callable[Concatenate[Cursor, P], R]:
        """
        Method decorator to update the line cache
        """

        @wraps(func)
        def wrapper(self: Cursor, *args: P.args, **kwargs: P.kwargs) -> R:
            prev_position = self.position
            result = func(self, *args, **kwargs)
            new_position = self.position

            if new_position > prev_position:
                num_lines = self.text.data[prev_position:new_position].count("\n")
                self.line += num_lines
            else:
                num_lines = self.text.data[new_position:prev_position].count("\n")
                self.line -= num_lines

            return result

        return wrapper

    @update_line
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

    def clone(self) -> Cursor:
        new = copy(self)
        self.text.cursors.add(new)
        return new

    @update_line
    def prev(self, n: int = 1) -> None:
        for _ in range(n):
            if self.position == 0:
                return
            self.position = wcwidth.grapheme_boundary_before(
                self.text.data, self.position
            )

    @update_line
    def next(self, n: int = 1) -> None:
        for _ in range(n):
            if self.position == len(self.text.data):
                return
            increment = len(next(wcwidth.iter_graphemes(self.text.data, self.position)))
            self.position += increment

    @update_line
    def to_prev_line(self, n: int = 1) -> None:
        for _ in range(n):
            self.position = self.text.data.rfind("\n", 0, self.position)
            if self.position == -1:
                self.position = 0
                return
        self.to_beginning_of_line()

    @update_line
    def to_next_line(self, n: int = 1) -> None:
        for _ in range(n):
            self.position = self.text.data.find("\n", self.position)
            if self.position == -1:
                self.position = len(self.text.data)
                self.to_beginning_of_line()
                return
        if self.position < len(self.text.data):
            self.position += 1

    @update_line
    def to_beginning_of_line(self) -> None:
        self.position = self.text.data.rfind("\n", 0, self.position)
        if self.position == -1:
            self.position = 0
        elif self.position < len(self.text.data):
            self.position += 1

    @update_line
    def to_end_of_line(self) -> None:
        self.position = self.text.data.find("\n", self.position)
        if self.position == -1:
            self.position = len(self.text.data) - 1

    @update_line
    def get_line_idx(self) -> int:
        """
        0-based index
        """
        # return len(self.text.data[: self.position + 1].splitlines()) - 1
        # return self.text.data[:self.position].count("\n")
        return self.line

    '''
    def get_line_column_idx(self) -> tuple[int, int]:
        """
        0-based index
        """
        aux = self.text.data[: self.position + 1].splitlines()
        line = len(aux) - 1
        column = len(aux[-1]) - 1
        return line, column
    '''

    def to_line(self, line: int) -> None:
        self.position = sum(
            map(lambda l: len(l), self.text.data.splitlines(keepends=True)[:line])
        )
        self.line = line


@dataclass
class Delete:
    begin: int
    count: int

    @classmethod
    def fromInsert(cls, position: int, text: str) -> Self:
        return cls(position, len(text))


@dataclass
class Insert:
    position: int
    text: str

    @classmethod
    def fromDelete(cls, begin: int, count: int, original_text: str) -> Self:
        return cls(begin, original_text[begin : begin + count])


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
