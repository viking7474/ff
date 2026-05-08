#!/usr/bin/env python3
"""Reference encoder for WINFOX_CONFIG_* encrypted env transport.

Requires `pycryptodome` on the server side:

    python -m pip install pycryptodome

Examples:

    python tools/encode_winfox_config.py config.json
    python tools/encode_winfox_config.py config.json --shell powershell
    python tools/encode_winfox_config.py - --shell bash < config.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import sys
import zlib
from pathlib import Path
from typing import Dict

try:
    from Crypto.Cipher import AES
except ImportError as exc:  # pragma: no cover - runtime dependency message
    raise SystemExit(
        "Missing dependency: pycryptodome. Install with `python -m pip install pycryptodome`."
    ) from exc


MODE = "cbc-hmac-zlib"
VERSION = "1"
DEFAULT_CHUNK_SIZE = 2047
DEFAULT_MAX_ENV_SIZE = 28000
AES_KEY = bytes(
    [
        0x6D, 0x13, 0x34, 0x9A, 0x27, 0x80, 0xEE, 0x45,
        0x73, 0x2C, 0x9D, 0xB1, 0x14, 0x67, 0xCA, 0x58,
        0xA4, 0x92, 0x0F, 0x36, 0x7B, 0xD8, 0x21, 0x5E,
        0xC9, 0x40, 0x18, 0xAF, 0x63, 0xF4, 0x2A, 0x85,
    ]
)
HMAC_KEY = bytes(
    [
        0x3C, 0xA7, 0x51, 0x20, 0xD4, 0x6E, 0x8B, 0x17,
        0xF2, 0x49, 0x90, 0x2D, 0xBC, 0x74, 0x0A, 0xE1,
        0x65, 0x33, 0xC8, 0x5A, 0x19, 0x8F, 0xD0, 0x47,
        0xAB, 0x26, 0x71, 0x9C, 0x04, 0xDE, 0x58, 0x12,
    ]
)


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def load_json_bytes(path: str) -> bytes:
    if path == "-":
        raw = sys.stdin.buffer.read()
    else:
        raw = Path(path).read_bytes()

    parsed = json.loads(raw.decode("utf-8"))
    canonical = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
    return canonical.encode("utf-8")


def estimate_env_block_size(env: Dict[str, str]) -> int:
    return sum(len(key) + 1 + len(value) + 1 for key, value in env.items())


def encode_env(
    payload: bytes,
    chunk_size: int,
    force_chunked: bool,
    single_only: bool,
) -> Dict[str, str]:
    iv = secrets.token_bytes(16)
    compressed = zlib.compress(payload)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pkcs7_pad(compressed))
    mac = hmac.new(HMAC_KEY, iv + ciphertext, hashlib.sha256).digest()

    iv_b64 = base64.b64encode(iv).decode("ascii")
    ct_b64 = base64.b64encode(ciphertext).decode("ascii")
    mac_b64 = base64.b64encode(mac).decode("ascii")

    env = {
        "WINFOX_CONFIG_VERSION": VERSION,
        "WINFOX_CONFIG_MODE": MODE,
        "WINFOX_CONFIG_IV": iv_b64,
        "WINFOX_CONFIG_HMAC": mac_b64,
    }

    if not force_chunked and len(ct_b64) <= chunk_size:
        env["WINFOX_CONFIG_ENC"] = ct_b64
        return env

    if single_only:
        raise SystemExit(
            "Encrypted config does not fit in a single WINFOX_CONFIG_ENC variable. "
            f"Ciphertext base64 length: {len(ct_b64)}; chunk size limit: {chunk_size}."
        )

    chunks = [ct_b64[i : i + chunk_size] for i in range(0, len(ct_b64), chunk_size)]
    env["WINFOX_CONFIG_ENC_COUNT"] = str(len(chunks))
    for index, chunk in enumerate(chunks, start=1):
        env[f"WINFOX_CONFIG_ENC_{index}"] = chunk
    return env


def validate_env_size(env: Dict[str, str], max_env_size: int) -> None:
    estimated_size = estimate_env_block_size(env)
    if estimated_size <= max_env_size:
        return

    chunk_count = env.get("WINFOX_CONFIG_ENC_COUNT", "1")
    raise SystemExit(
        "Encrypted config too large for env transport. "
        f"Estimated env size: {estimated_size}. "
        f"Configured limit: {max_env_size}. "
        f"Chunk count: {chunk_count}."
    )


def render_json(env: Dict[str, str]) -> str:
    return json.dumps(env, indent=2)


def render_cmd(env: Dict[str, str]) -> str:
    return "\n".join(f"set {key}={value}" for key, value in env.items())


def render_powershell(env: Dict[str, str]) -> str:
    return "\n".join(f'$env:{key}="{value}"' for key, value in env.items())


def render_bash(env: Dict[str, str]) -> str:
    return "\n".join(f"export {key}='{value}'" for key, value in env.items())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Encode a Winfox fingerprint JSON payload into WINFOX_CONFIG_* env variables."
    )
    parser.add_argument(
        "config",
        help="Path to plaintext fingerprint JSON, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--shell",
        choices=["json", "cmd", "powershell", "bash"],
        default="json",
        help="Output format.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Maximum ciphertext chunk size for chunked env output.",
    )
    parser.add_argument(
        "--force-chunked",
        action="store_true",
        help="Always emit WINFOX_CONFIG_ENC_COUNT and WINFOX_CONFIG_ENC_1...N.",
    )
    parser.add_argument(
        "--max-env-size",
        type=int,
        default=DEFAULT_MAX_ENV_SIZE,
        help="Maximum estimated total env block size before failing.",
    )
    parser.add_argument(
        "--single-only",
        action="store_true",
        help="Fail if the ciphertext does not fit in a single WINFOX_CONFIG_ENC variable.",
    )
    args = parser.parse_args()

    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size must be greater than zero")
    if args.max_env_size <= 0:
        raise SystemExit("--max-env-size must be greater than zero")

    payload = load_json_bytes(args.config)
    env = encode_env(
        payload,
        chunk_size=args.chunk_size,
        force_chunked=args.force_chunked,
        single_only=args.single_only,
    )
    validate_env_size(env, max_env_size=args.max_env_size)

    renderers = {
        "json": render_json,
        "cmd": render_cmd,
        "powershell": render_powershell,
        "bash": render_bash,
    }
    print(renderers[args.shell](env))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
