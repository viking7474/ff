import asyncio
import os
import traceback
from pathlib import Path

from camoufox.rdp_api import RDPBrowser


WINFOX_PATH = os.environ.get("WINFOX_PATH", "")
TEST_RDP_PORT_BASE = int(os.environ.get("RDP_PORT_BASE", "6100"))
TEST_WS_PORT_BASE = int(os.environ.get("WS_PORT_BASE", "8800"))


class Reporter:
    def __init__(self):
        self.results = []

    def add(self, name, status, detail=""):
        self.results.append((name, status, detail))
        print(f"[{status}] {name}")
        if detail:
            print(f"      {detail}")

    def summary(self):
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        for name, status, detail in self.results:
            print(f"{status:5}  {name}")
            if detail:
                print(f"       {detail}")


async def run_test(reporter, name, coro):
    try:
        result = await coro
        reporter.add(name, "PASS", str(result) if result is not None else "")
        return result
    except NotImplementedError as exc:
        reporter.add(name, "SKIP", str(exc))
    except Exception as exc:
        reporter.add(name, "FAIL", f"{type(exc).__name__}: {exc}")
        traceback.print_exc()


async def make_browser(idx=0, headless=False):
    return RDPBrowser(
        executable_path=WINFOX_PATH,
        headless=headless,
        rdp_port=TEST_RDP_PORT_BASE + idx,
        ws_port=TEST_WS_PORT_BASE + idx,
    )


async def test_single_core(reporter):
    async with await make_browser(0, headless=False) as browser:
        page = await browser.new_page()
        await run_test(reporter, "goto example.com", page.goto("https://example.com"))
        await run_test(reporter, "wait_for_load_state(load)", page.wait_for_load_state("load"))
        await run_test(reporter, "evaluate document.title", page.evaluate("document.title"))
        await run_test(reporter, "content()", page.content())
        await run_test(reporter, "screenshot()", page.screenshot("core_single.png"))
        await run_test(reporter, "page.url_fresh()", page.url_fresh())


