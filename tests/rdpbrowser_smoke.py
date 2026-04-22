import asyncio
import os
import tempfile
import traceback
from pathlib import Path

from camoufox.rdp_api import RDPBrowser


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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
        await run_test(reporter, "page.title()", page.title())
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
        await run_test(reporter, "page.text_content(h1)", page.text_content("h1"))
        await run_test(reporter, "page.inner_text(body)", page.inner_text("body"))
        await run_test(reporter, "page.inner_html(body)", page.inner_html("body"))
        await run_test(reporter, "page.all_text_contents(a)", page.all_text_contents("a"))
        await run_test(reporter, "page.all_inner_texts(a)", page.all_inner_texts("a"))
        await run_test(reporter, "page.get_attribute(a, href)", page.get_attribute("a", "href"))
        await run_test(reporter, "page.count(a)", page.count("a"))
        await run_test(reporter, "page.exists(h1)", page.exists("h1"))
        await run_test(reporter, "page.has_selector(body)", page.has_selector("body"))
        await run_test(reporter, "page.is_visible(h1)", page.is_visible("h1"))
        await run_test(reporter, "page.is_hidden(#missing)", page.is_hidden("#missing"))
        await run_test(reporter, "page.wait_for_text(Example Domain)", page.wait_for_text("Example Domain", timeout=5000))
        await run_test(reporter, "page.wait_for_selector_count(a, 1)", page.wait_for_selector_count("a", 1, timeout=5000))
        await run_test(reporter, "page.wait_until_visible(h1)", page.wait_until_visible("h1", timeout=5000))
        await run_test(reporter, "page.wait_for_url(example.com)", page.wait_for_url("example.com", timeout=5000))
        await run_test(reporter, "page.hover(a)", page.hover("a"))
        await run_test(reporter, "page.first(a).text_content()", page.first("a").text_content())
        await run_test(reporter, "page.nth(a, 0).text_content()", page.nth("a", 0).text_content())
        await run_test(reporter, "page.last(a).text_content()", page.last("a").text_content())
        await run_test(reporter, "locator.first().text_content()", page.locator("a").first().text_content())
        await run_test(reporter, "locator.last().text_content()", page.locator("a").last().text_content())
        await run_test(reporter, "locator.nth(0).text_content()", page.locator("a").nth(0).text_content())
        await run_test(reporter, "locator.inner_text()", page.locator("h1").inner_text())
        await run_test(reporter, "locator.exists()", page.locator("h1").exists())
        await run_test(reporter, "locator.is_visible()", page.locator("h1").is_visible())
        await run_test(reporter, "locator.is_hidden()", page.locator("#missing").is_hidden())


