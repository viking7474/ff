import os
import platform
import sys
from pathlib import Path
from typing import Literal, Optional

from platformdirs import user_cache_dir
from rich.console import Console


ARCH_MAP = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "x86": "x86_64",
    "i686": "i686",
    "i386": "i686",
    "arm64": "arm64",
    "aarch64": "arm64",
    "armv5l": "arm64",
    "armv6l": "arm64",
    "armv7l": "arm64",
}
OS_MAP: dict[str, Literal["mac", "win", "lin"]] = {
    "darwin": "mac",
    "linux": "lin",
    "win32": "win",
}

if sys.platform not in OS_MAP:
    raise RuntimeError(f"OS {sys.platform} is not supported")

OS_NAME: Literal["mac", "win", "lin"] = OS_MAP[sys.platform]
INSTALL_DIR: Path = Path(user_cache_dir("winfox"))

LAUNCH_FILE = {
    "win": "winfox.exe",
    "mac": "../MacOS/winfox",
    "lin": "winfox-bin",
}

console = Console()


def rprint(msg: str, fg: Optional[str] = None, nl: bool = True) -> None:
    style = f"bold {fg}" if fg else "bold"
    console.print(msg, style=style, end="\n" if nl else "", highlight=False)


def _coerce_browser_path(browser_path: Optional[Path] = None) -> Optional[Path]:
    if browser_path:
        return browser_path

    env_path = os.getenv("WINFOX_PATH") or os.getenv("WINFOX_BROWSER_PATH")
    if env_path:
        return Path(env_path)
    return None


def get_path(file: str) -> str:
    if OS_NAME == "mac":
        return os.path.abspath(INSTALL_DIR / "Winfox.app" / "Contents" / "Resources" / file)
    return str(INSTALL_DIR / file)


def launch_path(browser_path: Optional[Path] = None) -> str:
    resolved = _coerce_browser_path(browser_path)
    if resolved:
        if resolved.is_file():
            exec_path = str(resolved)
        elif OS_NAME == "mac":
            exec_path = os.path.abspath(
                resolved / "Winfox.app" / "Contents" / "Resources" / LAUNCH_FILE[OS_NAME]
            )
        else:
            exec_path = str(resolved / LAUNCH_FILE[OS_NAME])
    else:
        exec_path = get_path(LAUNCH_FILE[OS_NAME])

    if not os.path.exists(exec_path):
        raise FileNotFoundError(
            "Winfox executable was not found. Set `WINFOX_PATH`, pass `executable_path`, "
            "or install the browser into the default Winfox cache directory."
        )
    return exec_path
