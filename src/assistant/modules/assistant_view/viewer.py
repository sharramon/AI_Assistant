"""Terminal 2's process: prints the lines it gets on stdin until stdin closes. View only."""

import ctypes
import os
import sys


def main() -> None:
    if os.name == "nt":
        ctypes.windll.kernel32.SetConsoleTitleW("Assistant activity (view only)")
        # Our stdout handle is inherited from the app (terminal 1); write to our own window.
        out = open("CONOUT$", "w", encoding="utf-8", errors="replace")
    else:
        out = sys.stdout
    sys.stdin.reconfigure(encoding="utf-8")
    print("Main Assistant activity. View only: talk in the other terminal.\n", file=out, flush=True)
    for line in sys.stdin:
        print(line, end="", file=out, flush=True)


if __name__ == "__main__":
    main()
