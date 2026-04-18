import { accessSync, constants } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";

import type { ResolveWinfoxExecutableOptions } from "./types.js";

const COMMON_BUILD_PATHS = [
  ["dist", "bin"],
  ["obj-x86_64-pc-linux-gnu", "dist", "bin"],
  ["obj-i686-pc-linux-gnu", "dist", "bin"],
  ["obj-x86_64-pc-mingw32", "dist", "bin"],
  ["obj-i686-pc-mingw32", "dist", "bin"],
  ["obj-x86_64-apple-darwin", "dist"],
  ["obj-aarch64-apple-darwin", "dist"],
] as const;

export function getWinfoxBinaryName(platform = process.platform): string {
  if (platform === "win32") {
    return "winfox.exe";
  }

  if (platform === "darwin") {
    return join("Winfox.app", "Contents", "MacOS", "winfox");
  }

  return "winfox-bin";
}

function canExecute(filePath: string): boolean {
  try {
    accessSync(filePath, constants.F_OK | constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function findProjectRoot(startDir: string): string {
  let currentDir = resolve(startDir);

  while (true) {
    if (canExecute(join(currentDir, ".git"))) {
      return currentDir;
    }

    try {
      accessSync(join(currentDir, "package.json"), constants.F_OK);
      return currentDir;
    } catch {
      const parentDir = dirname(currentDir);
      if (parentDir === currentDir) {
        return resolve(startDir);
      }
      currentDir = parentDir;
    }
  }
}

function candidatePaths(startDir: string): string[] {
  const rootDir = findProjectRoot(startDir);
  const binaryName = getWinfoxBinaryName();

  return [
    join(startDir, binaryName),
    join(rootDir, binaryName),
    ...COMMON_BUILD_PATHS.map((segments) => join(rootDir, ...segments, binaryName)),
  ];
}

function assertExecutable(filePath: string, source: string): string {
  const resolvedPath = resolve(filePath);
  if (!canExecute(resolvedPath)) {
    throw new Error(`Winfox executable from ${source} was not found or is not executable: ${resolvedPath}`);
  }

  return resolvedPath;
}

export function resolveWinfoxExecutablePath(
  options: ResolveWinfoxExecutableOptions = {},
): string {
  const cwd = resolve(options.cwd ?? process.cwd());

  if (options.executablePath) {
    return assertExecutable(
      isAbsolute(options.executablePath)
        ? options.executablePath
        : join(cwd, options.executablePath),
      "options.executablePath",
    );
  }

  const envPath = options.env?.WINFOX_EXECUTABLE_PATH ?? process.env.WINFOX_EXECUTABLE_PATH;
  if (envPath) {
    return assertExecutable(isAbsolute(envPath) ? envPath : join(cwd, envPath), "WINFOX_EXECUTABLE_PATH");
  }

  const candidates = candidatePaths(cwd).map((candidate) => resolve(candidate));
  const executablePath = candidates.find((candidate) => canExecute(candidate));

  if (!executablePath) {
    throw new Error(
      [
        `Unable to locate a Winfox executable named ${getWinfoxBinaryName()}.`,
        "Searched:",
        ...candidates.map((candidate) => `- ${candidate}`),
        "Set WINFOX_EXECUTABLE_PATH or pass executablePath explicitly.",
      ].join("\n"),
    );
  }

  return executablePath;
}
