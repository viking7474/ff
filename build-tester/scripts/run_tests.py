#!/usr/bin/env python3
import sys

print(
    "The Python build tester entrypoint is deprecated.\n"
    "Use the Node/TypeScript entrypoint instead:\n"
    "  npm run test --workspace winfox-build-tester -- [binary_path] [options]",
    file=sys.stderr,
)
sys.exit(1)
