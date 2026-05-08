# Winfox Encrypted Config Reference

This document describes the server-side reference flow for generating
`WINFOX_CONFIG_*` values for the browser encrypted config transport.

## Mode

Current browser mode:

1. `WINFOX_CONFIG_MODE=cbc-hmac-zlib`

The browser expects:

1. UTF-8 JSON
2. `zlib.compress(...)`
3. `AES-256-CBC`
4. `HMAC-SHA256(iv || ciphertext)`
5. base64 for IV, HMAC, and ciphertext

## Required Env Variables

Always required:

1. `WINFOX_CONFIG_VERSION=1`
2. `WINFOX_CONFIG_MODE=cbc-hmac-zlib`
3. `WINFOX_CONFIG_IV=<base64>`
4. `WINFOX_CONFIG_HMAC=<base64>`

Payload forms:

1. Single blob:
   `WINFOX_CONFIG_ENC=<base64>`
2. Chunked blob:
   `WINFOX_CONFIG_ENC_COUNT=<n>`
   `WINFOX_CONFIG_ENC_1...N=<base64 fragments>`

## Reference Script

Use:

```bash
python tools/encode_winfox_config.py path/to/config.json
```

The encoder:

1. compresses the plaintext JSON
2. encrypts the compressed payload
3. base64-encodes the ciphertext
4. emits a single `WINFOX_CONFIG_ENC` variable if it fits
5. otherwise emits chunked `WINFOX_CONFIG_ENC_1...N` variables automatically
6. fails early if the final env payload is too large for the configured env-size budget

Sample input file:

```bash
tools/sample_winfox_config.json
```

The script requires `pycryptodome` on the server side:

```bash
python -m pip install pycryptodome
```

## Input JSON

The input file is plaintext fingerprint JSON. Example:

```json
{
  "canvas:seed": 123456,
  "audio:seed": 654321,
  "timezone": "Asia/Ho_Chi_Minh",
  "navigator:userAgent": "Mozilla/5.0 ...",
  "navigator:platform": "Win32",
  "navigator:oscpu": "Windows NT 10.0; Win64; x64",
  "navigator:hardwareConcurrency": 8,
  "screen.width": 1920,
  "screen.height": 1080,
  "screen.colorDepth": 24,
  "webgl:vendor": "Intel Inc.",
  "webgl:renderer": "Intel Iris OpenGL Engine"
}
```

## Output Formats

### JSON

```bash
python tools/encode_winfox_config.py config.json --shell json
```

Useful options:

```bash
python tools/encode_winfox_config.py config.json --chunk-size 2047 --max-env-size 28000
python tools/encode_winfox_config.py config.json --single-only
python tools/encode_winfox_config.py config.json --force-chunked
```

### PowerShell

```bash
python tools/encode_winfox_config.py config.json --shell powershell
```

### CMD

```bash
python tools/encode_winfox_config.py config.json --shell cmd
```

### Bash

```bash
python tools/encode_winfox_config.py config.json --shell bash
```

## Examples

### Launch Browser Directly From PowerShell

```powershell
python tools/encode_winfox_config.py config.json --shell powershell > .\winfox-env.ps1
. .\winfox-env.ps1
& "C:\path\to\winfox.exe"
```

### Launch Browser Directly In One Command

```bash
python tools/launch_winfox_with_encrypted_config.py tools/sample_winfox_config.json
```

Pass a browser explicitly:

```bash
python tools/launch_winfox_with_encrypted_config.py tools/sample_winfox_config.json --browser "C:\path\to\winfox.exe"
```

### Feed Into `RDPBrowser`

The script can emit JSON, then your server can load that JSON and pass it into
`RDPBrowser(encrypted_config_env=...)`.

```python
import json
import subprocess

from winfox.rdp import RDPBrowser


env_json = subprocess.check_output(
    ["python", "tools/encode_winfox_config.py", "config.json", "--shell", "json"],
    text=True,
)
encrypted_env = json.loads(env_json)

browser = RDPBrowser(
    executable_path=r"C:\path\to\winfox.exe",
    encrypted_config_env=encrypted_env,
)
```

## Notes

1. `encrypted_config_env` must not be mixed with Python-side `fingerprint`,
   `timezone`, or `locale`.
2. The browser verifies HMAC before AES-CBC decrypt.
3. If the ciphertext is short enough, the script emits a single
   `WINFOX_CONFIG_ENC` variable.
4. If it is longer, the script emits chunked `WINFOX_CONFIG_ENC_1...N` values.
5. Chunking avoids per-variable env limits, but not the total process env limit.
6. The reference encoder defaults to:
   - `chunk_size = 2047`
   - `max_env_size = 28000`
7. `RDPBrowser(encrypted_config_env=...)` also validates the estimated final env block size before launch.
