# RDPBrowser vs Juggler

This repository currently contains two distinct Firefox automation directions:

1. `RDPBrowser`
2. legacy `Juggler` / Playwright integration

The recommended direction for Python automation in this repo is now `RDPBrowser`.

## Short Version

Use `RDPBrowser` when you want:

1. stealth-first automation
2. Firefox RDP control plus trusted-like input
3. practical browser automation for scraping and workflow tasks
4. lower dependence on large upstream Playwright/Juggler patch drift

Keep `Juggler` only when you need:

1. legacy compatibility work
2. direct Playwright/Juggler maintenance work
3. debugging historical protocol behavior in this codebase

## Architecture

### RDPBrowser

`RDPBrowser` uses:

1. Firefox RDP actors for browser and target control
2. a temporary WebExtension bridge for commands, proxy auth, and network capture
3. an experiment API for trusted-like input and navigation helpers

Flow:

```text
Python controller
-> Firefox RDP
-> extension websocket bridge
-> nativeInput experiment API
-> Firefox tab/window
```

### Juggler

`Juggler` uses:

1. a custom protocol inside Firefox
2. Playwright/Juggler bootstrap patches
3. a browser-integrated protocol and page agent model

Flow:

```text
Playwright
-> Juggler protocol
-> patched Firefox integration
-> tab/page agent handling inside browser runtime
```

## Main Differences

| Topic | RDPBrowser | Juggler |
|---|---|---|
| Primary transport | Firefox RDP | Juggler protocol |
| Input backend | extension + experiment API | patched Juggler input path |
| Network tooling | extension bridge capture/spy | protocol-driven model |
| Multi-instance | strong | workable but not the repo focus now |
| Patch dependence | lower | higher |
| Stealth-first fit | strong | mixed, patch-heavy |
| Playwright parity | not a goal | native goal |

## Current Repository Position

For this repository direction:

1. `RDPBrowser` is the primary Python automation path.
2. `Juggler` is kept as a legacy/reference path.
3. New automation hardening work should prefer `RDPBrowser` unless there is a concrete compatibility reason not to.
4. `winfox.rdp` is the implementation namespace for that path.
5. `camoufox.rdp_api` is only a compatibility facade.

## What RDPBrowser Already Covers Well

1. launch and browser lifecycle
2. navigation and page evaluation
3. selectors and locator basics
4. trusted-like input
5. screenshots
6. network capture and request spying
7. multi-instance runs
8. practical multi-tab handling

See:

1. `docs/rdpbrowser.md`
2. `docs/rdpbrowser_v1_capability_matrix.md`
3. `tests/rdpbrowser_smoke.py`

## What Juggler Still Means in This Repo

`Juggler` remains relevant for:

1. maintaining historical Playwright integration knowledge
2. understanding older stealth patching decisions
3. debugging legacy branches or compatibility work

It should not be treated as the default direction for new Python automation work in this branch.

In the Python package layout:

1. `winfox.rdp` is the active framework namespace.
2. `camoufox.rdp_api` preserves old RDP imports.
3. `camoufox.legacy` groups the old Playwright-centric path.
