#!/usr/bin/env python3
"""Launch Winfox directly from a plaintext config JSON in one command.

Examples:

    python tools/launch_winfox_with_encrypted_config.py tools/sample_winfox_config.json
    python tools/launch_winfox_with_encrypted_config.py tools/sample_winfox_config.json --browser "C:\\path\\to\\winfox.exe"
    python tools/launch_winfox_with_encrypted_config.py tools/sample_winfox_config.json -- --headless about:blank
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from encode_winfox_config import encode_env, load_json_bytes


def _resolve_browser_path(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Browser executable not found: {path}")
        return str(path)

    env_path = os.getenv("WINFOX_PATH") or os.getenv("WINFOX_BROWSER_PATH")
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Browser executable from env not found: {path}")
        return str(path)

    repo_root = Path(__file__).resolve().parents[1]
    pythonlib = repo_root / "pythonlib"
    if pythonlib.is_dir():
        sys.path.insert(0, str(pythonlib))
        try:
            from winfox.pkgman import launch_path  # type: ignore

            return str(launch_path())
        except Exception:
            pass

    raise FileNotFoundError(
        "Unable to resolve Winfox executable. Pass --browser or set WINFOX_PATH."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Encrypt a plaintext config JSON into WINFOX_CONFIG_* env vars and launch Winfox."
    )
    parser.add_argument(
        "config",
        help="Path to plaintext fingerprint JSON, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--browser",
        help="Path to the Winfox executable. If omitted, resolves from WINFOX_PATH or winfox.pkgman.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=2047,
        help="Maximum ciphertext chunk size for chunked env output.",
    )
    parser.add_argument(
        "--force-chunked",
        action="store_true",
        help="Always emit chunked WINFOX_CONFIG_ENC_1...N variables.",
    )
    parser.add_argument(
        "browser_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments passed to the browser. Prefix with -- to stop launcher parsing.",
    )
    args = parser.parse_args()

    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size must be greater than zero")

    browser_path = _resolve_browser_path(args.browser)
    payload = load_json_bytes(args.config)
    encrypted_env = encode_env(
        payload,
        chunk_size=args.chunk_size,
        force_chunked=args.force_chunked,
    )

    env = os.environ.copy()
    env.update(encrypted_env)

    browser_args = list(args.browser_args)
    if browser_args and browser_args[0] == "--":
        browser_args = browser_args[1:]

    command = [browser_path, *browser_args]
    print(f"Launching Winfox: {browser_path}")
    process = subprocess.Popen(command, env=env)
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
