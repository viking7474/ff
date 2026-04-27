import asyncio
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pythonlib"))

from winfox.rdp import RDPBrowser


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
ITERATIONS = int(os.environ.get("STRESS_ITERATIONS", "5"))
RDP_PORT = int(os.environ.get("RDP_PORT", "6700"))
WS_PORT = int(os.environ.get("WS_PORT", "9400"))


def port_is_open(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def port_can_bind(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


async def main() -> None:
    if not WINFOX_PATH:
        raise RuntimeError("Set WINFOX_PATH to the built Winfox executable path")
    if not Path(WINFOX_PATH).exists():
        raise FileNotFoundError(f"WINFOX_PATH not found: {WINFOX_PATH}")

    for index in range(ITERATIONS):
        print(f"[ITER {index + 1}/{ITERATIONS}] start/stop with fixed ports")
        async with RDPBrowser(
            executable_path=WINFOX_PATH,
            headless=False,
            rdp_port=RDP_PORT,
            ws_port=WS_PORT,
        ) as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")
            await page.wait_for_load_state("load")
            print(f"  live ports: rdp={port_is_open(RDP_PORT)} ws={port_is_open(WS_PORT)}")

        await asyncio.sleep(1)
        rdp_bindable = port_can_bind(RDP_PORT)
        ws_bindable = port_can_bind(WS_PORT)
        print(f"  bindable after close: rdp={rdp_bindable} ws={ws_bindable}")
        if not rdp_bindable or not ws_bindable:
            raise RuntimeError("Port reuse check failed after browser shutdown")

    print(f"PASS windows cleanup and port reuse x{ITERATIONS}")


if __name__ == "__main__":
    asyncio.run(main())
