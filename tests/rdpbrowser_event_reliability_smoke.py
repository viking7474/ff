import asyncio
import os
from pathlib import Path

from camoufox.rdp_api import RDPBrowser


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
RDP_PORT = int(os.environ.get("RDP_PORT", "6300"))
WS_PORT = int(os.environ.get("WS_PORT", "9000"))


async def main() -> None:
    if not WINFOX_PATH:
        raise RuntimeError("Set WINFOX_PATH to the built Winfox executable path")
    if not Path(WINFOX_PATH).exists():
        raise FileNotFoundError(f"WINFOX_PATH not found: {WINFOX_PATH}")

    async with RDPBrowser(
        executable_path=WINFOX_PATH,
        headless=False,
        rdp_port=RDP_PORT,
        ws_port=WS_PORT,
    ) as browser:
        page = await browser.new_page()

        loads = []
        navs = []

        def on_load(payload):
            loads.append(payload)

        def on_nav(payload):
            navs.append(payload)

        page.on("load", on_load)
        page.on("framenavigated", on_nav)

        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await asyncio.sleep(1)

        print("load events:", len(loads))
        if loads:
            print("first load payload keys:", sorted(loads[0].keys()))
            print("first load payload url:", loads[0].get("url"))

        print("framenavigated events:", len(navs))
        if navs:
            print("first framenavigated payload keys:", sorted(navs[0].keys()))
            print("first framenavigated payload url:", navs[0].get("url"))

        page.remove_listener("load", on_load)
        load_count_before = len(loads)
        await page.reload()
        await page.wait_for_load_state("load")
        await asyncio.sleep(1)
        print("load events after remove_listener:", len(loads))
        if len(loads) != load_count_before:
            raise RuntimeError("load listener fired after remove_listener()")

        page2 = await browser.new_page()
        task1 = asyncio.create_task(page.goto("https://example.com"))
        task2 = asyncio.create_task(page2.goto("https://httpbin.org/html"))
        await asyncio.gather(task1, task2)
        print("page1 url:", await page.url_fresh())
        print("page2 url:", await page2.url_fresh())

        await page2.close()
        print("page2 closed:", page2.is_closed())

        try:
            await page2.evaluate("document.title")
        except RuntimeError as exc:
            print("closed page fail-fast:", exc)
        else:
            raise RuntimeError("Closed page did not fail fast")

        print("PASS event and reliability smoke test")


if __name__ == "__main__":
    asyncio.run(main())
