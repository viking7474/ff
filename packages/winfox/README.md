# Winfox JavaScript Library

This is the Node.js / TypeScript wrapper library for Camoufox. It provides integrations with Playwright, as well as a standalone custom RDP driver port (under `src/rdp`).

## E2E Smoke Test

To run the context isolation smoke test against a built Camoufox binary, use the following commands:

1. Build the TypeScript files:
\`\`\`bash
npm run build
\`\`\`

2. Execute the test and provide the `WINFOX_PATH` environment variable:
\`\`\`bash
WINFOX_PATH="/path/to/your/camoufox/binary" node --test dist/test/context_smoke.test.js
\`\`\`

*(Note: On Windows, use `set WINFOX_PATH=C:\path\to\camoufox.exe && node --test dist/test/context_smoke.test.js` or run in cross-env)*
