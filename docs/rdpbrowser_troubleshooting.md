# RDPBrowser Troubleshooting

This guide covers the most common runtime issues seen while bringing `RDPBrowser` to a stable state in this repository.

## Basic Checklist

Before debugging behavior, verify:

1. `WINFOX_PATH` points to the correct built executable
2. the Python environment can import `camoufox`, `geckordp`, and `websockets`
3. each running browser instance has a unique `rdp_port` and `ws_port`

## Import Errors

### `ModuleNotFoundError: No module named 'camoufox'`

Cause:

1. local `pythonlib/` package is not installed in the active environment

Fix:

```bash
python -m pip install -e ./pythonlib
python -m pip install geckordp websockets
```

## Bridge Not Connected

### `ConnectionError: Extension bridge not connected`

Cause:

1. the temporary addon did not connect back to the Python websocket bridge
2. `ws_port` is already in use
3. the browser instance launched, but the extension install/connection path failed

Things to check:

1. use unique `ws_port` values for concurrent browsers
2. run `tests/rdpbrowser_smoke.py` first before more advanced tests
3. verify the build still includes the extension experiment API and addon loading path

## Encrypted Config

### `ERROR: Failed to load encrypted WINFOX config`

Cause:

1. one or more `WINFOX_CONFIG_*` variables are missing
2. `WINFOX_CONFIG_HMAC` does not match the encrypted payload
3. ciphertext, IV, or HMAC are not valid base64
4. decrypt or zlib-decompress failed
5. decrypted plaintext is not valid JSON

Things to check:

1. `WINFOX_CONFIG_MODE=cbc-hmac-zlib`
2. `WINFOX_CONFIG_IV` is present
3. `WINFOX_CONFIG_HMAC` is present
4. either `WINFOX_CONFIG_ENC` is present, or `WINFOX_CONFIG_ENC_COUNT` plus all `WINFOX_CONFIG_ENC_1...N` chunks are present
5. the same AES key and HMAC key were used by the external encryption service
6. for a server-side reference encoder, see `docs/winfox_encrypted_config_reference.md` and `tools/encode_winfox_config.py`

### `ValueError` from `RDPBrowser(..., encrypted_config_env=...)`

Cause:

1. encrypted env is missing required keys
2. `fingerprint`, `timezone`, or `locale` were passed together with `encrypted_config_env`

Fix:

1. pass encrypted identity only through `encrypted_config_env`
2. do not mix encrypted identity transport with Python-side fingerprint/timezone/locale overrides

## `new_page()` Problems

### `TimeoutError: Timed out waiting for a new tab actor`

Cause:

1. a new tab was requested but Firefox did not expose a new tab actor in time
2. in earlier iterations, closing the last tab destabilized later rounds

Current mitigation in this repo:

1. the first `new_page()` attaches the startup tab
2. later `new_page()` calls create new tabs
3. closing the final page keeps a background `about:blank` tab alive internally so future tab creation remains stable

If you see this again:

1. rerun `tests/rdpbrowser_multi_tab_smoke.py`
2. rerun `tests/rdpbrowser_stress_multi_tab.py`
3. verify the issue is not just a one-off browser startup race

## Event Issues

### `page.on()` callback never fires

Cause:

1. event support is intentionally minimal
2. the supported events are currently:
   - `load`
   - `domcontentloaded`
   - `framenavigated`

Recommendations:

1. start with `page.on("load", cb)` in a simple navigation flow
2. verify using `tests/rdpbrowser_event_reliability_smoke.py`
3. avoid assuming Playwright-level event parity for request/response events

## Input Problems

### Text does not appear after `fill()`

Cause:

1. bridge input path may be unavailable for that page
2. older code used key modifiers that were not supported by the extension path

Current behavior:

1. `fill()` now clears via DOM assignment and types through the bridge when available

If it regresses:

1. confirm `page.click()` works first
2. confirm `keyboard.press()` works
3. confirm the page has a valid `tab_id` and bridge connection

## File Upload Problems

### `set_input_files()` fails

Cause:

1. selector does not point to an `<input type="file">`
2. one of the provided local paths does not exist
3. multiple files were supplied to a non-multiple file input

Current behavior:

1. `set_input_files()` is a practical file-input helper
2. it does not implement native file chooser parity
3. it dispatches `input` and `change` after populating the file input

Recommendations:

1. start with a simple injected `<input type="file">` smoke flow
2. verify the selector points to the real file input element
3. verify file existence before calling the helper

## Storage / State Problems

### `save_state()` or `load_state()` does not restore everything

Cause:

1. the current state model is intentionally practical, not full browser context parity
2. the current implementation focuses on cookies and per-origin `localStorage`

Recommendations:

1. use `page.get_session_storage()` / `page.set_session_storage()` only as page-level helpers for now
2. treat `save_state()` / `load_state()` as a practical session reuse tool, not a full Playwright-style storage-state equivalent
3. use `clear_existing=True` when you want a cleaner restore on a fresh browser instance
4. use `save_state_to_file()` / `load_state_from_file()` when you need to persist state outside process memory

## Context Model Notes

The current context model is intentionally minimal:

1. each context is backed by an isolated child browser instance
2. ports are allocated dynamically to reduce collisions
3. use `tests/rdpbrowser_context_smoke.py` and `tests/rdpbrowser_context_stress.py` when validating context isolation and cleanup

## Network Capture Confusion

### `wait_for_response()` succeeds but `get_captured_responses()` is empty

Cause:

1. older logic cleared captures too aggressively

Current behavior:

1. `wait_for_response()` no longer clears captures automatically
2. use `get_captured_responses(clear=False)` if you want to inspect captured data after waiting

## Windows Cleanup / Port Reuse

### Repeated runs leave ports in use or produce shutdown warnings

Use the dedicated validation scripts:

1. `tests/rdpbrowser_stress_launch_close.py`
2. `tests/rdpbrowser_windows_cleanup_check.py`

These scripts are the fastest way to detect:

1. lingering browser processes
2. websocket bridge cleanup issues
3. port reuse problems between runs

### `Cancelling an overlapped future failed` on Windows

Cause:

1. Python's default Proactor event loop on Windows can emit noisy shutdown warnings for pipe transports even when the browser session itself completed successfully.

Current repository approach:

1. the official `RDPBrowser` test and stress scripts force `asyncio.WindowsSelectorEventLoopPolicy()` on Windows to avoid this warning in manual validation runs

If you write your own standalone Windows runner and see the same warning, add this before creating the event loop:

```python
import asyncio
import os

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

## Recommended Debug Order

If something breaks, test in this order:

1. `tests/rdpbrowser_smoke.py`
2. `tests/rdpbrowser_multi_tab_smoke.py`
3. `tests/rdpbrowser_event_reliability_smoke.py`
4. `tests/rdpbrowser_stress_launch_close.py`
5. `tests/rdpbrowser_stress_multi_tab.py`
6. `tests/rdpbrowser_stress_multi_instance.py`
7. `tests/rdpbrowser_windows_cleanup_check.py`
