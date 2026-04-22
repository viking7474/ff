import asyncio
import os
import tempfile
from pathlib import Path

from camoufox.rdp_api import RDPBrowser


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
ITERATIONS = int(os.environ.get("STRESS_ITERATIONS", "5"))
RDP_PORT_BASE = int(os.environ.get("RDP_PORT_BASE", "6800"))
WS_PORT_BASE = int(os.environ.get("WS_PORT_BASE", "9500"))


async def main() -> None:
    if not WINFOX_PATH:
        raise RuntimeError("Set WINFOX_PATH to the built Winfox executable path")
    if not Path(WINFOX_PATH).exists():
        raise FileNotFoundError(f"WINFOX_PATH not found: {WINFOX_PATH}")

    for index in range(ITERATIONS):
        print(f"[ITER {index + 1}/{ITERATIONS}] save/load state")
        state_file = None
        async with RDPBrowser(
            executable_path=WINFOX_PATH,
            headless=False,
            rdp_port=RDP_PORT_BASE + index * 2,
            ws_port=WS_PORT_BASE + index * 2,
        ) as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")
            await page.wait_for_load_state("load")
            await page.set_local_storage({"persist_key": f"value_{index}"})
            await page.evaluate(f"document.cookie = 'persist_cookie={index}; path=/'; true")
            state = await browser.save_state()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as handle:
                state_file = handle.name
            await browser.save_state_to_file(state_file)

        async with RDPBrowser(
            executable_path=WINFOX_PATH,
            headless=False,
            rdp_port=RDP_PORT_BASE + index * 2 + 1,
            ws_port=WS_PORT_BASE + index * 2 + 1,
        ) as browser2:
            result = await browser2.load_state(state, clear_existing=True)
            print(f"  loaded: {result}")
            page = await browser2.new_page()
            await page.goto("https://example.com")
            await page.wait_for_load_state("load")
            storage = await page.get_local_storage()
            cookies = await page.evaluate("document.cookie")
            if storage.get("persist_key") != f"value_{index}":
                raise RuntimeError(f"localStorage mismatch: {storage}")
            if f"persist_cookie={index}" not in cookies:
                raise RuntimeError(f"cookie mismatch: {cookies}")

        async with RDPBrowser(
            executable_path=WINFOX_PATH,
            headless=False,
            rdp_port=RDP_PORT_BASE + index * 2 + 10,
            ws_port=WS_PORT_BASE + index * 2 + 10,
        ) as browser3:
            result = await browser3.load_state_from_file(state_file, clear_existing=True)
            print(f"  loaded from file: {result}")
            page = await browser3.new_page()
            await page.goto("https://example.com")
            await page.wait_for_load_state("load")
            storage = await page.get_local_storage()
            cookies = await page.evaluate("document.cookie")
            if storage.get("persist_key") != f"value_{index}":
                raise RuntimeError(f"file localStorage mismatch: {storage}")
            if f"persist_cookie={index}" not in cookies:
                raise RuntimeError(f"file cookie mismatch: {cookies}")

        if state_file and os.path.exists(state_file):
            os.unlink(state_file)

    print(f"PASS state persistence check x{ITERATIONS}")


if __name__ == "__main__":
    asyncio.run(main())
