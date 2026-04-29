# RDPBrowser

`RDPBrowser` is the Firefox RDP-based automation path for Winfox.

It is designed for stealth-first automation without relying on Playwright/Juggler as the primary runtime transport.

In this repository, `RDPBrowser` should be treated as the primary Python automation path.

## Package Identity

Use the package layout like this:

1. `winfox.rdp` is the active implementation and the default import path for new code.
2. `camoufox.rdp_api` is a compatibility facade that re-exports the same public RDP surface.
3. `camoufox.legacy` contains the historical Playwright-centric Python path.

Recommended import for new code:

```python
from winfox.rdp import RDPBrowser
```

Compatibility import that still works:

```python
from camoufox.rdp_api import RDPBrowser
```

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

from winfox.rdp import RDPBrowser


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

from winfox.rdp import RDPBrowser


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
Waits for a newly opened page or tab to appear, using both page registry changes and tab actor discovery to reduce popup race conditions.

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

7. `await page.expect_popup(timeout=5000)`
Wait for a popup or new tab opened by actions from the current page.

### Page DOM helpers

1. `await page.text_content(selector)`
Return the matched element's text content.

2. `await page.inner_text(selector)`
Return the matched element's rendered inner text.

3. `await page.inner_html(selector)`
Return the matched element's `innerHTML`.

4. `await page.all_text_contents(selector)`
Return text content for all matched elements.

5. `await page.all_inner_texts(selector)`
Return rendered inner text for all matched elements.

6. `await page.get_attribute(selector, name)`
Return the matched element's attribute value.

7. `await page.count(selector)`
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

15. `await page.first(selector)` / `await page.nth(selector, index)` / `await page.last(selector)`
Return locator-style handles for the first, nth, or last matching element.

16. `await page.wait_for_selector(selector)`
Wait until the selector is present/visible under the current implementation's rules.

Locator helpers now also include:

1. `locator.first()`
2. `locator.last()`
3. `locator.nth(index)`
4. `locator.inner_text()`
5. `locator.exists()`
6. `locator.is_visible()`
7. `locator.is_hidden()`
8. `locator.filter(has_text=..., exact=False)`

Additional practical locator-style helpers:

1. `page.get_by_text(text, exact=False)`
2. `page.get_by_placeholder(text, exact=False)`
3. `page.get_by_label(text, exact=False)`
4. `page.get_by_test_id(value)`
5. `page.get_by_role(role, name=None, exact=False)`

The same helper style is available on same-origin frames:

1. `frame.get_by_text(...)`
2. `frame.get_by_placeholder(...)`
3. `frame.get_by_label(...)`
4. `frame.get_by_test_id(...)`
5. `frame.locator(...).filter(has_text=...)`
6. `frame.get_by_role(...)`

Locator chaining is also supported in a practical form:

1. `locator.locator(selector)`
2. `frame.locator(...).locator(selector)`

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

12. `dialog.handled` / `dialog.accepted` / `dialog.prompt_text`
Inspect the observed dialog state after it has been accepted or dismissed.

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

6. `await page.set_request_block_patterns(patterns)`
Block requests whose URLs contain one of the given substrings.

7. `await page.set_extra_http_headers(headers, patterns=None)`
Apply practical request-header overrides for matching URL patterns.

8. `await page.clear_interception()`
Clear the current minimal interception rules.

9. `await page.fulfill_text(patterns, body, content_type="text/plain")`
Mock matching requests with a text response using a `data:` URL redirect.

10. `await page.fulfill_json(patterns, data)`
Mock matching requests with a JSON response using a `data:` URL redirect.

Typical event payloads now include:

1. `requestId`
2. `state`
3. `url`
4. `method`
5. `headers`
6. `requestBody`
7. `responseHeaders`
8. `responseBody`
9. `status`
10. `error`
11. `timestamp`
12. `page`

The practical event bridge is designed so that `request`, `response`, and `requestfinished` can often be correlated through the same `requestId`.

Current interception scope is intentionally small:

1. block by URL substring pattern
2. override request headers by URL substring pattern
3. mock text or JSON responses by URL substring pattern

Current practical behavior:

1. block and header rules are merged instead of overwriting each other
2. blocked requests may appear through `requestfailed` with `error="blocked_by_interception"`

It is not yet full route/fulfill/continue parity, but it now supports a minimal practical fulfill path for text and JSON.

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

5. `await page.save_storage_state()`
Capture a page-scoped state object containing `localStorage` and `sessionStorage`.

6. `await page.load_storage_state(state)`
Restore a page-scoped storage state object into the current page.

7. `await browser.save_state()`
Return a practical reusable state object containing cookies and `localStorage` grouped by origin.

8. `await browser.load_state(state)`
Restore cookies and per-origin `localStorage` from a saved state object.

9. `await browser.save_state_to_file(path)`
Write a practical browser state object to disk as JSON.

10. `await browser.load_state_from_file(path)`
Load a practical browser state object from disk.

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

Hardening additions in this repo now also include:

1. page-scoped `save_storage_state()` / `load_storage_state()`
2. file-based `save_state_to_file()` / `load_state_from_file()`
3. multi-origin persistence validation

`sessionStorage` helpers exist at page level, but are not yet treated as portable browser-wide state parity.

## Contexts

`RDPBrowser` now includes a minimal context model.

Current design:

1. each context is an isolated child `RDPBrowser` instance
2. each context gets its own profile and ports
3. this provides practical isolation without pretending to be a single-process Playwright context implementation

Available APIs:

1. `await browser.new_context()`
2. `browser.contexts()`
3. `await browser.close_all_contexts()`
4. `await context.new_page()`
5. `context.pages()`
6. `await context.get_active_page()`
7. `await context.save_state()`
8. `await context.load_state(state)`
9. `await context.save_state_to_file(path)`
10. `await context.load_state_from_file(path)`
11. `await context.close()`

Smoke coverage:

1. `tests/rdpbrowser_context_smoke.py`
2. `tests/rdpbrowser_context_stress.py`

## Frames

`RDPBrowser` now includes a minimal frame model focused on same-origin iframes.

Available APIs:

1. `await page.frames()`
2. `await page.child_frames(path=None)`
3. `await page.frame(index=..., name=..., url_contains=..., path=...)`
4. `await frame.parent_frame()`
5. `await frame.child_frames()`
6. `await frame.evaluate(expression)`
7. `await frame.text_content(selector)`
8. `await frame.inner_text(selector)`
9. `await frame.inner_html(selector)`
10. `await frame.get_attribute(selector, name)`
11. `await frame.count(selector)`
12. `await frame.exists(selector)`
13. `await frame.is_visible(selector)`
14. `await frame.is_hidden(selector)`
15. `await frame.wait_for_text(text)`
16. `await frame.wait_for_selector(selector)`
17. `frame.locator(selector)`
15. `await frame.hover(selector)`
16. `await frame.click(selector)`
17. `await frame.focus(selector)`
18. `await frame.press(selector, key)`

Current scope:

1. same-origin frames are supported for DOM/evaluate helpers and basic interaction helpers
2. cross-origin frames expose metadata only
3. cross-origin frame DOM/evaluate access raises a clear runtime error
4. nested frame paths are supported for same-origin frame lookup
5. frame tree helpers are available through `page.child_frames()`, `frame.parent_frame()`, and `frame.child_frames()`

Example:

```python
frames = await page.frames()
frame = await page.frame(name="sameOriginFrame")
print(await frame.text_content("h1"))
```

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
5. `tests/rdpbrowser_state_persistence_check.py`

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
