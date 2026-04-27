import asyncio
import os
from pathlib import Path

from winfox.rdp import RDPBrowser


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
RDP_PORT = int(os.environ.get("RDP_PORT", "7000"))
WS_PORT = int(os.environ.get("WS_PORT", "9700"))


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
        ctx1 = await browser.new_context()
        ctx2 = await browser.new_context()
        print("contexts count:", len(browser.contexts()))

        page1 = await ctx1.new_page()
        await page1.goto("https://example.com")
        await page1.wait_for_load_state("load")
        await page1.set_local_storage({"ctx_key": "ctx1"})

        page2 = await ctx2.new_page()
        await page2.goto("https://example.com")
        await page2.wait_for_load_state("load")
        storage2 = await page2.get_local_storage()
        print("ctx2 localStorage before load:", storage2)
        if storage2.get("ctx_key") == "ctx1":
            raise RuntimeError("Context isolation failed before state load")

        state1 = await ctx1.save_state()
        print("ctx1 state origins:", len(state1.get("origins", [])))
        await ctx2.load_state(state1, clear_existing=True)

        page2b = await ctx2.new_page()
        await page2b.goto("https://example.com")
        await page2b.wait_for_load_state("load")
        storage2b = await page2b.get_local_storage()
        print("ctx2 localStorage after load:", storage2b)
        if storage2b.get("ctx_key") != "ctx1":
            raise RuntimeError("Context state load failed")

        print("ctx1 pages:", len(ctx1.pages()))
        print("ctx2 pages:", len(ctx2.pages()))

        await ctx2.close()
        print("contexts after closing ctx2:", len(browser.contexts()))
        if len(browser.contexts()) != 1:
            raise RuntimeError("Context close/unregister failed")

        await ctx1.close()
        print("contexts after closing ctx1:", len(browser.contexts()))
        if len(browser.contexts()) != 0:
            raise RuntimeError("All contexts should be closed")

    print("PASS context smoke test")


if __name__ == "__main__":
    asyncio.run(main())
