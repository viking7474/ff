# Winfox Build Tester

Tests a raw Winfox binary directly against the browser-side anti-detect checks. This is now a Node/TypeScript entrypoint built around `packages/winfox`.

## Prerequisites

- Node.js 18+

## Setup

```bash
# Install workspace deps
npm install
```

## Usage

```bash
npm run test --workspace winfox-build-tester -- <binary_path> [options]
```

**Example:**
```bash
npm run test --workspace winfox-build-tester -- /path/to/winfox-bin
```

## Options

```
  binary_path or --executable-path PATH  Path to the Winfox binary
  --headful                           Run with a visible window
  --timeout-ms N                      Wait timeout for browser checks
  --save-json PATH                    Save raw results JSON
```

## What It Tests

The Node CLI launches a single Winfox instance, serves the browser checks locally, and reports a grade from the in-page results.

Each profile is scored across:

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
| WebRTC | IP spoofing (test IP injected) |
| Stability | Fingerprint stable over time |
| Headless Detection | No headless mode signals |
| Match Results | Injected values actually appear in page |

## How It Differs from the Service Tests

| | Build Tester | Service Tests |
|---|---|---|
| Entry point | `npm run test --workspace winfox-build-tester` | `npm run test --workspace winfox-service-tester` |
| Launch API | `packages/winfox` | `packages/winfox` |
| Proxy support | No | Yes |

## The Checks Bundle

`scripts/checks-bundle.js` is built from the TypeScript sources in `src/lib/checks/`. It is rebuilt by the Node CLI when needed.

```bash
rm scripts/checks-bundle.js
npm run test --workspace winfox-build-tester -- <binary_path>
```

Source files:
- `src/lib/checks/index.ts` — entry point
- `src/lib/checks/core.ts` — automation, JS engine, lie detection, etc.
- `src/lib/checks/extended.ts` — canvas, WebGL, fonts, audio, etc.
- `src/lib/checks/workers.ts` — worker thread consistency
- `src/lib/checks/collectors.ts` — fingerprint data collectors (hashes, WebRTC, stability)
