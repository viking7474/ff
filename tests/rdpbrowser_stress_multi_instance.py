import asyncio
import os
from pathlib import Path

from winfox.rdp import RDPBrowser


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
ROUNDS = int(os.environ.get("STRESS_ROUNDS", "5"))
WORKERS = int(os.environ.get("STRESS_WORKERS", "3"))
RDP_PORT_BASE = int(os.environ.get("RDP_PORT_BASE", "6500"))
WS_PORT_BASE = int(os.environ.get("WS_PORT_BASE", "9200"))
URLS = [
    "https://example.com",
    "https://httpbin.org/html",
    "https://example.com/?worker=3",
]


async def worker(round_index: int, worker_index: int) -> str:
    rdp_port = RDP_PORT_BASE + round_index * 10 + worker_index
    ws_port = WS_PORT_BASE + round_index * 10 + worker_index
    url = URLS[worker_index % len(URLS)]
    async with RDPBrowser(
        executable_path=WINFOX_PATH,
        headless=False,
        rdp_port=rdp_port,
        ws_port=ws_port,
    ) as browser:
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_load_state("load")
        return await page.url_fresh()


async def main() -> None:
    if not WINFOX_PATH:
        raise RuntimeError("Set WINFOX_PATH to the built Winfox executable path")
    if not Path(WINFOX_PATH).exists():
        raise FileNotFoundError(f"WINFOX_PATH not found: {WINFOX_PATH}")

    for round_index in range(ROUNDS):
        print(f"[ROUND {round_index + 1}/{ROUNDS}] starting {WORKERS} workers")
        results = await asyncio.gather(
            *(worker(round_index, worker_index) for worker_index in range(WORKERS))
        )
        for worker_index, result in enumerate(results, start=1):
            print(f"  worker{worker_index}: {result}")
        await asyncio.sleep(1)

    print(f"PASS multi-instance stress rounds={ROUNDS} workers={WORKERS}")


if __name__ == "__main__":
    asyncio.run(main())
