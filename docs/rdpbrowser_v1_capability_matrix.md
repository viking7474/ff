# RDPBrowser V1 Capability Matrix

This document defines the current `RDPBrowser` v1 supported surface.

Status values:

1. `ready`: expected to work and covered by smoke validation
2. `partial`: usable but not yet protocol-complete or not broadly exercised
3. `missing`: not implemented as a supported surface

## Browser Lifecycle

| Capability | Status | Backend | Notes |
|---|---|---|---|
| launch | ready | RDP + process launch | Validated by smoke suite |
| close | ready | bridge + RDP + process teardown | Windows cleanup improved |
| multi-instance | ready | per-instance ports and profiles | Smoke-validated |

## Page and Navigation

| Capability | Status | Backend | Notes |
|---|---|---|---|
| `new_page()` | ready | extension + RDP tab attach | Same window, new tab |
| `list_pages()` | ready | browser page registry | Smoke-covered |
| `page.close()` | ready | extension tab removal + registry cleanup | Smoke-covered |
| `page.bring_to_front()` | ready | extension tab activation | Smoke-covered |
| `browser.close_all_pages()` | ready | browser page lifecycle | Smoke-covered |
| `browser.page_by_url()` | ready | page registry + URL polling | Smoke-covered |
| `browser.pages_by_url()` | ready | page registry + URL polling | Smoke-covered |
| `browser.close_other_pages()` | ready | browser page lifecycle | Smoke-covered |
| `browser.wait_for_new_page()` | ready | registry-aware tab actor wait | Smoke-covered |
| `goto()` | ready | extension/RDP + document events | Smoke-validated |
| `reload()` | ready | RDP + document events | Smoke-validated |
| `wait_for_load_state()` | ready | document events | Smoke-validated |
| `url_fresh()` | ready | evaluation + state refresh | Smoke-validated |
| `page.title()` | ready | page evaluation helper | Smoke-covered |
| `page.wait_for_url()` | ready | polling + URL evaluation | Smoke-covered |
| `page.expect_popup()` | ready | browser page registry wait | Smoke-covered, popup active-page checks added |
| `browser.get_active_page()` | ready | bridge active-tab lookup + page registry | Smoke-covered |
| `page.is_active()` | ready | bridge active-tab lookup | Smoke-covered |

## DOM and Selectors

| Capability | Status | Backend | Notes |
|---|---|---|---|
| `evaluate()` | ready | `WebConsoleActor` | Smoke-validated |
| `content()` | ready | in-page JS | Smoke-validated |
| `query_selector()` | ready | in-page JS | Returns rect metadata |
| `query_selector_all()` | ready | in-page JS | Returns rect list |
| `page.text_content()` | ready | locator wrapper | Smoke-covered |
| `page.inner_text()` | ready | in-page JS helper | Smoke-covered |
| `page.inner_html()` | ready | in-page JS helper | Smoke-covered |
| `page.all_text_contents()` | ready | in-page JS helper | Smoke-covered |
| `page.all_inner_texts()` | ready | in-page JS helper | Smoke-covered |
| `page.get_attribute()` | ready | locator wrapper | Smoke-covered |
| `page.count()` | ready | locator wrapper | Smoke-covered |
| `page.exists()` | ready | selector count helper | Smoke-covered |
| `page.has_selector()` | ready | selector existence alias | Smoke-covered |
| `page.is_visible()` | ready | DOM visibility helper | Smoke-covered |
| `page.is_hidden()` | ready | DOM visibility helper | Smoke-covered |
| `page.wait_for_text()` | ready | body text polling | Smoke-covered |
| `page.wait_for_selector_count()` | ready | selector count polling | Smoke-covered |
| `page.wait_until_hidden()` | ready | hidden-state wait wrapper | Smoke-covered |
| `page.wait_until_visible()` | ready | visible-state wait wrapper | Smoke-covered |
| `page.first()` / `page.nth()` / `page.last()` | ready | richer locator selection helpers | Smoke-covered |
| `wait_for_selector()` | ready | JS observer/polling | Smoke-validated |
| `locator.wait_for()` | ready | JS observer/polling | Smoke-validated |
| `locator.text_content()` | ready | in-page JS | Smoke-validated |
| `locator.inner_text()` | ready | in-page JS | Smoke-covered |
| `locator.get_attribute()` | ready | in-page JS | Smoke-validated |
| `locator.count()` | ready | in-page JS | Smoke-validated |
| `locator.first()` / `locator.last()` / `locator.nth()` | ready | richer locator selection helpers | Smoke-covered |
| `locator.exists()` | ready | richer locator helper | Smoke-covered |
| `locator.is_visible()` / `locator.is_hidden()` | ready | richer locator helper | Smoke-covered |

## Input

| Capability | Status | Backend | Notes |
|---|---|---|---|
| mouse move | ready | extension + experiment API | Smoke-validated |
| mouse click | ready | extension + experiment API | Smoke-validated |
| mouse wheel | ready | extension + experiment API | Smoke-validated |
| keyboard press | ready | extension + experiment API | Smoke-validated |
| hover | ready | selector rect + mouse move | Smoke-covered |
| focus | ready | in-page JS focus helper | Smoke-covered |
| press(selector, key) | ready | focus helper + keyboard press | Smoke-covered |
| set_input_files | partial | practical file input injection | Smoke-covered |
| fill | ready | click + DOM clear + bridge type | Smoke-validated |
| locator click | ready | bridge input | Smoke-validated |

## Screenshots and Helpers

| Capability | Status | Backend | Notes |
|---|---|---|---|
| screenshot | ready | extension with fallback | Smoke-validated |
| simulate tab switch | ready | extension window APIs | Smoke-validated |

## Network

