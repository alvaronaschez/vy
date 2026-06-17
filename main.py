# from __future__ import annotations  # python < 3.14

import curses
from dataclasses import dataclass
from enum import Enum, StrEnum, auto
from functools import partial
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


def cut_line(s: str, tab_size: int, offset: int, width: int) -> str:
    result: str = expand_tabs(s, tab_size)
    result = wcwidth.clip(result, offset, offset + width, control_codes="ignore")
    return result


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
    # positions: list[BookMark]


type ReadKeyCallback = Callable[[], str]
type RenderCallback = Callable[[ViewPort], None]
type GetViewPortSizeCallback = Callable[[], ViewPortSize]  # (height, width)


class Vy:
    __slots__ = (
        "_read_key",
        "_render",
        "_get_view_port_size",
        "buffer",
        "cursor",
        "y_off",
        "x_off",
        "x_goal",
        "view_port",
        "mode",
        "insert_buffer",
        "quit",
    )

    class Mode(Enum):
        NORMAL = auto()
        INSERT = auto()

    class Config:
        TAB_SIZE = 8

    def __init__(
        self: Self,
        read_key: ReadKeyCallback,
        render: RenderCallback,
        get_view_port_size: GetViewPortSizeCallback,
        file_path: str | None = None,
    ) -> None:
        self._read_key = read_key
        self._render = render
        self._get_view_port_size = get_view_port_size

        self.buffer: Text = Text(file_path)
        self.cursor: TextCursor = self.buffer.get_cursor()

        self.y_off: int = 0  # first line to print
        self.x_off: int = 0  # first column to print
        self.x_goal: int = 0
        self.view_port: ViewPort | None = None

        self.mode: Vy.Mode = self.Mode.NORMAL
        self.insert_buffer: str = ""
        self.quit: bool = False

    def cursor_down(self) -> None:
        self.cursor.to_next_line()
        self.cursor.to_column(self.x_goal, self.Config.TAB_SIZE)

    def cursor_up(self) -> None:
        self.cursor.to_prev_line()
        self.cursor.to_column(self.x_goal, self.Config.TAB_SIZE)

    def cursor_left(self) -> None:
        self.cursor.prev()
        self.x_goal = self.cursor.get_column(self.Config.TAB_SIZE)

    def cursor_right(self) -> None:
        if self.cursor.is_eof():
            return

        self.cursor.next()
        self.x_goal = self.cursor.get_column(self.Config.TAB_SIZE)

    def build_view_port(self) -> ViewPort:
        height, width = self._get_view_port_size()

        cursor_line_idx = self.cursor.get_line_idx()
        if self.y_off > cursor_line_idx:
            self.y_off = cursor_line_idx
        if cursor_line_idx >= self.y_off + height:
            self.y_off = cursor_line_idx - height + 1

        cursor_column = self.cursor.get_column(tab_size=self.Config.TAB_SIZE)
        if cursor_column < self.x_off:
            self.x_off = cursor_column
        elif cursor_column - self.x_off >= width:
            self.x_off = cursor_column - width + 1

        begin = self.cursor.clone()
        begin.to_prev_line(cursor_line_idx - self.y_off)

        end = begin.clone()
        end.to_next_line(height - 1)
        end.to_end_of_line()

        # text: str
        text: Any = self.buffer.get_range(begin, end)
        if end.get_line_idx() == self.buffer.line_count() - 1:
            # insert eof character, cursor is allowed to sit there
            text += " "
        # keep line endings and replace them with whitespace
        # text: list[str]
        text = text.splitlines(keepends=True)
        text = [line.replace("\n", " ") for line in text]
        # cursor_line = text[cursor_line_idx - self.y_off]
        text = [
            cut_line(line, self.Config.TAB_SIZE, self.x_off, width) for line in text
        ]

        cursor_y = cursor_line_idx - self.y_off
        cursor_x = self.cursor.get_column(tab_size=self.Config.TAB_SIZE) - self.x_off
        cursor = ScreenCursor(cursor_y, cursor_x)

        self.view_port = ViewPort(height=height, width=width, lines=text, cursor=cursor)

        return self.view_port

    def render(self) -> None:
        self.view_port = self.build_view_port()
        self._render(self.view_port)

    def read_key_(self) -> None:
        k = self._read_key()

        match self.mode:
            case self.Mode.NORMAL:
                match k:
                    case "q":
                        self.quit = True
                    case Key.CTRL_Q:
                        self.quit = True
                    case "h":
                        self.cursor_left()
                    case "j":
                        self.cursor_down()
                    case "k":
                        self.cursor_up()
                    case "l":
                        self.cursor_right()
                    case "i":
                        self.mode = self.Mode.INSERT
                    case "u":
                        self.buffer.undo(self.cursor)
                    case Key.CTRL_R:
                        self.buffer.redo(self.cursor)
                    case _:
                        pass
            case self.Mode.INSERT:
                match k:
                    case Key.ESC:
                        self.buffer.insert(self.cursor, self.insert_buffer)
                        self.insert_buffer = ""
                        self.mode = self.Mode.NORMAL
                    case _:
                        self.insert_buffer += k

    def run(self) -> None:
        while not self.quit:
            self.render()
            self.read_key_()


class CursesContextManager:
    def __init__(self) -> None:
        self.stdscr = curses.initscr()
        curses.set_tabsize(Vy.Config.TAB_SIZE)

    def __enter__(self) -> curses.window:
        curses.noecho()
        curses.raw()
        curses.nonl()
        self.stdscr.keypad(True)

        curses.set_escdelay(25)

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
    ESC = chr(27)
    CTRL_OPEN_BRACKET = chr(27)  # [
    CTRL_SLASH = chr(27)  # /
    CTRL_CLOSE_BRACKET = chr(29)  # ]
    CTRL_CARET = chr(30)  # ^
    CTRL_UNDERSCORE = chr(30)  # _


def print_view_port(view_port: ViewPort, window: curses.window) -> None:
    # window.clear()
    window.erase()
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

    # window.refresh()
    window.noutrefresh()  # stage update (no draw)
    curses.doupdate()  # flush everything at once


def main() -> None:
    # if len(sys.argv) != 2:
    #    raise Exception()
    with CursesContextManager() as stdscr:

        read_key: ReadKeyCallback = lambda: stdscr.getkey()
        get_view_port_size: GetViewPortSizeCallback = lambda: ViewPortSize(
            *stdscr.getmaxyx()
        )
        render: RenderCallback = partial(print_view_port, window=stdscr)

        Vy(
            read_key=read_key,
            get_view_port_size=get_view_port_size,
            render=render,
            # file_path="foo.test",
            # file_path="main.py",
            file_path="sqlite3.c",
        ).run()


if __name__ == "__main__":
    main()
