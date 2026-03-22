# from __future__ import annotations  # python < 3.14

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable, Self, NamedTuple, Any
from functools import partial
import curses
# import sys

import wcwidth


def expand_tabs(s: str, tab_size: int) -> str:
    result = []
    column = 0
    for grapheme in wcwidth.iter_graphemes(s):
        if grapheme == "\t":
            spaces = tab_size - (column % tab_size)
            result.append(spaces * " ")
            column += spaces
        else:
            result.append(grapheme)
            column += wcwidth.width(grapheme)

    return "".join(result)


def wrap(s: str, width: int, tabsize: int) -> list[str]:
    result: list[str] = []
    aux: list[str] = []
    column = 0
    s = expand_tabs(s, tabsize)
    for grapheme in wcwidth.iter_graphemes(s):
        if column + wcwidth.width(grapheme) > width:
            result.append("".join(aux))
            aux = [grapheme]
            column = wcwidth.width(grapheme)
        else:
            aux.append(grapheme)
            column += wcwidth.width(grapheme)
    result.append("".join(aux))
    return result


@dataclass
class Cursor:
    y: int = 0
    x: int = 0

    def __lt__(self, other: Self) -> bool:
        return (self.y, self.x) < (other.y, other.x)


class BookMark(NamedTuple):
    line: int
    subline: int


class ViewPortSize(NamedTuple):
    height: int
    width: int


@dataclass
class ViewPort:
    height: int
    width: int
    cursor: Cursor
    lines: list[str]
    positions: list[BookMark]


type ReadKeyCallback = Callable[[], Key | str]
type PrintCallback = Callable[[ViewPort], None]
type GetViewPortSizeCallback = Callable[[], ViewPortSize]  # (height, width)


@dataclass(slots=True)
class Vy:
    _read_key: ReadKeyCallback
    _print: PrintCallback
    _get_view_port_size: GetViewPortSizeCallback

    file_path: Path | None = None
    buffer: list[str] = field(default_factory=lambda: list(str()))
    cursor: Cursor = field(default_factory=Cursor)
    scroll_offset: int = 0
    x_goal: int = 0
    view_port: ViewPort | None = None
    quit: bool = False

    class Config:
        TAB_SIZE = 8

    def __init__(
        self: Self,
        read_key: ReadKeyCallback,
        get_view_port_size: GetViewPortSizeCallback,
        print_: PrintCallback,
        file_path: str | None = None,
    ) -> None:
        self._read_key = read_key
        self._print = print_
        self._get_view_port_size = get_view_port_size

        if file_path:
            self.file_path = Path(file_path)
            with open(self.file_path, "r") as f:
                # lines = f.readlines() # this one adds '\n' to the end of each line
                lines = f.read().splitlines()
            self.buffer = lines
        else:
            self.file_path = None
            self.buffer = [""]

        self.cursor = Cursor()
        self.scroll_offset = 0
        self.x_goal = 0
        self.view_port = None
        self.quit = False

    def cursor_down(self) -> None:
        self.cursor.y = min(self.cursor.y + 1, len(self.buffer) - 1)
        self.cursor.x = min(self.cursor.x, len(self.buffer[self.cursor.y]))

    def cursor_up(self) -> None:
        self.cursor.y = max(self.cursor.y - 1, 0)
        self.cursor.x = min(self.cursor.x, len(self.buffer[self.cursor.y]))

    def cursor_left(self) -> None:
        if self.cursor.x == 0:
            return
        self.cursor.x = wcwidth.grapheme_boundary_before(
            self.buffer[self.cursor.y], self.cursor.x
        )

    def cursor_right(self) -> None:
        if self.cursor.x == len(self.buffer[self.cursor.y]):
            return
        increment = len(
            next(wcwidth.iter_graphemes(self.buffer[self.cursor.y], self.cursor.x))
        )
        self.cursor.x += increment

    def cursor_to_view_port(
        self, c: Cursor, bookmarks: list[BookMark], width: int
    ) -> Cursor | None:
        # if the cursor is not in the view port return None
        if c.y < bookmarks[0].line or c.y > bookmarks[-1].line:
            return None

        if c.x == len(self.buffer[c.y]):
            # we append an space here so we can go past eol
            # on the screen every line has at least one space
            to_wrap = self.buffer[c.y] + " "
        else:  # c.x < len(self.buffer[c.y]
            to_wrap = self.buffer[c.y][: c.x + 1]

        wrapped = wrap(to_wrap, width, tabsize=self.Config.TAB_SIZE)
        line, subline = c.y, len(wrapped) - 1
        columns = wcwidth.width(wrapped[-1])
        # columns > 0 as we always insert one space at the end of each line on the vp
        x = columns - 1

        for i, b in enumerate(bookmarks):
            if line == b.line and subline == b.subline:
                return Cursor(i, x)

        return None

    def build_view_port(self) -> ViewPort:
        height, width = self._get_view_port_size()

        lines: list[str] = []
        positions: list[BookMark] = []
        first_line = min(self.scroll_offset, self.cursor.y)
        for i, line in enumerate(self.buffer[first_line:], first_line):
            # we append an space here so we can go past eol
            # on the screen every line has at least one space
            line += " "
            wrapped = wrap(line, width, tabsize=self.Config.TAB_SIZE)
            wrapped_positions = [BookMark(i, j) for j in range(len(wrapped))]
            lines.extend(wrapped)
            positions.extend(wrapped_positions)

            if len(lines) >= height and i >= self.cursor.y:
                break

        # adjust overfetch
        if len(lines) > height:
            lines_to_remove = len(lines) - height
            # distance from the cursor to the beginning of the fetched lines
            distance0 = abs(positions[0].line - self.cursor.y)
            # distance from the cursor to the end of the fetched lines
            distance1 = abs(positions[-1].line - self.cursor.y)

            if distance1 < distance0:  # remove from the beginning
                lines = lines[lines_to_remove:]
                positions = positions[lines_to_remove:]
            else:  # remove from the end
                lines = lines[:-lines_to_remove]
                positions = positions[:-lines_to_remove]

        self.scroll_offset = positions[0].line

        # TODO: that's not gonna work when there are wrapped lines
        # we have to compute y position better
        # we have to compute x position better as well
        # cursor = Cursor(self.cursor.y - self.scroll_offset, self.cursor.x)
        cursor = self.cursor_to_view_port(self.cursor, positions, width)
        if cursor is None:
            raise Exception("Cursor out of the view port error")
        if cursor.x >= width:
            breakpoint()

        # lines[-1] = f"(y: {self.cursor.y}, x: {self.cursor.x}) linelen: {
        #     len(self.buffer[self.cursor.y])}"
        # x = self.buffer[self.cursor.y][-1]
        # assert x != '\n'

        self.view_port = ViewPort(
            height=height, width=width, lines=lines, positions=positions, cursor=cursor
        )

        return self.view_port

    def print(self) -> None:
        self.view_port = self.build_view_port()
        self._print(self.view_port)

    def read_key(self) -> None:
        k = self._read_key()

        match k:
            case Key.q:
                self.quit = True
            case Key.CTRL_Q:
                self.quit = True
            case Key.h:
                self.cursor_left()
            case Key.j:
                self.cursor_down()
            case Key.k:
                self.cursor_up()
            case Key.l:
                self.cursor_right()
            case _:
                pass

    def run(self) -> None:
        while not self.quit:
            self.print()
            self.read_key()


