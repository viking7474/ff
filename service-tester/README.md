# Winfox Service Tester

End-to-end proxy-backed checks that verify a Winfox binary works through the Node/TypeScript `winfox` launcher. The Python service tester is deprecated.

## Prerequisites

- Node.js 18+
- At least one proxy in `proxies.txt`

## Quick Start

```bash
# 1. Add your proxies (see format below)
# 2. Install workspace deps
# 3. Run the service tester
npm install
./run_tests.sh
```

`run_tests.sh` now forwards to the Node/TypeScript workspace entrypoint in `winfox-service-tester`.

## Proxies

Tests require real proxies. Each context gets its own proxy, and the WebRTC IP is automatically derived from the proxy server address.

Create `proxies.txt` in this directory with one proxy per line:

```
user:pass@domain:port
```

Example:
```
alice:secret123@proxy1.example.com:10000
bob:hunter2@proxy2.example.com:10000
alice:secret123@proxy1.example.com:10001
```

- Blank lines and lines starting with `#` are ignored
- Proxies are assigned round-robin across the 6 test profiles
- Fewer proxies than profiles is fine — they cycle

## Manual Setup

If you prefer to run steps individually:

```bash
npm install
npm run test --workspace winfox-service-tester -- --proxies ./proxies.txt --executable-path /path/to/winfox-bin
```

## Options

```
./run_tests.sh [options]
npm run test --workspace winfox-service-tester -- [options]

  --executable-path PATH  Path to the Winfox binary or app bundle
  --profile-count N       Number of proxy-backed runs (default: 3)
  --proxies PATH          Path to proxies file (default: proxies.txt)
  --headful               Run with visible browser window
  --timeout-ms N          Wait timeout for browser checks
  --save-json PATH        Save raw results JSON
```

## What It Tests

Each run launches Winfox through one proxy and executes the browser-side checks bundle against a local test page.

- A dedicated browser launch via `packages/winfox`
- Its own proxy configuration
- The same browser-side anti-detect checks used by the build tester

Each context is scored across these categories:

| Category | What it checks |
|---|---|
| Automation Detection | Playwright/CDP artefacts |
| JS Engine | V8 vs SpiderMonkey signals |
| Lie Detection | Inconsistent property overrides |
| Firefox APIs | Firefox-specific API presence |
| Cross-Signal | Consistency across navigator, screen, etc. |
| CSS Fingerprint | CSS rendering fingerprint |
| Canvas Noise | Canvas hash uniqueness and stability |
| WebGL Render | WebGL rendering hash |
| Audio Integrity | AudioContext fingerprint |
| Font Platform | OS-consistent font availability |
| Speech Voices | Voice list matches declared OS |
| WebRTC | IP matches proxy server address |
| Stability | Fingerprint stable over time with other contexts open |
| Headless Detection | No headless mode signals |

## Interpreting Results

| Grade | Meaning |
|---|---|
| **A** | All checks pass |
| **B** | 1–2 failures (minor) |
| **C** | 3–5 failures |
| **D** | 6–10 failures |
| **F** | 11+ failures |

A grade of **A or B** exits with code `0`. Anything worse exits with code `1`.

The saved JSON report is intended for comparing grades and details across proxies and builds.

## Failure Triage

If a check fails, fix it in the browser/runtime or in `packages/winfox`, not in the tester.
