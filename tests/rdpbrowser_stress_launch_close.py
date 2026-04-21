import asyncio
import os
from pathlib import Path

from camoufox.rdp_api import RDPBrowser


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
ITERATIONS = int(os.environ.get("STRESS_ITERATIONS", "10"))
RDP_PORT_BASE = int(os.environ.get("RDP_PORT_BASE", "6400"))
WS_PORT_BASE = int(os.environ.get("WS_PORT_BASE", "9100"))


async def main() -> None:
    if not WINFOX_PATH:
        raise RuntimeError("Set WINFOX_PATH to the built Winfox executable path")
    if not Path(WINFOX_PATH).exists():
        raise FileNotFoundError(f"WINFOX_PATH not found: {WINFOX_PATH}")

    for index in range(ITERATIONS):
        rdp_port = RDP_PORT_BASE + index
        ws_port = WS_PORT_BASE + index
        print(f"[ITER {index + 1}/{ITERATIONS}] launch rdp={rdp_port} ws={ws_port}")
        async with RDPBrowser(
            executable_path=WINFOX_PATH,
            headless=False,
            rdp_port=rdp_port,
            ws_port=ws_port,
        ) as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")
            await page.wait_for_load_state("load")
            title = await page.evaluate("document.title")
            print(f"[ITER {index + 1}] title={title!r}")
        await asyncio.sleep(1)

    print(f"PASS launch/close stress x{ITERATIONS}")


if __name__ == "__main__":
    asyncio.run(main())
