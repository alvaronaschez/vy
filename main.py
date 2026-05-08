# from __future__ import annotations  # python < 3.14

from dataclasses import dataclass
from enum import StrEnum
from functools import partial
import curses
from typing import Any, Callable, NamedTuple, Self

import wcwidth

from text import Cursor as TextCursor
from text import Text

# import sys



def get_width(grapheme: str) -> int:
    if grapheme == "\n":
        return 1
    else:
        return wcwidth.width(grapheme)


def expand_tabs(s: str, tab_size: int) -> str:
    result: list[str] = []
    column = 0
    for grapheme in wcwidth.iter_graphemes(s):
        if grapheme == "\t":
            spaces = tab_size - (column % tab_size)
            result.append(spaces * " ")
            column += spaces
        else:
            result.append(grapheme)
            column += get_width(grapheme)

    return "".join(result)


def wrap(s: str, width: int, tabsize: int) -> list[str]:
    result: list[str] = []
    aux: list[str] = []
    column = 0
    s = expand_tabs(s, tabsize)
    for grapheme in wcwidth.iter_graphemes(s):
        if column + get_width(grapheme) > width:
            result.append("".join(aux))
            aux = [grapheme]
            column = get_width(grapheme)
        else:
            aux.append(grapheme)
            column += get_width(grapheme)
    result.append("".join(aux))
    return result


@dataclass
class ScreenCursor:
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
    cursor: ScreenCursor
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

    buffer: Text
    cursor: TextCursor

    scroll_offset: int = 0  # visible lines above the cursor
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

        self.buffer = Text(file_path)
        self.cursor = self.buffer.get_cursor()

        self.scroll_offset = 0
        self.x_goal = 0
        self.view_port = None
        self.quit = False

    def cursor_down(self) -> None:
        self.cursor.to_next_line()
        self.cursor.to_column(self.x_goal, self.Config.TAB_SIZE)
        self.scroll_offset += 1

    def cursor_up(self) -> None:
        self.cursor.to_prev_line()
        self.cursor.to_column(self.x_goal, self.Config.TAB_SIZE)
        if self.scroll_offset > 0:
            self.scroll_offset -= 1

    def cursor_left(self) -> None:
        self.cursor.prev()
        self.x_goal = self.cursor.get_column(self.Config.TAB_SIZE)
        if self.cursor.is_eol() and self.scroll_offset > 0:
            self.scroll_offset -= 1

    def cursor_right(self) -> None:
        if self.cursor.is_eof():
            return

        if self.cursor.is_eol():
            self.scroll_offset += 1

        self.cursor.next()
        self.x_goal = self.cursor.get_column(self.Config.TAB_SIZE)

    def cursor_to_view_port(
        self, cursor: TextCursor, bookmarks: list[BookMark], lines: list[str]
    ) -> ScreenCursor:
        bol = cursor.clone()
        bol.to_beginning_of_line()

        line_idx = cursor.get_line_idx()

        x = cursor.position - bol.position

        for j, bookmark in enumerate(bookmarks):
            if bookmark.line == line_idx:
                if x > len(lines[j]):
                    x -= len(lines[j])
                else:
                    return ScreenCursor(j, x)
        raise Exception("Cursor out of screen")

    def build_view_port(self) -> ViewPort:
        height, width = self._get_view_port_size()

        self.scroll_offset = min(self.scroll_offset, height - 1)

        lines: list[str] = []
        positions: list[BookMark] = []

        begin = self.cursor.clone()
        begin.to_prev_line(self.scroll_offset)

        end = begin.clone()
        end.to_next_line(height)

        text = self.buffer.get_range(begin, end)
        if end.get_line_idx() == self.buffer.line_count() - 1:
            # insert eof character, cursor is allowed to sit there
            text += " "
        # keep line endings and replace them with whitespace
        text = text.splitlines(keepends=True)
        text = [line.replace("\n", " ") for line in text]

        for i, line in enumerate(text, begin.get_line_idx()):
            # we append an space here so we can go past eol
            # on the screen every line has at least one space
            line += " "
            wrapped = wrap(line, width, tabsize=self.Config.TAB_SIZE)
            wrapped_positions = [BookMark(i, j) for j in range(len(wrapped))]
            lines.extend(wrapped)
            positions.extend(wrapped_positions)

            if len(lines) >= height and i >= self.cursor.get_line_idx():
                break

        # adjust overfetch
        if len(lines) > height:
            lines_to_remove = len(lines) - height
            # distance from the cursor to the beginning of the fetched lines
            distance0 = abs(positions[0].line - self.cursor.get_line_idx())
            # distance from the cursor to the end of the fetched lines
            distance1 = abs(positions[-1].line - self.cursor.get_line_idx())

            if distance1 < distance0:  # remove from the beginning
                lines = lines[lines_to_remove:]
                positions = positions[lines_to_remove:]
            else:  # remove from the end
                lines = lines[:-lines_to_remove]
                positions = positions[:-lines_to_remove]

        # self.scroll_offset = positions[0].line
        self.scroll_offset = self.cursor.get_line_idx() - positions[0].line

        cursor = self.cursor_to_view_port(self.cursor, positions, lines)

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
    a = "a"
    b = "b"
    c = "c"
    d = "d"
    e = "e"
    f = "f"
    g = "g"
    h = "h"
    i = "i"
    j = "j"
    k = "k"
    l = "l"  # noqa: E741
    m = "m"
    n = "n"
    o = "o"
    p = "p"
    q = "q"
    r = "r"
    s = "s"
    t = "t"
    u = "u"
    v = "v"
    w = "w"
    x = "x"
    y = "y"
    z = "z"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"
    H = "H"
    I = "I"
    J = "J"
    K = "K"
    L = "L"
    M = "M"
    N = "N"
    O = "O"
    P = "P"
    Q = "Q"
    R = "R"
    S = "S"
    T = "T"
    U = "U"
    V = "V"
    W = "W"
    X = "X"
    Y = "Y"
    Z = "Z"


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
            # file_path="foo.test",
            # file_path="main.py",
            file_path="sqlite3.c",
        ).run()


if __name__ == "__main__":
    main()
