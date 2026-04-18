import { firefox } from "playwright";

import { resolveWinfoxExecutablePath } from "./resolve.js";
import type {
  WinfoxBrowser,
  WinfoxBrowserContext,
  WinfoxLaunchOptions,
  WinfoxPersistentContextLaunchOptions,
} from "./types.js";

export async function launchWinfox(
  options: WinfoxLaunchOptions = {},
): Promise<WinfoxBrowser> {
  const executablePath = resolveWinfoxExecutablePath({ executablePath: options.executablePath });

  return firefox.launch({
    ...options,
    executablePath,
  });
}

export async function launchPersistentWinfoxContext(
  userDataDir: string,
  options: WinfoxPersistentContextLaunchOptions = {},
): Promise<WinfoxBrowserContext> {
  const executablePath = resolveWinfoxExecutablePath({ executablePath: options.executablePath });

  return firefox.launchPersistentContext(userDataDir, {
    ...options,
    executablePath,
  });
}
