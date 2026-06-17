from copy import copy
from dataclasses import dataclass
from functools import wraps
from os.path import expanduser, expandvars, realpath
from typing import Callable, Concatenate, ParamSpec, Self, TypeVar, cast

import wcwidth


class Text:
    # TODO: poll file updates
    # ask if reload when changed from outside
    # os.stat(filename).st_mtime? watchdog?

    __slots__ = ("file_path", "data", "undo_stack", "redo_stack")

    def __init__(self, file_path: str | None = None) -> None:
        self.file_path: str | None = None
        self.data: str = ""
        self.undo_stack: list[Delete | Insert] = []
        self.redo_stack: list[Delete | Insert] = []

        if file_path:
            self.file_path = realpath(expandvars(expanduser(file_path)))
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.data = f.read()
            except FileNotFoundError as e:
                # TODO: create new file?
                # self.data = ""
                raise e
            except IsADirectoryError as e:
                raise e

    def _delete_raw(self, begin: int, count: int) -> None:
        assert count >= 0
        assert 0 <= begin <= len(self.data)

        if not self.data or count == 0 or begin == len(self.data):
            return

        self.data = self.data[:begin] + self.data[begin + count :]

    def _insert_raw(self, position: int, text: str) -> None:
        assert 0 <= position <= len(self.data)
        if not text:
            return

        self.data = self.data[:position] + text + self.data[position:]

    def _inverse(self, command: Delete | Insert) -> Delete | Insert:
        match command:
            case Delete(begin, count):
                return Insert.fromDelete(begin, count, self.data)
            case Insert(position, text):
                return Delete.fromInsert(position, text)

    def _apply_raw(self, command: Delete | Insert) -> None:
        match command:
            case Delete(begin, count):
                self._delete_raw(begin, count)
            case Insert(position, text):
                self._insert_raw(position, text)

    def _move_after(self, cursor: Cursor, command: Delete | Insert) -> None:
        match command:
            case Delete(begin, _):
                cursor.to_position(begin)
            case Insert(position, text):
                cursor.to_position(position + len(text))

    def delete(self, begin: Cursor, end: Cursor, closed_open: bool = True) -> None:
        """
        closed interval [begin, end]
        closed-open interval [begin, end)
        """
        if not closed_open:
            end = copy(end)
            end.next()
        count = end.position - begin.position
        if count <= 0:
            return

        command = Delete(begin.position, count)
        self.undo_stack.append(self._inverse(command))
        self.redo_stack.clear()
        self._delete_raw(begin.position, count)
        self._move_after(begin, command)

    def insert(self, cursor: Cursor, text: str) -> None:
        if text:
            command = Insert(cursor.position, text)
            self.undo_stack.append(self._inverse(command))
            self.redo_stack.clear()
            self._insert_raw(cursor.position, text)
            self._move_after(cursor, command)

    def undo(self, cursor: Cursor) -> None:
        if not self.undo_stack:
            return
        command = self.undo_stack.pop()
        inverse = self._inverse(command)

        self._apply_raw(command)
        self.redo_stack.append(inverse)
        self._move_after(cursor, command)

    def redo(self, cursor: Cursor) -> None:
        if not self.redo_stack:
            return
        command = self.redo_stack.pop()
        inverse = self._inverse(command)

        self._apply_raw(command)
        self.undo_stack.append(inverse)
        self._move_after(cursor, command)

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
        return c

    def get_lines(self, begin: Cursor, end: Cursor) -> list[str]:
        return self.get_range(begin, end).splitlines(keepends=True)

    def line_count(self) -> int:
        return self.data.count("\n") + 1

    def get_range(self, begin: Cursor, end: Cursor) -> str:
        return self.data[begin.position : end.position]


P = ParamSpec("P")
R = TypeVar("R")


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

    __slots__ = ("text", "position", "line")

    def __init__(self, text: Text, position: int = 0, line: int = 0):
        self.text = text
        self.position = position
        self.line = line

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

        # return wrapper
        # avoid mypy error
        return cast(Callable[Concatenate["Cursor", P], R], wrapper)

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
            case Delete(begin, count):
                end = begin + count
                if self.position < begin:
                    return
                elif self.position < end:
                    self.position = begin
                else:
                    self.position -= count
            case Insert(position, text):
                if self.position < position:
                    return
                else:
                    self.position += len(text)

    def clone(self) -> Cursor:
        new = copy(self)
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
    def to_position(self, position: int) -> None:
        assert 0 <= position <= len(self.text.data)
        self.position = position

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
            # elif self.position < len(self.text.data):
            else:
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
            # self.position = len(self.text.data) - 1
            self.position = len(self.text.data)

    def get_line_idx(self) -> int:
        """
        0-based index
        """
        # return len(self.text.data[: self.position + 1].splitlines()) - 1
        # return self.text.data[:self.position].count("\n")
        return self.line

    def get_column(self, tab_size: int) -> int:
        # TODO: use cache like with lines
        start = self.text.data.rfind("\n", 0, self.position) + 1
        end = self.position

        column = 0

        for grapheme in wcwidth.iter_graphemes(self.text.data, start, end):
            if grapheme == "\t":
                width = tab_size - column % tab_size
            else:
                width = max(0, wcwidth.width(grapheme))

            column += width

        return column

    def to_column(self, n: int, tab_size: int) -> None:
        """Go to the nth column or to eol if n > eol"""
        assert n >= 0

        start = self.text.data.rfind("\n", 0, self.position) + 1
        end = self.text.data.find("\n", self.position)
        if end == -1:
            end = len(self.text.data) - 1

        self.position = start
        column = 0

        for grapheme in wcwidth.iter_graphemes(self.text.data, start, end):
            if grapheme == "\t":
                width = tab_size - column % tab_size
            else:
                width = max(0, wcwidth.width(grapheme))

            column += width

            if column > n:
                return

            self.position += len(grapheme)

            if column == n:
                return

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

    def is_eol(self) -> bool:
        return self.text.data[self.position] == "\n"

    def is_eof(self) -> bool:
        return self.position == len(self.text.data)


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


"""
# almost as fast as get_eol, without external dependencies
def newline_indexes(s: str):
    i = -1
    while True:
        i = s.find("\n", i + 1)
        if i == -1:
            break
        yield i


# fastest
import more_itertools
from functools import partial
get_eol = partial(more_itertools.iter_index, value="\n")
"""
