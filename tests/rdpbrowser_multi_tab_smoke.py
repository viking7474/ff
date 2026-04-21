import asyncio
import os
from pathlib import Path

from camoufox.rdp_api import RDPBrowser


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
RDP_PORT = int(os.environ.get("RDP_PORT", "6200"))
WS_PORT = int(os.environ.get("WS_PORT", "8900"))


def print_step(name: str, detail: str = "") -> None:
    print(f"[STEP] {name}")
    if detail:
        print(f"       {detail}")


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
        print_step("launch browser")

        page1 = await browser.new_page()
        await page1.goto("https://example.com")
        await page1.wait_for_load_state("load")
        title1 = await page1.evaluate("document.title")
        print_step("page1 ready", f"title={title1!r}, url={await page1.url_fresh()}")

        page2 = await browser.new_page()
        await page2.goto("https://httpbin.org/html")
        await page2.wait_for_load_state("load")
        title2 = await page2.evaluate("document.title")
        print_step("page2 ready", f"title={title2!r}, url={await page2.url_fresh()}")

        pages = browser.list_pages()
        print_step("list_pages() after two tabs", f"count={len(pages)}")
        for index, page in enumerate(pages, start=1):
            print(f"       page{index}: closed={page.is_closed()} url={await page.url_fresh()}")

        await page1.bring_to_front()
        await asyncio.sleep(1)
        await page1.screenshot("multi_tab_page1.png")
        print_step("page1.bring_to_front()", "saved multi_tab_page1.png")

        await page2.bring_to_front()
        await asyncio.sleep(1)
        await page2.screenshot("multi_tab_page2.png")
        print_step("page2.bring_to_front()", "saved multi_tab_page2.png")

        url1_before_close = await page1.url_fresh()
        await page2.close()
        print_step("page2.close()", f"page2.is_closed()={page2.is_closed()}")

        pages_after_close = browser.list_pages()
        print_step("list_pages() after close", f"count={len(pages_after_close)}")
        for index, page in enumerate(pages_after_close, start=1):
            print(f"       page{index}: closed={page.is_closed()} url={await page.url_fresh()}")

        url1_after_close = await page1.url_fresh()
        print_step(
            "page1 still alive after page2 close",
            f"before={url1_before_close} after={url1_after_close}",
        )

        if len(pages) < 2:
            raise RuntimeError("Expected at least 2 pages after opening second tab")
        if len(pages_after_close) != 1:
            raise RuntimeError("Expected exactly 1 page after closing page2")
        if page1.is_closed():
            raise RuntimeError("page1 should remain open after closing page2")
        if not page2.is_closed():
            raise RuntimeError("page2 should be closed after page2.close()")
        if url1_before_close != url1_after_close:
            raise RuntimeError("page1 URL changed unexpectedly after closing page2")

        print("\nPASS multi-tab management smoke test")


if __name__ == "__main__":
    asyncio.run(main())
