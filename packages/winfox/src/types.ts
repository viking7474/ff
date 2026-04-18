import type {
  Browser,
  BrowserContext,
  BrowserServer,
  LaunchOptions,
} from "playwright";
import { firefox } from "playwright";

export type WinfoxBrowser = Browser;
export type WinfoxBrowserContext = BrowserContext;
export type WinfoxBrowserServer = BrowserServer;
export type WinfoxLaunchOptions = LaunchOptions;
export type WinfoxPersistentContextLaunchOptions = Parameters<
  typeof firefox.launchPersistentContext
>[1];

export interface ResolveWinfoxExecutableOptions {
  executablePath?: string;
  cwd?: string;
  env?: NodeJS.ProcessEnv;
}
