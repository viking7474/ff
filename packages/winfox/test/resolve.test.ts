import test from "node:test";
import assert from "node:assert/strict";
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";

import { getWinfoxBinaryName, resolveWinfoxExecutablePath } from "../src/index.js";

function createExecutable(rootDir: string): string {
  const binaryName = getWinfoxBinaryName();
  const executablePath = join(rootDir, binaryName);
  mkdirSync(dirname(executablePath), { recursive: true });
  writeFileSync(executablePath, "#!/bin/sh\nexit 0\n", "utf8");
  chmodSync(executablePath, 0o755);
  return executablePath;
}

test("resolveWinfoxExecutablePath prefers explicit executablePath", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "winfox-explicit-"));

  try {
    const executablePath = createExecutable(tempDir);

    assert.equal(
      resolveWinfoxExecutablePath({ executablePath }),
      executablePath,
    );
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

test("resolveWinfoxExecutablePath searches cwd for strict winfox binary names", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "winfox-cwd-"));

  try {
    const executablePath = createExecutable(tempDir);

    assert.equal(resolveWinfoxExecutablePath({ cwd: tempDir }), executablePath);
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

test("resolveWinfoxExecutablePath fails with a winfox-only error", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "winfox-missing-"));

  try {
    assert.throws(
      () => resolveWinfoxExecutablePath({ cwd: tempDir, env: {} }),
      (error: unknown) => {
        assert.ok(error instanceof Error);
        assert.match(error.message, /Unable to locate a Winfox executable/);
        assert.match(error.message, /winfox/i);
        assert.doesNotMatch(error.message, /camoufox/i);
        return true;
      },
    );
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});