async def test_wait_until_hidden(reporter):
    async with await make_browser(21, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await run_test(
            reporter,
            "inject temporary hidden target",
            page.evaluate(
                """
                (() => {
                  const el = document.createElement('div');
                  el.id = 'rdp-hide-test';
                  document.body.appendChild(el);
                  setTimeout(() => el.remove(), 200);
                  return true;
                })()
                """
            ),
        )
        await run_test(
            reporter,
            "page.wait_until_hidden(#rdp-hide-test)",
            page.wait_until_hidden("#rdp-hide-test", timeout=5000),
        )


async def test_file_upload(reporter):
    async with await make_browser(24, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await run_test(
            reporter,
            "inject file input",
            page.evaluate(
                """
                (() => {
                  const input = document.createElement('input');
                  input.type = 'file';
                  input.id = 'rdp-file-input';
                  document.body.appendChild(input);
                  return true;
                })()
                """
            ),
        )

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as handle:
                handle.write("rdpbrowser upload test")
                temp_path = handle.name

            await run_test(
                reporter,
                "page.set_input_files(#rdp-file-input)",
                page.set_input_files("#rdp-file-input", temp_path),
            )
            await run_test(
                reporter,
                "uploaded file count",
                page.evaluate("document.querySelector('#rdp-file-input').files.length"),
            )
            await run_test(
                reporter,
                "uploaded file name",
                page.evaluate("document.querySelector('#rdp-file-input').files[0].name"),
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


async def test_dialogs(reporter):
    async with await make_browser(23, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")

        dialog_future = asyncio.create_task(page.expect_dialog(timeout=5000))
        await page.evaluate("setTimeout(() => alert('RDP alert'), 50); true")
        dialog = await run_test(reporter, "page.expect_dialog(alert)", dialog_future)
        if dialog:
            reporter.add(
                "dialog.type alert",
                "PASS" if dialog.type == "alert" else "FAIL",
                f"type={dialog.type}",
            )
            reporter.add(
                "dialog.message alert",
                "PASS" if dialog.message == "RDP alert" else "FAIL",
                f"message={dialog.message}",
            )
            await run_test(reporter, "dialog.accept(alert)", dialog.accept())
            reporter.add(
                "dialog.state alert",
                "PASS" if dialog.handled and dialog.accepted is True else "FAIL",
                f"handled={dialog.handled} accepted={dialog.accepted} prompt_text={dialog.prompt_text}",
            )

        dialog_future = asyncio.create_task(page.expect_dialog(timeout=5000))
        await page.evaluate("setTimeout(() => confirm('RDP confirm'), 50); true")
        dialog = await run_test(reporter, "page.expect_dialog(confirm)", dialog_future)
        if dialog:
            reporter.add(
                "dialog.type confirm",
                "PASS" if dialog.type == "confirm" else "FAIL",
                f"type={dialog.type}",
            )
            await run_test(reporter, "dialog.dismiss(confirm)", dialog.dismiss())
            reporter.add(
                "dialog.state confirm",
                "PASS" if dialog.handled and dialog.accepted is False else "FAIL",
                f"handled={dialog.handled} accepted={dialog.accepted} prompt_text={dialog.prompt_text}",
            )

        dialog_future = asyncio.create_task(page.expect_dialog(timeout=5000))
        await page.evaluate("setTimeout(() => prompt('RDP prompt', 'default value'), 50); true")
        dialog = await run_test(reporter, "page.expect_dialog(prompt)", dialog_future)
        if dialog:
            reporter.add(
                "dialog.type prompt",
                "PASS" if dialog.type == "prompt" else "FAIL",
                f"type={dialog.type}",
            )
            reporter.add(
                "dialog.default prompt",
                "PASS" if dialog.default_value == "default value" else "FAIL",
                f"default={dialog.default_value}",
            )
            await run_test(reporter, "dialog.accept(prompt)", dialog.accept("typed value"))
            reporter.add(
                "dialog.state prompt",
                "PASS" if dialog.handled and dialog.accepted is True and dialog.prompt_text == "typed value" else "FAIL",
                f"handled={dialog.handled} accepted={dialog.accepted} prompt_text={dialog.prompt_text}",
            )


async def test_input_basic(reporter):
    async with await make_browser(1, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://www.google.com")
        await page.wait_for_load_state("load")
        await run_test(reporter, "wait_for_selector(search box)", page.wait_for_selector('textarea[name="q"]'))
        await run_test(reporter, "page.focus(search box)", page.focus('textarea[name="q"]'))
        await run_test(reporter, "fill(search box)", page.fill('textarea[name="q"]', "hello from RDPBrowser"))
        await asyncio.sleep(1)
        await run_test(reporter, "keyboard.press(Enter)", page.keyboard.press("Enter"))
        await asyncio.sleep(3)
        await page.goto("https://www.google.com")
        await page.wait_for_load_state("load")
        await run_test(reporter, "page.press(search box, Enter)", page.press('textarea[name="q"]', "Enter"))
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


async def test_popup_new_page(reporter):
    async with await make_browser(22, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await run_test(
            reporter,
            "inject popup link",
            page.evaluate(
                """
                (() => {
                  const a = document.createElement('a');
                  a.id = 'rdp-popup-link';
                  a.href = 'https://httpbin.org/html';
                  a.target = '_blank';
                  a.textContent = 'Open popup';
                  document.body.appendChild(a);
                  return true;
                })()
                """
            ),
        )
        existing_pages = browser.list_pages()
        await run_test(reporter, "page.click(#rdp-popup-link)", page.click("#rdp-popup-link"))
        popup = await run_test(
            reporter,
            "browser.wait_for_new_page()",
            browser.wait_for_new_page(timeout=8000, existing_pages=existing_pages),
        )
        if popup:
            await run_test(reporter, "popup wait_for_load_state(load)", popup.wait_for_load_state("load"))
            await run_test(reporter, "popup url", popup.url_fresh())
            active_popup = await browser.get_active_page()
            reporter.add(
                "popup active page consistency",
                "PASS" if active_popup is popup else "PARTIAL",
                f"active_is_popup={active_popup is popup}",
            )

        await run_test(
            reporter,
            "inject second popup link",
            page.evaluate(
                """
                (() => {
                  const a = document.createElement('a');
                  a.id = 'rdp-popup-link-2';
                  a.href = 'https://example.com/?popup=2';
                  a.target = '_blank';
                  a.textContent = 'Open popup 2';
                  document.body.appendChild(a);
                  return true;
                })()
                """
            ),
        )
        popup_future = asyncio.create_task(page.expect_popup(timeout=8000))
        await run_test(reporter, "page.click(#rdp-popup-link-2)", page.click("#rdp-popup-link-2"))
        popup2 = await run_test(reporter, "page.expect_popup()", popup_future)
        if popup2:
            await run_test(reporter, "popup2 wait_for_load_state(load)", popup2.wait_for_load_state("load"))
            await run_test(reporter, "popup2 url", popup2.url_fresh())
            active_popup2 = await browser.get_active_page()
            reporter.add(
                "popup2 active page consistency",
                "PASS" if active_popup2 is popup2 else "PARTIAL",
                f"active_is_popup2={active_popup2 is popup2}",
            )
            await popup2.close()
            opener_url = await page.url_fresh()
            reporter.add(
                "opener survives popup2.close()",
                "PASS" if "example.com" in opener_url else "FAIL",
                opener_url,
            )


async def test_reload_and_cookies(reporter):
    async with await make_browser(3, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        await run_test(reporter, "reload()", page.reload())
        await run_test(reporter, "wait_for_load_state after reload", page.wait_for_load_state("load"))
        await run_test(reporter, "clear_cookies()", page.clear_cookies())


async def test_storage_state(reporter):
    state_file = None
    async with await make_browser(25, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")

        await run_test(
            reporter,
            "page.set_local_storage()",
            page.set_local_storage({"rdp_local_key": "rdp_local_value"}),
        )
        await run_test(reporter, "page.get_local_storage()", page.get_local_storage())

        await run_test(
            reporter,
            "page.set_session_storage()",
            page.set_session_storage({"rdp_session_key": "rdp_session_value"}),
        )
        await run_test(reporter, "page.get_session_storage()", page.get_session_storage())
        page_state = await run_test(reporter, "page.save_storage_state()", page.save_storage_state())
        if isinstance(page_state, dict):
            await run_test(reporter, "page.load_storage_state()", page.load_storage_state(page_state))

        page2 = await browser.new_page()
        await page2.goto("https://httpbin.org/html")
        await page2.wait_for_load_state("load")
        await run_test(
            reporter,
            "page2.set_local_storage()",
            page2.set_local_storage({"rdp_second_origin": "second_value"}),
        )

        await run_test(
            reporter,
            "set document.cookie for state",
            page.evaluate("document.cookie = 'rdp_state_cookie=1; path=/'; true"),
        )

        state = await run_test(reporter, "browser.save_state()", browser.save_state())
        if not isinstance(state, dict):
            reporter.add("browser.save_state() payload", "FAIL", "state is not a dict")
            return
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as handle:
                state_file = handle.name
            saved_path = await run_test(reporter, "browser.save_state_to_file()", browser.save_state_to_file(state_file))
            if isinstance(saved_path, str):
                reporter.add(
                    "saved state file exists",
                    "PASS" if os.path.exists(saved_path) else "FAIL",
                    saved_path,
                )
        except Exception as exc:
            reporter.add("browser.save_state_to_file()", "FAIL", f"{type(exc).__name__}: {exc}")

    async with await make_browser(26, headless=False) as browser2:
        await run_test(reporter, "browser.load_state()", browser2.load_state(state, clear_existing=True))
        page = await browser2.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        local_storage = await run_test(reporter, "loaded page.get_local_storage()", page.get_local_storage())
        cookie_text = await run_test(reporter, "loaded document.cookie", page.evaluate("document.cookie"))
        if isinstance(local_storage, dict):
            reporter.add(
                "loaded localStorage contains key",
                "PASS" if local_storage.get("rdp_local_key") == "rdp_local_value" else "FAIL",
                str(local_storage),
            )
        if isinstance(cookie_text, str):
            reporter.add(
                "loaded cookie contains key",
                "PASS" if "rdp_state_cookie=1" in cookie_text else "FAIL",
                cookie_text,
            )

        page2 = await browser2.new_page()
        await page2.goto("https://httpbin.org/html")
        await page2.wait_for_load_state("load")
        local_storage2 = await run_test(reporter, "loaded page2.get_local_storage()", page2.get_local_storage())
        if isinstance(local_storage2, dict):
            reporter.add(
                "loaded second origin localStorage contains key",
                "PASS" if local_storage2.get("rdp_second_origin") == "second_value" else "FAIL",
                str(local_storage2),
            )

    if state_file:
        async with await make_browser(27, headless=False) as browser3:
            await run_test(reporter, "browser.load_state_from_file()", browser3.load_state_from_file(state_file, clear_existing=True))
            page = await browser3.new_page()
            await page.goto("https://example.com")
            await page.wait_for_load_state("load")
            local_storage = await run_test(reporter, "file loaded page.get_local_storage()", page.get_local_storage())
            if isinstance(local_storage, dict):
                reporter.add(
                    "file loaded localStorage contains key",
                    "PASS" if local_storage.get("rdp_local_key") == "rdp_local_value" else "FAIL",
                    str(local_storage),
                )

        try:
            os.unlink(state_file)
        except OSError:
            pass


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
        requests = []
        responses = []
        finished = []
        failed = []

        def cb(payload):
            called.append(payload)

        def on_request(payload):
            requests.append(payload)

        def on_response(payload):
            responses.append(payload)

        def on_finished(payload):
            finished.append(payload)

        def on_failed(payload):
            failed.append(payload)

        try:
            page.on("load", cb)
            page.on("request", on_request)
            page.on("response", on_response)
            page.on("requestfinished", on_finished)
            page.on("requestfailed", on_failed)
            await page.goto("https://example.com")
            await page.wait_for_load_state("load")
            await asyncio.sleep(2)
            page.remove_listener("load", cb)
            if called:
                reporter.add("page.on/remove_listener", "PASS", f"events={len(called)}")
            else:
                reporter.add("page.on/remove_listener", "PARTIAL", "No callback fired")

            reporter.add(
                'page.on("request")',
                "PASS" if len(requests) > 0 else "FAIL",
                f"events={len(requests)}",
            )
            if requests:
                reporter.add(
                    'request payload keys',
                    "PASS" if all(k in requests[0] for k in ["requestId", "state", "url", "method", "requestBody", "timestamp"]) else "FAIL",
                    str(sorted(requests[0].keys())),
                )
            reporter.add(
                'page.on("response")',
                "PASS" if len(responses) > 0 else "FAIL",
                f"events={len(responses)}",
            )
            if responses:
                reporter.add(
                    'response payload keys',
                    "PASS" if all(k in responses[0] for k in ["requestId", "state", "url", "status", "responseBody", "timestamp"]) else "FAIL",
                    str(sorted(responses[0].keys())),
                )
            reporter.add(
                'page.on("requestfinished")',
                "PASS" if len(finished) > 0 else "FAIL",
                f"events={len(finished)}",
            )
            if finished:
                reporter.add(
                    'requestfinished payload state',
                    "PASS" if finished[0].get("state") == "finished" else "FAIL",
                    str(finished[0].get("state")),
                )
            request_ids = {item.get("requestId") for item in requests if item.get("requestId") is not None}
            response_ids = {item.get("requestId") for item in responses if item.get("requestId") is not None}
            finished_ids = {item.get("requestId") for item in finished if item.get("requestId") is not None}
            common_ids = request_ids & response_ids & finished_ids
            reporter.add(
                'request/response/finished correlation',
                "PASS" if len(common_ids) > 0 else "FAIL",
                f"common_ids={len(common_ids)}",
            )

            await page.evaluate(
                """
                (() => {
                  const img = new Image();
                  img.src = 'http://127.0.0.1:9/rdp-fail.png?' + Date.now();
                  document.body.appendChild(img);
                  return true;
                })()
                """
            )
            await asyncio.sleep(3)
            reporter.add(
                'page.on("requestfailed")',
                "PASS" if len(failed) > 0 else "PARTIAL",
                f"events={len(failed)}",
            )
            if failed:
                reporter.add(
                    'requestfailed payload keys',
                    "PASS" if all(k in failed[0] for k in ["requestId", "state", "url", "error", "timestamp"]) else "FAIL",
                    str(sorted(failed[0].keys())),
                )
                reporter.add(
                    'requestfailed payload state',
                    "PASS" if failed[0].get("state") == "failed" else "FAIL",
                    str(failed[0].get("state")),
                )
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
            pages_before_close = browser.list_pages()
            reporter.add(
                "new_page() multi-page model",
                "PARTIAL" if same or url1 == url2 else "PASS",
                f"same_object={same}, url1={url1}, url2={url2}",
            )
            reporter.add(
                "browser.list_pages() before close",
                "PASS" if len(pages_before_close) >= 2 else "FAIL",
                f"count={len(pages_before_close)}",
            )
            active_page = await browser.get_active_page()
            reporter.add(
                "browser.get_active_page()",
                "PASS" if active_page is page2 else "FAIL",
                f"active_is_page2={active_page is page2}",
            )
            page_by_url = await browser.page_by_url("httpbin.org/html")
            reporter.add(
                "browser.page_by_url(httpbin)",
                "PASS" if page_by_url is page2 else "FAIL",
                f"matched_page2={page_by_url is page2}",
            )
            pages_by_url = await browser.pages_by_url("http")
            reporter.add(
                "browser.pages_by_url(http)",
                "PASS" if len(pages_by_url) >= 2 else "FAIL",
                f"count={len(pages_by_url)}",
            )
            reporter.add(
                "page2.is_active()",
                "PASS" if await page2.is_active() else "FAIL",
                f"page2_active={await page2.is_active()}",
            )
            await page2.close()
            pages_after_close = browser.list_pages()
            reporter.add(
                "page.close()",
                "PASS" if page2.is_closed() else "FAIL",
                f"page2_closed={page2.is_closed()}",
            )
            reporter.add(
                "browser.list_pages() after close",
                "PASS" if len(pages_after_close) == 1 else "FAIL",
                f"count={len(pages_after_close)}",
            )
            url1_after_close = await page1.url_fresh()
            reporter.add(
                "page1 survives page2.close()",
                "PASS" if url1_after_close == url1 else "FAIL",
                f"before={url1}, after={url1_after_close}",
            )
            await page1.bring_to_front()
            active_page_after = await browser.get_active_page()
            reporter.add(
                "browser.get_active_page() after bring_to_front",
                "PASS" if active_page_after is page1 else "FAIL",
                f"active_is_page1={active_page_after is page1}",
            )
            reporter.add(
                "page1.is_active()",
                "PASS" if await page1.is_active() else "FAIL",
                f"page1_active={await page1.is_active()}",
            )
            page3 = await browser.new_page()
            await page3.goto("https://example.com/?page=3")
            await page3.wait_for_load_state("load")
            reporter.add(
                "browser.close_all_pages() pre-count",
                "PASS",
                f"count={len(browser.list_pages())}",
            )
            await browser.close_other_pages(page1)
            reporter.add(
                "browser.close_other_pages(page1)",
                "PASS" if len(browser.list_pages()) == 1 and browser.list_pages()[0] is page1 else "FAIL",
                f"count={len(browser.list_pages())}",
            )
            await page1.goto("https://example.com/?page=kept")
            await page1.wait_for_load_state("load")
            await browser.close_all_pages()
            reporter.add(
                "browser.close_all_pages()",
                "PASS" if len(browser.list_pages()) == 0 else "FAIL",
                f"count={len(browser.list_pages())}",
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
    await test_wait_until_hidden(reporter)
    await test_file_upload(reporter)
    await test_dialogs(reporter)
    await test_input_basic(reporter)
    await test_click_and_locator_click(reporter)
    await test_popup_new_page(reporter)
    await test_reload_and_cookies(reporter)
    await test_storage_state(reporter)
    await test_network(reporter)
    await test_memory_and_gc(reporter)
    await test_window_helpers(reporter)
    await test_multi_instance(reporter)
    await test_event_api(reporter)
    await test_new_page_model(reporter)
    reporter.summary()


if __name__ == "__main__":
    asyncio.run(main())
