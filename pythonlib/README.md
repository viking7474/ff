<div align="center">

# Winfox Python Interface

#### Standalone Python package for `winfox.rdp`.

</div>

## Overview

This distribution installs only the `winfox` package surface.

Primary imports:

1. `from winfox.rdp import RDPBrowser`
2. `from winfox import RDPBrowser`

The active Python automation namespace is `winfox.rdp`.

## Installation

```bash
pip install -U winfox
```

## Browser Binary

Provide the Winfox browser binary by one of these methods:

1. Pass `executable_path=...` when creating `RDPBrowser`
2. Set `WINFOX_PATH`
3. Place the browser in the default cache directory reported by `python -m winfox info`

Useful commands:

```bash
python -m winfox info
python -m winfox path
```

## Minimal Example

```python
import asyncio

from winfox.rdp import RDPBrowser


async def main():
    async with RDPBrowser(executable_path=r"C:\path\to\winfox.exe") as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        print(await page.title())


asyncio.run(main())
```

## More Information

See `docs/rdpbrowser.md` for the current RDP surface and usage notes.
