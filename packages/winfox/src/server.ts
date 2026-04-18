import { firefox } from "playwright";

import { resolveWinfoxExecutablePath } from "./resolve.js";
import type { WinfoxBrowserServer, WinfoxLaunchOptions } from "./types.js";

type FirefoxWithLaunchServer = typeof firefox & {
  launchServer?: (options?: WinfoxLaunchOptions) => Promise<WinfoxBrowserServer>;
};

export async function launchWinfoxServer(
  options: WinfoxLaunchOptions = {},
): Promise<WinfoxBrowserServer> {
  const browserType = firefox as FirefoxWithLaunchServer;

  if (!browserType.launchServer) {
    throw new Error("The installed Playwright build does not expose firefox.launchServer().");
  }

  const executablePath = resolveWinfoxExecutablePath({ executablePath: options.executablePath });

  return browserType.launchServer({
    ...options,
    executablePath,
  });
}
