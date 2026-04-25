import asyncio
import os
from pathlib import Path

from camoufox.rdp_api import RDPBrowser


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
ROUNDS = int(os.environ.get("STRESS_ROUNDS", "5"))
CONTEXTS_PER_ROUND = int(os.environ.get("CONTEXTS_PER_ROUND", "3"))
RDP_PORT = int(os.environ.get("RDP_PORT", "7100"))
WS_PORT = int(os.environ.get("WS_PORT", "9800"))


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
            print(f"[ROUND {round_index + 1}/{ROUNDS}] creating {CONTEXTS_PER_ROUND} contexts")
            contexts = []
            for ctx_index in range(CONTEXTS_PER_ROUND):
                ctx = await browser.new_context()
                contexts.append(ctx)
                page = await ctx.new_page()
                await page.goto("https://example.com")
                await page.wait_for_load_state("load")
                await page.set_local_storage({"ctx_key": f"round{round_index}-ctx{ctx_index}"})

            print("  active contexts:", len(browser.contexts()))
            if len(browser.contexts()) != CONTEXTS_PER_ROUND:
                raise RuntimeError("Context count mismatch after creation")

            # Save/load state between contexts in the same round.
            base_state = await contexts[0].save_state()
            for ctx in contexts[1:]:
                await ctx.load_state(base_state, clear_existing=True)

            for ctx_index, ctx in enumerate(contexts):
                page = await ctx.new_page()
                await page.goto("https://example.com")
                await page.wait_for_load_state("load")
                storage = await page.get_local_storage()
                print(f"  ctx{ctx_index} storage keys:", sorted(storage.keys()))

            for ctx in reversed(contexts):
                await ctx.close()

            print("  active contexts after close:", len(browser.contexts()))
            if browser.contexts():
                raise RuntimeError("Contexts should all be closed after round")

    print(f"PASS context stress rounds={ROUNDS} contexts={CONTEXTS_PER_ROUND}")


if __name__ == "__main__":
    asyncio.run(main())
