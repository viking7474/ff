# RDPBrowser

`RDPBrowser` is the Firefox RDP-based automation path for Winfox.

It is designed for stealth-first automation without relying on Playwright/Juggler as the primary runtime transport.

In this repository, `RDPBrowser` should be treated as the primary Python automation path.

## Architecture

`RDPBrowser` uses three layers:

1. Firefox RDP for browser and target control
2. A temporary WebExtension for bridge commands, proxy auth, and network capture
3. An experiment API for trusted-like input and navigation helpers

Flow:

```text
Python controller
-> geckordp / Firefox RDP
-> extension websocket bridge
-> nativeInput experiment API
-> Firefox tab/window
```

## What It Is Good At

`RDPBrowser` currently works well for:

1. Launching Winfox with an isolated profile
2. Navigating pages and evaluating JavaScript
3. Trusted-like mouse and keyboard input
4. Response capture and request spying through the extension layer
5. Running multiple Winfox instances in parallel with separate ports
6. Basic multi-tab handling via `new_page()` in the same window

## What It Is Not

`RDPBrowser` is not a drop-in replacement for the full Playwright/Juggler protocol surface.

Treat it as:

1. A stealth-first automation backend
2. A single-controller Python API with practical browser operations
3. A path that minimizes dependence on deep Juggler bootstrap patches

## Requirements

The Python environment must have:

1. Local `camoufox` package from `pythonlib/`
2. `geckordp`
3. `websockets`

Example installation:

```bash
python -m pip install -e ./pythonlib
python -m pip install geckordp websockets
```

## Minimal Example

```python
import asyncio

from camoufox.rdp_api import RDPBrowser


async def main():
    async with RDPBrowser(
        executable_path=r"C:\path\to\winfox.exe",
        headless=False,
        rdp_port=6000,
        ws_port=8775,
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
        print(await page.title())
        print(await page.text_content("h1"))
        await page.screenshot("rdp_example.png")


asyncio.run(main())
```

## Multi-Tab Example

```python
import asyncio

from camoufox.rdp_api import RDPBrowser


async def main():
    async with RDPBrowser(
        executable_path=r"C:\path\to\winfox.exe",
        headless=False,
        rdp_port=6000,
        ws_port=8775,
    ) as browser:
        page1 = await browser.new_page()
        await page1.goto("https://example.com")

        page2 = await browser.new_page()
        await page2.goto("https://httpbin.org/html")

        print(len(browser.list_pages()))
        print(await browser.get_active_page() is page2)

        await page1.bring_to_front()
        print(await page1.is_active())
        await page2.close()
        await browser.close_all_pages()


asyncio.run(main())
```

## API Overview

### Browser methods

1. `await browser.new_page()`
Creates a new controllable page. The first call binds the startup tab; later calls create new tabs in the same window.

2. `browser.list_pages()`
Returns the currently tracked live `RDPPage` objects.

3. `await browser.get_active_page()`
Returns the currently active tracked page, if the extension bridge can resolve the active tab.

4. `await browser.page_by_url(pattern)`
Finds the first tracked page whose current URL contains `pattern`.

5. `await browser.pages_by_url(pattern)`
Returns all tracked pages whose current URL contains `pattern`.

6. `await browser.close_other_pages(page)`
Closes every tracked page except the one you keep.

7. `await browser.close_all_pages()`
Closes all tracked pages and clears the page registry.

8. `await browser.wait_for_new_page(timeout=5000)`
Waits for a newly opened page or tab to appear in the browser registry.

### Page navigation and state

1. `await page.goto(url)`
Navigate to a URL.

2. `await page.reload()`
Reload the current page.

3. `await page.wait_for_load_state(state)`
Wait for `load` or `domcontentloaded` style readiness.

4. `await page.wait_for_url(pattern)`
Wait until the current URL contains a substring.

5. `await page.title()`
Return `document.title`.

6. `await page.url_fresh()`
Return the latest URL by querying the page directly.

### Page DOM helpers

1. `await page.text_content(selector)`
Return the matched element's text content.

2. `await page.inner_text(selector)`
Return the matched element's rendered inner text.

3. `await page.inner_html(selector)`
Return the matched element's `innerHTML`.

4. `await page.all_text_contents(selector)`
Return text content for all matched elements.

5. `await page.get_attribute(selector, name)`
Return the matched element's attribute value.

6. `await page.count(selector)`
Return the number of matched elements.

7. `await page.exists(selector)`
Return `True` if at least one matching element exists.

8. `await page.has_selector(selector)`
Alias for `exists(selector)`.

9. `await page.is_visible(selector)`
Return whether the selector currently resolves to a visible element.

10. `await page.is_hidden(selector)`
Return whether the selector is currently hidden or absent.

11. `await page.wait_for_text(text)`
Wait until `document.body.innerText` contains the given text.

12. `await page.wait_for_selector_count(selector, n)`
Wait until a selector matches exactly `n` elements.

13. `await page.wait_until_hidden(selector)`
Wait until a selector disappears or becomes hidden.

14. `await page.wait_until_visible(selector)`
Wait until a selector becomes visible.

15. `await page.wait_for_selector(selector)`
Wait until the selector is present/visible under the current implementation's rules.

### Page interaction helpers

1. `await page.click(selector)`
Click an element by selector.

2. `await page.hover(selector)`
Move the mouse to the selector's visible center.

