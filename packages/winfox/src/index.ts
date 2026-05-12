export { launchPersistentWinfoxContext, launchWinfox } from "./launch.js";
export {
  buildCertificateText,
  buildFullResult,
  computeCrossProfile,
  computeGrade,
  countAllChecks,
  generateCertificate,
  printCertificate,
  printProfileResult,
} from "./reports.js";
export { resolveWinfoxExecutablePath, getWinfoxBinaryName } from "./resolve.js";
export { launchWinfoxServer } from "./server.js";
export type {
  CertificateData,
  CrossProfileAnalysis,
  FullTestResult,
  ResolveWinfoxExecutableOptions,
  TesterProfile,
  TesterProfileResult,
  TesterResults,
  WinfoxBrowser,
  WinfoxBrowserContext,
  WinfoxBrowserServer,
  WinfoxLaunchOptions,
  WinfoxPersistentContextLaunchOptions,
} from "./types.js";

export * as rdp from "./rdp/index.js";
export * as humanize from "./humanize.js";
export * as geckordp from "./geckordp/index.js";