| Capability | Status | Backend | Notes |
|---|---|---|---|
| start/stop capture | ready | extension `filterResponseData` | Smoke-validated |
| wait for response | ready | capture polling | Smoke-validated |
| captured responses | ready | extension bridge | Smoke-validated |
| start/stop spy | ready | extension `webRequest` | Smoke-validated |
| spied requests | ready | extension bridge | Smoke-validated |

## Diagnostics and State

| Capability | Status | Backend | Notes |
|---|---|---|---|
| clear cookies | ready | extension cookies API | Smoke-validated |
| `page.get_local_storage()` | ready | in-page JS helper | Smoke-covered |
| `page.set_local_storage()` | ready | in-page JS helper | Smoke-covered |
| `page.get_session_storage()` | ready | in-page JS helper | Smoke-covered |
| `page.set_session_storage()` | ready | in-page JS helper | Smoke-covered |
| `page.save_storage_state()` | ready | page-scoped storage snapshot | Smoke-covered |
| `page.load_storage_state()` | ready | page-scoped storage restore | Smoke-covered |
| `browser.save_state()` | partial | cookies + per-origin localStorage | Smoke-covered |
| `browser.load_state()` | partial | cookies + per-origin localStorage | Smoke-covered |
| `browser.save_state_to_file()` | partial | browser state JSON export | Smoke-covered |
| `browser.load_state_from_file()` | partial | browser state JSON import | Smoke-covered |
| memory usage | ready | `MemoryActor` | Smoke-validated |
| force GC | ready | `MemoryActor` | Smoke-validated |

## Events

| Capability | Status | Backend | Notes |
|---|---|---|---|
| `page.on("load")` | ready | document events | Smoke-validated |
| `page.on("domcontentloaded")` | ready | document events | Implemented |
| `page.on("framenavigated")` | partial | watcher target updates | Implemented, not smoke-covered yet |
| `page.on("request")` | ready | bridge request event polling | Smoke-covered, standardized payload with `requestId` |
| `page.on("response")` | ready | bridge response event polling | Smoke-covered, standardized payload with `requestId` |
| `page.on("requestfinished")` | ready | bridge spy completion events | Smoke-covered, carries `state=finished`, correlates by `requestId` |
| `page.on("requestfailed")` | partial | bridge spy failure events | Best-effort, smoke-covered, carries `state=failed` and `error` |

## Dialogs

| Capability | Status | Backend | Notes |
|---|---|---|---|
| `page.expect_dialog()` | partial | practical JS shim | Smoke-covered |
| `dialog.type` | partial | practical JS shim | Smoke-covered |
| `dialog.message` | partial | practical JS shim | Smoke-covered |
| `dialog.handled` | partial | practical JS shim | Smoke-covered |
| `dialog.accepted` | partial | practical JS shim | Smoke-covered |
| `dialog.prompt_text` | partial | practical JS shim | Smoke-covered |
| `dialog.accept()` | partial | practical JS shim | Smoke-covered |
| `dialog.dismiss()` | partial | practical JS shim | Smoke-covered |

## Frames

| Capability | Status | Backend | Notes |
|---|---|---|---|
| `page.frames()` | ready | in-page frame enumeration | Smoke-covered |
| `page.frame(index/name/url_contains)` | ready | metadata lookup | Smoke-covered |
| `frame.text_content()` | ready | same-origin frame JS helper | Smoke-covered |
| `frame.inner_text()` | ready | same-origin frame JS helper | Smoke-covered |
| `frame.inner_html()` | ready | same-origin frame JS helper | Smoke-covered |
| `frame.get_attribute()` | ready | same-origin frame JS helper | Smoke-covered |
| `frame.count()` | ready | same-origin frame JS helper | Smoke-covered |
| `frame.exists()` | ready | same-origin frame JS helper | Smoke-covered |
| `frame.is_visible()` | ready | same-origin frame visibility helper | Smoke-covered |
| `frame.is_hidden()` | ready | same-origin frame visibility helper | Smoke-covered |
| `frame.wait_for_text()` | ready | same-origin frame text polling | Smoke-covered |
| `frame.wait_for_selector()` | ready | same-origin frame polling | Smoke-covered |
| `frame.locator()` | ready | frame-scoped locator helper | Smoke-covered |
| `frame.hover()` | ready | frame geometry + mouse move | Smoke-covered |
| `frame.click()` | ready | frame geometry + mouse click | Smoke-covered |
| `frame.focus()` | ready | same-origin frame JS helper | Smoke-covered |
| `frame.press()` | ready | frame focus + keyboard press | Smoke-covered |
| `frame.evaluate()` | partial | same-origin frame eval | Smoke-covered |
| cross-origin frame metadata | ready | frame enumeration only | Smoke-covered |
| cross-origin DOM/evaluate access | partial | explicit runtime error | By design |

## Known Limits

1. This is not full Playwright protocol parity.
2. Browser contexts are not modeled as a Playwright-equivalent abstraction.
3. File upload support exists through `set_input_files()`, but native chooser parity is not part of the current v1 supported surface.
4. Downloads and file chooser flows beyond direct file input population are not part of the current v1 supported surface.
5. Dialog handling exists as a practical shim, not native parity.
6. `save_state()` / `load_state()` currently focus on cookies and per-origin `localStorage`, not full browser context parity.
7. Frame support currently focuses on same-origin iframe access; cross-origin frames expose metadata only.
8. `httpbin.org/html` may return an empty title in simple smoke checks; this is not treated as an automation failure.

## Recommendation

Treat `RDPBrowser v1` as:

1. a stealth-first automation backend
2. suitable for practical scraping and browser workflow automation
3. strong enough for single-page and multi-instance orchestration
4. not yet a promise of full Playwright/Juggler parity
