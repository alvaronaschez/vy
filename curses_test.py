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


        #stdscr.addstr(10, 10, "Hello World!", curses.color_pair(1))
        #stdscr.refresh()
        #stdscr.getkey()
        #stdscr.clear()

        while True:
            c = stdscr.getkey()
            #c = stdscr.get_wch()

            stdscr.clear()

            #if c == "q": return
            #match c.__repr__():
            match str(c):
                case "q":
                    break
                case Key.CTRL_A:
                    stdscr.addstr(0, 0, "Ctrl+A")
                case Key.CTRL_B:
                    stdscr.addstr(0, 0, "Ctrl+B")
                case Key.CTRL_C:
                    stdscr.addstr(0, 0, "Ctrl+C")
                case Key.CTRL_D:
                    stdscr.addstr(0, 0, "Ctrl+D")
                case Key.CTRL_E:
                    stdscr.addstr(0, 0, "Ctrl+E")
                case Key.CTRL_F:
                    stdscr.addstr(0, 0, "Ctrl+F")
                case Key.CTRL_G:
                    stdscr.addstr(0, 0, "Ctrl+G")
                case Key.CTRL_H:
                    stdscr.addstr(0, 0, "Ctrl+H")
                case Key.CTRL_I:
                    stdscr.addstr(0, 0, "Ctrl+I")
                case Key.CTRL_J:
                    stdscr.addstr(0, 0, "Ctrl+J")
                case Key.CTRL_K:
                    stdscr.addstr(0, 0, "Ctrl+K")
                case Key.CTRL_L:
                    stdscr.addstr(0, 0, "Ctrl+L")
                case Key.CTRL_M:
                    stdscr.addstr(0, 0, "Ctrl+M")
                case Key.CTRL_N:
                    stdscr.addstr(0, 0, "Ctrl+N")
                case Key.CTRL_O:
                    stdscr.addstr(0, 0, "Ctrl+O")
                case Key.CTRL_P:
                    stdscr.addstr(0, 0, "Ctrl+P")
                case Key.CTRL_Q:
                    stdscr.addstr(0, 0, "Ctrl+Q")
                case Key.CTRL_R:
                    stdscr.addstr(0, 0, "Ctrl+R")
                case Key.CTRL_S:
                    stdscr.addstr(0, 0, "Ctrl+S")
                case Key.CTRL_T:
                    stdscr.addstr(0, 0, "Ctrl+T")
                case Key.CTRL_U:
                    stdscr.addstr(0, 0, "Ctrl+U")
                case Key.CTRL_V:
                    stdscr.addstr(0, 0, "Ctrl+V")
                case Key.CTRL_W:
                    stdscr.addstr(0, 0, "Ctrl+W")
                case Key.CTRL_X:
                    stdscr.addstr(0, 0, "Ctrl+X")
                case Key.CTRL_Y:
                    stdscr.addstr(0, 0, "Ctrl+Y")
                case Key.CTRL_Z:
                    stdscr.addstr(0, 0, "Ctrl+Z")
                case _:
                    stdscr.addstr(0, 0, c)
                    #stdscr.addstr(0, 0, repr(c))
                    #stdscr.addstr(1, 0, str(c))
                    #stdscr.addstr(0, 0, f'{c}')
                    #stdscr.addstr(0, 0, f'{repr(c)}')


if __name__ == "__main__":
    main()