async def test_selectors(reporter):
    async with await make_browser(20, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await run_test(reporter, "wait_for_selector(body)", page.wait_for_selector("body"))
        await run_test(reporter, "query_selector(h1)", page.query_selector("h1"))
        await run_test(reporter, "query_selector_all(a)", page.query_selector_all("a"))
        locator = page.locator("h1")
        await run_test(reporter, "locator.wait_for()", locator.wait_for())
        await run_test(reporter, "locator.text_content()", locator.text_content())
        await run_test(reporter, "locator.get_attribute(class)", locator.get_attribute("class"))
        await run_test(reporter, "locator.count()", locator.count())


async def test_input_basic(reporter):
    async with await make_browser(1, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://www.google.com")
        await page.wait_for_load_state("load")
        await run_test(reporter, "wait_for_selector(search box)", page.wait_for_selector('textarea[name="q"]'))
        await run_test(reporter, "fill(search box)", page.fill('textarea[name="q"]', "hello from RDPBrowser"))
        await asyncio.sleep(1)
        await run_test(reporter, "keyboard.press(Enter)", page.keyboard.press("Enter"))
        await asyncio.sleep(3)
        await run_test(reporter, "screenshot(input)", page.screenshot("input_test.png"))
        await run_test(reporter, "mouse.move_smooth()", page.mouse.move_smooth(400, 300))
        await run_test(reporter, "mouse.wheel_smooth()", page.mouse.wheel_smooth(600))


async def test_click_and_locator_click(reporter):
    async with await make_browser(2, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await run_test(reporter, "page.click(a)", page.click("a"))
        await asyncio.sleep(2)
        await run_test(reporter, "url after page.click(a)", page.url_fresh())
        await page.goto("https://example.com")
        loc = page.locator("a")
        await run_test(reporter, "locator.click()", loc.click())
        await asyncio.sleep(2)
        await run_test(reporter, "url after locator.click()", page.url_fresh())


async def test_reload_and_cookies(reporter):
    async with await make_browser(3, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await run_test(reporter, "reload()", page.reload())
        await run_test(reporter, "wait_for_load_state after reload", page.wait_for_load_state("load"))
        await run_test(reporter, "clear_cookies()", page.clear_cookies())


async def test_network(reporter):
    print("\n=== network ===")
    async with await make_browser(4, headless=False) as browser:
        page = await browser.new_page()
        await run_test(reporter, "start_capture()", page.start_capture(["example.com"]))
        await run_test(reporter, "start_spy()", page.start_spy(["example.com"]))
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await asyncio.sleep(2)
        matched = await run_test(reporter, "wait_for_response(example.com)", page.wait_for_response("example.com", timeout=5))
        responses = await run_test(reporter, "get_captured_responses(clear=False)", page.get_captured_responses(clear=False))
        requests = await run_test(reporter, "get_spied_requests()", page.get_spied_requests())
        if isinstance(matched, dict):
            reporter.add("matched response found", "PASS", matched.get("url", ""))
        if isinstance(responses, list):
            reporter.add("captured response count > 0", "PASS" if len(responses) > 0 else "FAIL", str(len(responses)))
            if responses:
                reporter.add("first response keys", "PASS", str(list(responses[0].keys())))
        if isinstance(requests, list):
            reporter.add("spied request count > 0", "PASS" if len(requests) > 0 else "FAIL", str(len(requests)))
            if requests:
                reporter.add("first request keys", "PASS", str(list(requests[0].keys())))
        await run_test(reporter, "stop_capture()", page.stop_capture())
        await run_test(reporter, "stop_spy()", page.stop_spy())


async def test_memory_and_gc(reporter):
    async with await make_browser(5, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await run_test(reporter, "memory_usage()", page.memory_usage())
        await run_test(reporter, "force_gc()", page.force_gc())


async def test_window_helpers(reporter):
    async with await make_browser(6, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await run_test(reporter, "simulate_tab_switch()", page.simulate_tab_switch())
        await run_test(reporter, "screenshot(window helpers)", page.screenshot("window_helpers.png"))


async def test_multi_instance(reporter):
    async def one(idx, url, path):
        async with await make_browser(idx, headless=False) as browser:
            page = await browser.new_page()
            await page.goto(url)
            await page.wait_for_load_state("load")
            title = await page.evaluate("document.title")
            await page.screenshot(path)
            return title

    try:
        title_a, title_b = await asyncio.gather(
            one(10, "https://example.com", "multi_a.png"),
            one(11, "https://httpbin.org/html", "multi_b.png"),
        )
        reporter.add("multi-instance run", "PASS", f"A={title_a!r}, B={title_b!r}")
    except Exception as exc:
        reporter.add("multi-instance run", "FAIL", f"{type(exc).__name__}: {exc}")
        traceback.print_exc()


async def test_event_api(reporter):
    async with await make_browser(12, headless=False) as browser:
        page = await browser.new_page()
        called = []

        def cb(payload):
            called.append(payload)

        try:
            page.on("load", cb)
            await page.goto("https://example.com")
            await page.wait_for_load_state("load")
            page.remove_listener("load", cb)
            if called:
                reporter.add("page.on/remove_listener", "PASS", f"events={len(called)}")
            else:
                reporter.add("page.on/remove_listener", "PARTIAL", "No callback fired")
        except Exception as exc:
            reporter.add("page.on/remove_listener", "FAIL", f"{type(exc).__name__}: {exc}")


async def test_new_page_model(reporter):
    async with await make_browser(13, headless=False) as browser:
        page1 = await browser.new_page()
        await page1.goto("https://example.com")
        await page1.wait_for_load_state("load")
        try:
            page2 = await browser.new_page()
            await page2.goto("https://httpbin.org/html")
            await page2.wait_for_load_state("load")
            url1 = await page1.url_fresh()
            url2 = await page2.url_fresh()
            same = page1 is page2
            reporter.add(
                "new_page() multi-page model",
                "PARTIAL" if same or url1 == url2 else "PASS",
                f"same_object={same}, url1={url1}, url2={url2}",
            )
        except Exception as exc:
            reporter.add("new_page() multi-page model", "FAIL", f"{type(exc).__name__}: {exc}")


async def main():
    if not WINFOX_PATH:
        raise RuntimeError("Set WINFOX_PATH to the built Winfox executable path")
    if not Path(WINFOX_PATH).exists():
        raise FileNotFoundError(f"WINFOX_PATH not found: {WINFOX_PATH}")

    reporter = Reporter()
    print("Starting RDPBrowser manual smoke suite...")

    try:
        async with await make_browser(99, headless=False) as browser:
            page = await browser.new_page()
            await run_test(reporter, "sanity goto", page.goto("https://example.com"))
            await run_test(reporter, "sanity title", page.evaluate("document.title"))
    except Exception:
        reporter.add("sanity bootstrap", "FAIL", "Basic browser start/new_page failed")
        reporter.summary()
        return

    await test_single_core(reporter)
    await test_selectors(reporter)
    await test_input_basic(reporter)
    await test_click_and_locator_click(reporter)
    await test_reload_and_cookies(reporter)
    await test_network(reporter)
    await test_memory_and_gc(reporter)
    await test_window_helpers(reporter)
    await test_multi_instance(reporter)
    await test_event_api(reporter)
    await test_new_page_model(reporter)
    reporter.summary()


if __name__ == "__main__":
    asyncio.run(main())
