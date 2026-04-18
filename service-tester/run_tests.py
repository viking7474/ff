#!/usr/bin/env python3
import sys

print(
    "The Python service tester entrypoint is deprecated.\n"
    "Use the Node/TypeScript entrypoint instead:\n"
    "  npm run test --workspace winfox-service-tester -- [options]",
    file=sys.stderr,
)
sys.exit(1)
