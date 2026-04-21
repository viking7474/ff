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
| `goto()` | ready | extension/RDP + document events | Smoke-validated |
| `reload()` | ready | RDP + document events | Smoke-validated |
| `wait_for_load_state()` | ready | document events | Smoke-validated |
| `url_fresh()` | ready | evaluation + state refresh | Smoke-validated |
| `page.title()` | ready | page evaluation helper | Smoke-covered |

## DOM and Selectors

| Capability | Status | Backend | Notes |
|---|---|---|---|
| `evaluate()` | ready | `WebConsoleActor` | Smoke-validated |
| `content()` | ready | in-page JS | Smoke-validated |
| `query_selector()` | ready | in-page JS | Returns rect metadata |
| `query_selector_all()` | ready | in-page JS | Returns rect list |
| `wait_for_selector()` | ready | JS observer/polling | Smoke-validated |
| `locator.wait_for()` | ready | JS observer/polling | Smoke-validated |
| `locator.text_content()` | ready | in-page JS | Smoke-validated |
| `locator.get_attribute()` | ready | in-page JS | Smoke-validated |
| `locator.count()` | ready | in-page JS | Smoke-validated |

## Input

| Capability | Status | Backend | Notes |
|---|---|---|---|
| mouse move | ready | extension + experiment API | Smoke-validated |
| mouse click | ready | extension + experiment API | Smoke-validated |
| mouse wheel | ready | extension + experiment API | Smoke-validated |
| keyboard press | ready | extension + experiment API | Smoke-validated |
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
| memory usage | ready | `MemoryActor` | Smoke-validated |
| force GC | ready | `MemoryActor` | Smoke-validated |

## Events

| Capability | Status | Backend | Notes |
|---|---|---|---|
| `page.on("load")` | ready | document events | Smoke-validated |
| `page.on("domcontentloaded")` | ready | document events | Implemented |
| `page.on("framenavigated")` | partial | watcher target updates | Implemented, not smoke-covered yet |
| request/response event parity | missing | n/a | Use capture/spy APIs instead |

## Known Limits

1. This is not full Playwright protocol parity.
2. Browser contexts are not modeled as a Playwright-equivalent abstraction.
3. Downloads, dialogs, file chooser flows, and popup orchestration are not part of the current v1 supported surface.
4. `httpbin.org/html` may return an empty title in simple smoke checks; this is not treated as an automation failure.

## Recommendation

Treat `RDPBrowser v1` as:

1. a stealth-first automation backend
2. suitable for practical scraping and browser workflow automation
3. strong enough for single-page and multi-instance orchestration
4. not yet a promise of full Playwright/Juggler parity
