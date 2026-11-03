"""A local page in its own window: Edge app mode (no tabs or address bar) on its own profile.

Its own profile makes it its own Edge process, separate from your normal Edge, so the app
can close it again. With `devtools`, Edge also opens its DevTools port on 127.0.0.1 (Edge
picks the port and writes it to the profile); the HTML viewer's snip uses it to take a
screenshot of exactly what you see. Used by `temp_ui` and the HTML viewer app.
"""

from __future__ import annotations

import logging
import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

EDGE = [
    Path(os.environ.get(var, "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")
]

log = logging.getLogger(__name__)


def open_app_window(
    url: str, profile: Path, *, size: str = "1400,850", devtools: bool = False, log: Any = log
) -> subprocess.Popen | None:
    """Open `url` in an Edge app window running on `profile`.

    `devtools`: also listen for DevTools on 127.0.0.1 (see `devtools_port`).
    Falls back to a browser tab without Edge, and returns `None` then.
    """
    edge = next((path for path in EDGE if path.is_file()), None)
    if edge is None:
        log.info("Edge not found; opening %s in a browser tab", url)
        webbrowser.open(url)
        return None
    args = [
        str(edge),
        f"--app={url}",
        f"--window-size={size}",
        f"--user-data-dir={profile}",
    ]
    if devtools:
        (Path(profile) / "DevToolsActivePort").unlink(missing_ok=True)  # Edge writes a fresh one
        args += ["--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0"]
    return subprocess.Popen([*args, "--no-first-run", "--no-default-browser-check"])


def close_app_windows(profile: Path, log: Any = log) -> None:
    """Stop the Edge processes running on `profile`: that app window, and nothing else.

    Windows only (a no-op elsewhere). Blocks up to 15 s; use `asyncio.to_thread` from async code.
    """
    if os.name != "nt":
        return
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
        "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:APP_WINDOW_PROFILE) } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    env = {**os.environ, "APP_WINDOW_PROFILE": f"--user-data-dir={profile}"}
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env=env, capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("Couldn't close the app window: %s", exc)


def raise_window(pid: int | None, title: str) -> bool:
    """Bring an app window to the front (restoring it if minimized). Windows only.

    Finds a visible Edge window owned by `pid` (the Edge the app started), or else one whose
    title ends with `title`. Returns whether it found one; elsewhere than Windows, `True`
    (it can't tell, so the caller shouldn't open another window).
    """
    if os.name != "nt":
        return True
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    found: list[tuple[bool, int]] = []  # (owned by pid, hwnd)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, 256)
        if name.value != "Chrome_WidgetWin_1":
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        text = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, text, 512)
        if text.value and (owner.value == pid or text.value.endswith(title)):
            found.append((owner.value == pid, hwnd))
        return True

    user32.EnumWindows(visit, 0)
    if not found:
        return False
    hwnd = max(found, key=lambda item: item[0])[1]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # Windows keeps a background process from taking the foreground; borrowing the input of
    # the window in front (AttachThreadInput) lets it.
    front = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    me = kernel32.GetCurrentThreadId()
    attached = front != me and bool(user32.AttachThreadInput(me, front, True))
    try:
        user32.BringWindowToTop(hwnd)
        if not user32.SetForegroundWindow(hwnd):
            log.info("Windows didn't let the %s window come to the front", title)
    finally:
        if attached:
            user32.AttachThreadInput(me, front, False)
    return True


def devtools_port(profile: Path) -> int | None:
    """The DevTools port of the window running on `profile`, if it has one."""
    try:
        return int((Path(profile) / "DevToolsActivePort").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
