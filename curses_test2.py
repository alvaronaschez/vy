from __future__ import annotations # python < 3.14

from enum import Enum

import curses


class CursesContextManager:
    def __init__(self):
        self.stdscr = curses.initscr()

    def __enter__(self):
        curses.noecho()
        curses.raw()
        curses.nonl()
        self.stdscr.keypad(True)

        curses.start_color()
        curses.use_default_colors()


        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_WHITE)

        self.stdscr.clear()

        return self.stdscr

    def __exit__(self, *_):
        curses.noraw()
        #curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()

class Key(Enum):
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
    q = "q"

    def __eq__(self, other):
        # Compare to another enum member of the same type
        if isinstance(other, Key):
            return self.value == other.value
        # Compare to raw value
        return self.value == other

    def __hash__(self):
        # Ensure hash consistency with __eq__
        return hash(self.value)

def main():
    with CursesContextManager() as stdscr:
        curses.set_tabsize(8)


        stdscr.addstr(0, 0, "1234	6789", curses.color_pair(1))
        stdscr.addstr(1, 0, "12	45	6789", curses.color_pair(1))
        y, x = stdscr.getmaxyx()
        #stdscr.addstr(y-1, 0, "x" * x, curses.color_pair(1))
        stdscr.addstr(y-1, 0, "x" * (x-1), curses.color_pair(1))
        #stdscr.refresh()
        #stdscr.getkey()
        #stdscr.clear()

        c = stdscr.getkey()


if __name__ == "__main__":
    main()
