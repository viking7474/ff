import asyncio
import os
from pathlib import Path

from camoufox.rdp_api import RDPBrowser


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
RDP_PORT = int(os.environ.get("RDP_PORT", "6900"))
WS_PORT = int(os.environ.get("WS_PORT", "9600"))


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
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")

        await page.evaluate(
            """
            (() => {
              const f1 = document.createElement('iframe');
              f1.name = 'sameOriginFrame';
              f1.srcdoc = '<html><body><h1>Frame One</h1><a href="javascript:void(0)" id="frame-link">Link</a><input id="frame-input" /><script>window.__frameClicked=false; document.addEventListener("click", e => { if (e.target && e.target.id === "frame-link") window.__frameClicked = true; });</script></body></html>';
              document.body.appendChild(f1);

              const f2 = document.createElement('iframe');
              f2.name = 'crossOriginFrame';
              f2.src = 'https://httpbin.org/html';
              document.body.appendChild(f2);
              return true;
            })()
            """
        )
        await asyncio.sleep(2)

        frames = await page.frames()
        print("frames count:", len(frames))
        for frame in frames:
            print(
                {
                    "index": frame.index,
                    "name": frame.name,
                    "src": frame.src,
                    "url": frame.url,
                    "same_origin": frame.same_origin,
                }
            )

        frame0 = await page.frame(index=0)
        if not frame0:
            raise RuntimeError("Failed to resolve frame by index")
        print("frame0 text:", await frame0.text_content("h1"))
        print("frame0 inner_text:", await frame0.inner_text("body"))
        print("frame0 inner_html:", await frame0.inner_html("body"))
        print("frame0 count(a):", await frame0.count("a"))
        print("frame0 exists(h1):", await frame0.exists("h1"))
        print("frame0 is_visible(h1):", await frame0.is_visible("h1"))
        print("frame0 is_hidden(#missing):", await frame0.is_hidden("#missing"))
        print("frame0 wait_for_selector(h1):", await frame0.wait_for_selector("h1"))
        print("frame0 wait_for_text(Frame One):", await frame0.wait_for_text("Frame One"))
        print("frame0 evaluate(document.body.innerText):", await frame0.evaluate("document.body.innerText"))
        await frame0.hover("#frame-link")
        print("frame0 hover(#frame-link): ok")
        await frame0.click("#frame-link")
        print("frame0 click(#frame-link):", await frame0.evaluate("window.__frameClicked"))
        await frame0.focus("#frame-input")
        print("frame0 focus(#frame-input):", await frame0.evaluate("document.activeElement && document.activeElement.id"))
        await frame0.press("#frame-input", "A")
        print("frame0 press(#frame-input, A):", await frame0.evaluate("document.querySelector('#frame-input').value"))
        floc = frame0.locator("a")
        await floc.wait_for()
        print("frame locator text_content:", await floc.text_content())
        print("frame locator inner_text:", await floc.inner_text())
        print("frame locator get_attribute(href):", await floc.get_attribute("href"))
        print("frame locator count:", await floc.count())
        print("frame locator exists:", await floc.exists())
        print("frame locator is_visible:", await floc.is_visible())
        print("frame locator is_hidden(#missing):", await frame0.locator("#missing").is_hidden())
        print("frame locator first text:", await frame0.locator("a").first().text_content())
        print("frame locator nth(0) text:", await frame0.locator("a").nth(0).text_content())
        print("frame locator last text:", await frame0.locator("a").last().text_content())
        await frame0.locator("#frame-link").hover()
        print("frame locator hover(#frame-link): ok")
        await frame0.locator("#frame-link").click()
        print("frame locator click(#frame-link):", await frame0.evaluate("window.__frameClicked"))
        await frame0.locator("#frame-input").focus()
        print("frame locator focus(#frame-input):", await frame0.evaluate("document.activeElement && document.activeElement.id"))
        await frame0.locator("#frame-input").press("B")
        print("frame locator press(#frame-input, B):", await frame0.evaluate("document.querySelector('#frame-input').value"))

        named = await page.frame(name="sameOriginFrame")
        if not named or named.name != "sameOriginFrame":
            raise RuntimeError("Failed to resolve frame by name")

        cross = await page.frame(name="crossOriginFrame")
        if not cross:
            raise RuntimeError("Failed to resolve cross-origin frame metadata")
        if cross.same_origin:
            raise RuntimeError("Cross-origin frame was incorrectly marked same-origin")

        try:
            await cross.text_content("body")
        except RuntimeError as exc:
            print("cross-origin access error:", exc)
        else:
            raise RuntimeError("Cross-origin frame access should have failed")

        try:
            await cross.is_visible("body")
        except RuntimeError as exc:
            print("cross-origin visibility error:", exc)
        else:
            raise RuntimeError("Cross-origin visibility access should have failed")

    print("PASS frame smoke test")


if __name__ == "__main__":
    asyncio.run(main())
