# RDPBrowser

`RDPBrowser` is the Firefox RDP-based automation path for Winfox.

It is designed for stealth-first automation without relying on Playwright/Juggler as the primary runtime transport.

In this repository, `RDPBrowser` should be treated as the primary Python automation path.

## Architecture

`RDPBrowser` uses three layers:

1. Firefox RDP for browser and target control
2. A temporary WebExtension for bridge commands, proxy auth, and network capture
3. An experiment API for trusted-like input and navigation helpers

Flow:

```text
Python controller
-> geckordp / Firefox RDP
-> extension websocket bridge
-> nativeInput experiment API
-> Firefox tab/window
```

## What It Is Good At

`RDPBrowser` currently works well for:

1. Launching Winfox with an isolated profile
2. Navigating pages and evaluating JavaScript
3. Trusted-like mouse and keyboard input
4. Response capture and request spying through the extension layer
5. Running multiple Winfox instances in parallel with separate ports
6. Basic multi-tab handling via `new_page()` in the same window

## What It Is Not

`RDPBrowser` is not a drop-in replacement for the full Playwright/Juggler protocol surface.

Treat it as:

1. A stealth-first automation backend
2. A single-controller Python API with practical browser operations
3. A path that minimizes dependence on deep Juggler bootstrap patches

## Requirements

The Python environment must have:

1. Local `camoufox` package from `pythonlib/`
2. `geckordp`
3. `websockets`

Example installation:

```bash
python -m pip install -e ./pythonlib
python -m pip install geckordp websockets
```

## Minimal Example

```python
import asyncio

from camoufox.rdp_api import RDPBrowser


async def main():
    async with RDPBrowser(
        executable_path=r"C:\path\to\winfox.exe",
        headless=False,
        rdp_port=6000,
        ws_port=8775,
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        print(await page.title())
        await page.screenshot("rdp_example.png")


asyncio.run(main())
```

## Multi-Tab Example

```python
import asyncio

from camoufox.rdp_api import RDPBrowser


async def main():
    async with RDPBrowser(
        executable_path=r"C:\path\to\winfox.exe",
        headless=False,
        rdp_port=6000,
        ws_port=8775,
    ) as browser:
        page1 = await browser.new_page()
        await page1.goto("https://example.com")

        page2 = await browser.new_page()
        await page2.goto("https://httpbin.org/html")

        print(len(browser.list_pages()))

        await page1.bring_to_front()
        await page2.close()
        await browser.close_all_pages()


asyncio.run(main())
```

## Multi-Instance Usage

Multiple Winfox profiles can run at once as long as each instance gets:

1. A unique `rdp_port`
2. A unique `ws_port`
3. A separate `profile_path`, or let `RDPBrowser` create one

Recommended model:

1. One `RDPBrowser` instance per browser/profile
2. One main controlled page per worker or task group

## Official Smoke Suite

An official manual smoke suite lives at:

`tests/rdpbrowser_smoke.py`

Run it with:

```bash
set WINFOX_PATH=C:\path\to\winfox.exe
python tests/rdpbrowser_smoke.py
```

Or in PowerShell:

```powershell
$env:WINFOX_PATH = 'C:\path\to\winfox.exe'
python tests/rdpbrowser_smoke.py
```

The smoke suite validates:

1. Launch and navigation
2. Selectors and locator operations
3. Input and scrolling
4. Screenshots
5. Response capture and request spying
6. Multi-instance execution
7. Minimal event support
8. Multi-page tab attachment

## Stress Scripts

The repo also includes focused stress scripts:

1. `tests/rdpbrowser_stress_launch_close.py`
2. `tests/rdpbrowser_stress_multi_instance.py`
3. `tests/rdpbrowser_stress_multi_tab.py`
4. `tests/rdpbrowser_windows_cleanup_check.py`

Use them to validate repeated runs, multi-instance behavior, multi-tab lifecycle, and Windows cleanup/port reuse.

Example:

```bash
set WINFOX_PATH=C:\path\to\winfox.exe
python tests\rdpbrowser_stress_launch_close.py
python tests\rdpbrowser_stress_multi_instance.py
python tests\rdpbrowser_stress_multi_tab.py
python tests\rdpbrowser_windows_cleanup_check.py
```

## Supported Surface

See `docs/rdpbrowser_v1_capability_matrix.md` for the current supported surface and maturity levels.

## Comparison With Juggler

See `docs/rdpbrowser_vs_juggler.md` for the current repository positioning and a direct comparison against legacy Juggler automation.

## Troubleshooting

See `docs/rdpbrowser_troubleshooting.md` for common runtime failures and the recommended debug order.