3. `await page.focus(selector)`
Focus the matched element.

4. `await page.press(selector, key)`
Focus the selector and press a keyboard key.

5. `await page.set_input_files(selector, paths)`
Populate a file input with one or more local files through the current practical file-upload path.

6. `await page.fill(selector, text)`
Clear the element and type text through the trusted bridge path.

7. `await page.bring_to_front()`
Activate the page's tab.

8. `await page.close()`
Close the page's tab and unregister it.

9. `await page.is_active()`
Return whether this page currently owns the active tab.

10. `page.is_closed()`
Return whether the page has been disposed/closed.

10. `await page.expect_dialog(timeout=5000)`
Wait for the next practical dialog observed by the page's dialog shim.

11. `await dialog.accept(prompt_text=None)` / `await dialog.dismiss()`
Handle a detected `alert`, `confirm`, or `prompt` through the current practical dialog layer.

### Network and diagnostics

1. `await page.start_capture(patterns)` / `await page.get_captured_responses()`
Capture response bodies matching URL patterns.

2. `await page.start_spy(patterns)` / `await page.get_spied_requests()`
Capture request metadata and response bodies for matching URLs.

3. `await page.wait_for_response(pattern)`
Wait until a captured response appears.

4. `page.on("request", callback)` / `page.on("response", callback)`
Receive practical request/response events built on top of the bridge spy/capture layer.

5. `page.on("requestfinished", callback)` / `page.on("requestfailed", callback)`
Receive best-effort completion/failure events for observed requests.

6. `await page.memory_usage()`
Read the current tab's memory metrics.

7. `await page.force_gc()`
Force GC and cycle collection for the current tab.

## Storage and State

1. `await page.get_local_storage()`
Read the current page's `localStorage` entries as a dictionary.

2. `await page.set_local_storage(data)`
Set one or more `localStorage` entries on the current page.

3. `await page.get_session_storage()`
Read the current page's `sessionStorage` entries as a dictionary.

4. `await page.set_session_storage(data)`
Set one or more `sessionStorage` entries on the current page.

5. `await browser.save_state()`
Return a practical reusable state object containing cookies and `localStorage` grouped by origin.

6. `await browser.load_state(state)`
Restore cookies and per-origin `localStorage` from a saved state object.

## Multi-Instance Usage

Multiple Winfox profiles can run at once as long as each instance gets:

1. A unique `rdp_port`
2. A unique `ws_port`
3. A separate `profile_path`, or let `RDPBrowser` create one

Recommended model:

1. One `RDPBrowser` instance per browser/profile
2. One main controlled page per worker or task group

## Dialog Handling Notes

`RDPBrowser` dialog support is currently implemented as a practical JavaScript shim for:

1. `alert`
2. `confirm`
3. `prompt`

This is useful for automation flows and smoke validation, but it is not yet native browser dialog parity.

## File Upload Notes

`RDPBrowser` currently supports a practical file-upload path through:

1. `await page.set_input_files(selector, paths)`

Current scope:

1. targets `<input type="file">`
2. creates `File` objects in page context
3. dispatches `input` and `change`

Current limitations:

1. this is not native file chooser parity
2. `wait_for_file_chooser()` is not part of the current supported surface

## State Notes

`save_state()` and `load_state()` currently focus on:

1. cookies
2. per-origin `localStorage`

`sessionStorage` helpers exist at page level, but are not yet treated as portable browser-wide state parity.

## Official Smoke Suite

An official manual smoke suite lives at:

`tests/rdpbrowser_smoke.py`

Run it with:

```bash
set WINFOX_PATH=C:\path\to\winfox.exe
python tests/rdpbrowser_smoke.py
```

Or in PowerShell:

```powershell
$env:WINFOX_PATH = 'C:\path\to\winfox.exe'
python tests/rdpbrowser_smoke.py
```

The smoke suite validates:

1. Launch and navigation
2. Selectors and locator operations
3. Input and scrolling
4. Screenshots
5. Response capture and request spying
6. Multi-instance execution
7. Minimal event support
8. Multi-page tab attachment

## Stress Scripts

The repo also includes focused stress scripts:

1. `tests/rdpbrowser_stress_launch_close.py`
2. `tests/rdpbrowser_stress_multi_instance.py`
3. `tests/rdpbrowser_stress_multi_tab.py`
4. `tests/rdpbrowser_windows_cleanup_check.py`

Use them to validate repeated runs, multi-instance behavior, multi-tab lifecycle, and Windows cleanup/port reuse.

Example:

```bash
set WINFOX_PATH=C:\path\to\winfox.exe
python tests\rdpbrowser_stress_launch_close.py
python tests\rdpbrowser_stress_multi_instance.py
python tests\rdpbrowser_stress_multi_tab.py
python tests\rdpbrowser_windows_cleanup_check.py
```

## Supported Surface

See `docs/rdpbrowser_v1_capability_matrix.md` for the current supported surface and maturity levels.

## Vietnamese Reference

See `docs/rdpbrowser_vi.md` for a Vietnamese overview of the available `RDPBrowser` functions and a compact usage example.

## Comparison With Juggler

See `docs/rdpbrowser_vs_juggler.md` for the current repository positioning and a direct comparison against legacy Juggler automation.

## Troubleshooting

See `docs/rdpbrowser_troubleshooting.md` for common runtime failures and the recommended debug order.
