import asyncio
import os
from pathlib import Path

from winfox.rdp import RDPBrowser


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
ROUNDS = int(os.environ.get("STRESS_ROUNDS", "5"))
TABS_PER_ROUND = int(os.environ.get("TABS_PER_ROUND", "3"))
RDP_PORT = int(os.environ.get("RDP_PORT", "6600"))
WS_PORT = int(os.environ.get("WS_PORT", "9300"))


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
        for round_index in range(ROUNDS):
            print(f"[ROUND {round_index + 1}/{ROUNDS}] opening {TABS_PER_ROUND} tabs")
            pages = []
            for tab_index in range(TABS_PER_ROUND):
                page = await browser.new_page()
                await page.goto(f"https://example.com/?round={round_index}&tab={tab_index}")
                await page.wait_for_load_state("load")
                pages.append(page)

            live_pages = browser.list_pages()
            print(f"  list_pages() after open: {len(live_pages)}")
            if len(live_pages) < TABS_PER_ROUND:
                raise RuntimeError("Page registry count is lower than expected after opening tabs")

            for page in reversed(pages):
                await page.bring_to_front()
                await asyncio.sleep(0.2)
                await page.close()

            remaining = browser.list_pages()
            print(f"  list_pages() after close: {len(remaining)}")
            if remaining:
                raise RuntimeError("Expected all stress-test tabs to be closed")

    print(f"PASS multi-tab stress rounds={ROUNDS} tabs={TABS_PER_ROUND}")


if __name__ == "__main__":
    asyncio.run(main())