class CursesContextManager:
    def __init__(self) -> None:
        self.stdscr = curses.initscr()
        curses.set_tabsize(Vy.Config.TAB_SIZE)

    def __enter__(self) -> curses.window:
        curses.noecho()
        curses.raw()
        curses.nonl()
        self.stdscr.keypad(True)

        curses.start_color()
        curses.use_default_colors()

        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_WHITE)

        self.stdscr.clear()

        return self.stdscr

    def __exit__(self, *_: list[Any]) -> None:
        curses.noraw()
        # curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()


class Key(StrEnum):
    CTRL_A = chr(1)
    CTRL_B = chr(2)
    CTRL_C = chr(3)
    CTRL_D = chr(4)
    CTRL_E = chr(5)
    CTRL_F = chr(6)
    CTRL_G = chr(7)
    CTRL_H = chr(8)
    CTRL_I = chr(9)
    CTRL_J = chr(10)
    CTRL_K = chr(11)
    CTRL_L = chr(12)
    CTRL_M = chr(13)
    CTRL_N = chr(14)
    CTRL_O = chr(15)
    CTRL_P = chr(16)
    CTRL_Q = chr(17)
    CTRL_R = chr(18)
    CTRL_S = chr(19)
    CTRL_T = chr(20)
    CTRL_U = chr(21)
    CTRL_V = chr(22)
    CTRL_W = chr(23)
    CTRL_X = chr(24)
    CTRL_Y = chr(25)
    CTRL_Z = chr(26)
    h = "h"
    j = "j"
    k = "k"
    l = "l"  # noqa: E741
    q = "q"


def print_view_port(view_port: ViewPort, window: curses.window) -> None:
    window.clear()
    vp_height, vp_width = window.getmaxyx()

    for i, line in enumerate(view_port.lines):
        if i == vp_height - 1 and len(line) == vp_width:
            # from addstr docs: Attempting to write to the lower right corner of a
            # window, subwindow, or pad will cause an exception to be raised after
            # the string is printed.
            window.addstr(i, 0, line[:-1])
            window.insch(i, vp_width - 1, line[-1])
        else:
            window.addstr(i, 0, line)

    # print cursor
    window.move(view_port.cursor.y, view_port.cursor.x)


def main() -> None:
    # if len(sys.argv) != 2:
    #    raise Exception()
    with CursesContextManager() as stdscr:

        read_key: ReadKeyCallback = lambda: stdscr.getkey()
        get_view_port_size: GetViewPortSizeCallback = lambda: ViewPortSize(
            *stdscr.getmaxyx()
        )
        print_: PrintCallback = partial(print_view_port, window=stdscr)

        Vy(
            read_key=read_key,
            get_view_port_size=get_view_port_size,
            print_=print_,
            file_path="main.py",
        ).run()


if __name__ == "__main__":
    main()
