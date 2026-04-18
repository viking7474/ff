import { createHash, createHmac, randomUUID } from "node:crypto";

export type Grade = "A" | "B" | "C" | "D" | "F";

export interface TesterCheckResult {
  passed: boolean;
  detail?: string;
}

export interface TesterResults {
  core?: Record<string, Record<string, TesterCheckResult>>;
  extended?: Record<string, Record<string, TesterCheckResult>>;
  workers?: Record<string, Record<string, TesterCheckResult>>;
  webrtc?: { passed?: boolean; detail?: string };
  stability?: { stable?: boolean; detail?: string };
  selfDestruct?: Record<string, TesterCheckResult>;
  fingerprints?: {
    navigator?: { userAgent?: string; platform?: string };
    audio?: { hash?: string };
    canvas?: { hash?: string };
    fonts?: { hash?: string };
    timezone?: { timezone?: string };
    screen?: { width?: number; height?: number };
    speechVoices?: { hash?: string };
    webgl?: { unmaskedVendor?: string; unmaskedRenderer?: string };
  };
}

export interface MatchResult {
  name: string;
  passed: boolean;
  expected?: string;
  actual?: string;
}

export interface TesterProfile {
  name: string;
  os?: "macos" | "linux" | "windows";
  mode?: "per-context" | "global";
  proxy?: string;
  proxyGeo?: Record<string, string>;
}

export interface TesterProfileResult {
  profile: TesterProfile;
  results?: TesterResults | null;
  matchResults?: MatchResult[];
  grade: Grade;
  passCount: number;
  totalChecks: number;
  error?: string;
}

export interface CrossProfileAnalysis {
  macPerContext: {
    uniqueAudio: number;
    uniqueCanvas: number;
    uniqueFonts: number;
    uniqueTimezones: number;
    uniqueScreens: number;
    uniqueVoices: number;
    uniqueWebGL: number;
    uniquePlatforms: number;
    total: number;
  };
  linuxPerContext: {
    uniqueAudio: number;
    uniqueCanvas: number;
    uniqueFonts: number;
    uniqueTimezones: number;
    uniqueScreens: number;
    uniqueVoices: number;
    uniqueWebGL: number;
    uniquePlatforms: number;
    total: number;
  };
}

export interface FullTestResult {
  profiles: TesterProfileResult[];
  crossProfile: CrossProfileAnalysis;
  overallGrade: Grade;
  totalPassed: number;
  totalChecks: number;
  timestamp: string;
  binaryPath?: string;
}

export interface CertificateData {
  id: string;
  signature: string;
  resultsHash: string;
  timestamp: string;
  platform: string;
  browserVersion: string;
  passCount: number;
  totalTests: number;
  overallPass: boolean;
  sectionResults: Array<{ name: string; passed: number; total: number }>;
  failedTests: string[];
  profileCount: number;
  proxyInfo?: Array<Record<string, string>>;
}

export interface CertificateOptions {
  title: string;
  platform: string;
  secret: string;
  includeProxyInfo?: boolean;
}

export const CATEGORY_LABELS: Record<string, string> = {
  automation: "Automation Detection",
  jsEngine: "JS Engine",
  lieDetection: "Lie Detection",
  firefoxAPIs: "Firefox APIs",
  crossSignal: "Cross-Signal",
  cssFingerprint: "CSS Fingerprint",
  mathEngine: "Math Engine",
  permissionsAPI: "Permissions",
  speechVoices: "Speech Voices",
  performanceAPI: "Performance",
  intlConsistency: "Intl Consistency",
  emojiFingerprint: "Emoji",
  canvasNoiseDetection: "Canvas Noise",
  webglRenderHash: "WebGL Render",
  fontPlatformConsistency: "Font Platform",
  audioIntegrity: "Audio Integrity",
  iframeTesting: "Iframe Testing",
  workerConsistency: "Workers",
  headlessDetection: "Headless Detection",
  trashDetection: "Trash Detection",
  fontEnvironment: "Font Environment",
};

const GREEN = "\u001b[92m";
const RED = "\u001b[91m";
const YELLOW = "\u001b[93m";
const CYAN = "\u001b[96m";
const BOLD = "\u001b[1m";
const RESET = "\u001b[0m";
const BOX_W = 60;
const CAT_ART = String.raw`    /\_____ /\\
   /  o   o  \\
  ( ==  ^  == )
   )         (
  (  )     (  )
 ( (  )   (  ) )
(__(__)___(__)__)`.replace("_____ ", "_____");

function stripAnsi(value: string): string {
  return value.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, "");
}

function gradeColor(grade: Grade): string {
  if (grade === "A") {
    return GREEN;
  }
  if (grade === "B" || grade === "C") {
    return YELLOW;
  }
  return RED;
}

function boxLine(inner: string): string {
  const visible = stripAnsi(inner).length;
  return `║${inner}${" ".repeat(Math.max(0, BOX_W - visible))}║`;
}

function boxSep(): string {
  return `╠${"═".repeat(BOX_W)}╣`;
}

function boxTop(): string {
  return `╔${"═".repeat(BOX_W)}╗`;
}

function boxBot(): string {
  return `╚${"═".repeat(BOX_W)}╝`;
}

function formatSectionLine(name: string, passed: number, total: number): string {
  const ok = passed === total;
  const score = `${passed}/${total}`;
  const statusVisible = ok ? "[PASS]" : `[${total - passed} FAIL]`;
  const statusAnsi = ok ? `${GREEN}${statusVisible}${RESET}` : `${RED}${statusVisible}${RESET}`;
  const prefixVisible = `  ${name} `;
  const suffixVisible = ` ${score}  ${statusVisible}  `;
  const dotsLength = Math.max(1, BOX_W - prefixVisible.length - suffixVisible.length);
  return boxLine(`  ${name} ${".".repeat(dotsLength)} ${score}  ${statusAnsi}  `);
}

export function computeGrade(passCount: number, totalChecks: number): Grade {
  const failCount = totalChecks - passCount;
  if (failCount === 0) {
    return "A";
  }
  if (failCount <= 2) {
    return "B";
  }
  if (failCount <= 5) {
    return "C";
  }
  if (failCount <= 10) {
    return "D";
  }
  return "F";
}

export function countChecks(categories: Record<string, unknown>): { passed: number; total: number } {
  let passed = 0;
  let total = 0;
  for (const category of Object.values(categories)) {
    if (!category || typeof category !== "object") {
      continue;
    }
    for (const check of Object.values(category as Record<string, unknown>)) {
      if (!check || typeof check !== "object" || !("passed" in check)) {
        continue;
      }
      total += 1;
      if ((check as TesterCheckResult).passed) {
        passed += 1;
      }
    }
  }
  return { passed, total };
}

export function countAllChecks(
  results: TesterResults,
  matchResults: MatchResult[] = [],
  includeSelfDestruct = true,
): { passed: number; total: number } {
  let passed = 0;
  let total = 0;

  for (const category of [results.core ?? {}, results.extended ?? {}, results.workers ?? {}]) {
    const counts = countChecks(category);
    passed += counts.passed;
    total += counts.total;
  }

  total += 1;
  if (results.webrtc?.passed) {
    passed += 1;
  }

  total += 1;
  if (results.stability?.stable) {
    passed += 1;
  }

  for (const match of matchResults) {
    total += 1;
    if (match.passed) {
      passed += 1;
    }
  }

  if (includeSelfDestruct && results.selfDestruct) {
    for (const check of Object.values(results.selfDestruct)) {
      total += 1;
      if (check.passed) {
        passed += 1;
      }
    }
  }

  return { passed, total };
}

function emptyCrossProfile(): CrossProfileAnalysis {
  const empty = {
    uniqueAudio: 0,
    uniqueCanvas: 0,
    uniqueFonts: 0,
    uniqueTimezones: 0,
    uniqueScreens: 0,
    uniqueVoices: 0,
    uniqueWebGL: 0,
    uniquePlatforms: 0,
    total: 0,
  };
  return {
    macPerContext: { ...empty },
    linuxPerContext: { ...empty },
  };
}

export function computeCrossProfile(profileResults: TesterProfileResult[]): CrossProfileAnalysis {
  const mac = profileResults.filter((profile) => profile.profile.os === "macos");
  const linux = profileResults.filter((profile) => profile.profile.os === "linux");

  const analyze = (group: TesterProfileResult[]) => {
    if (group.length === 0) {
      return emptyCrossProfile().macPerContext;
    }

    const audio = new Set<string>();
    const canvas = new Set<string>();
    const fonts = new Set<string>();
    const timezones = new Set<string>();
    const screens = new Set<string>();
    const voices = new Set<string>();
    const webgl = new Set<string>();
    const platforms = new Set<string>();

    for (const profile of group) {
      const fingerprints = profile.results?.fingerprints;
      if (!fingerprints) {
        continue;
      }
      if (fingerprints.audio?.hash) {
        audio.add(fingerprints.audio.hash);
      }
      if (fingerprints.canvas?.hash) {
        canvas.add(fingerprints.canvas.hash);
      }
      if (fingerprints.fonts?.hash) {
        fonts.add(fingerprints.fonts.hash);
      }
      if (fingerprints.timezone?.timezone) {
        timezones.add(fingerprints.timezone.timezone);
      }
      if (fingerprints.screen?.width && fingerprints.screen?.height) {
        screens.add(`${fingerprints.screen.width}x${fingerprints.screen.height}`);
      }
      if (fingerprints.speechVoices?.hash) {
        voices.add(fingerprints.speechVoices.hash);
      }
      if (fingerprints.webgl?.unmaskedVendor || fingerprints.webgl?.unmaskedRenderer) {
        webgl.add(`${fingerprints.webgl?.unmaskedVendor ?? ""}|${fingerprints.webgl?.unmaskedRenderer ?? ""}`);
      }
      if (fingerprints.navigator?.platform) {
        platforms.add(fingerprints.navigator.platform);
      }
    }

    return {
      uniqueAudio: audio.size,
      uniqueCanvas: canvas.size,
      uniqueFonts: fonts.size,
      uniqueTimezones: timezones.size,
      uniqueScreens: screens.size,
      uniqueVoices: voices.size,
      uniqueWebGL: webgl.size,
      uniquePlatforms: platforms.size,
      total: group.length,
    };
  };

  return {
    macPerContext: analyze(mac),
    linuxPerContext: analyze(linux),
  };
}

export function printProfileResult(profileResult: TesterProfileResult): void {
  const grade = profileResult.grade;
  const gradeAnsi = `${gradeColor(grade)}${BOLD}[${grade}]${RESET}`;
  if (profileResult.error) {
    console.log(`  ${RED}✗${RESET} ${profileResult.profile.name}: ${RED}ERROR${RESET} - ${profileResult.error}`);
    return;
  }

  const tick = grade === "A" || grade === "B" ? "✓" : "✗";
  console.log(`  ${tick} ${profileResult.profile.name}: ${gradeAnsi} ${profileResult.passCount}/${profileResult.totalChecks}`);

  for (const match of profileResult.matchResults ?? []) {
    if (!match.passed) {
      console.log(`      ${RED}✗ ${match.name}: expected ${match.expected ?? "?"}, got ${match.actual ?? "?"}${RESET}`);
    }
  }

  const stability = profileResult.results?.stability;
  if (stability && !stability.stable) {
    console.log(`      ${RED}↳ Stability: ${stability.detail ?? "unstable"}${RESET}`);
  }
  const webrtc = profileResult.results?.webrtc;
  if (webrtc && !webrtc.passed) {
    console.log(`      ${RED}↳ WebRTC: ${webrtc.detail ?? "failed"}${RESET}`);
  }
}

export function buildFullResult(input: {
  profiles: TesterProfileResult[];
  crossProfile?: CrossProfileAnalysis;
  timestamp?: string;
  binaryPath?: string;
}): FullTestResult {
  const totalPassed = input.profiles.reduce((sum, profile) => sum + profile.passCount, 0);
  const totalChecks = input.profiles.reduce((sum, profile) => sum + profile.totalChecks, 0);
  return {
    profiles: input.profiles,
    crossProfile: input.crossProfile ?? computeCrossProfile(input.profiles),
    overallGrade: computeGrade(totalPassed, totalChecks),
    totalPassed,
    totalChecks,
    timestamp: input.timestamp ?? new Date().toISOString(),
    binaryPath: input.binaryPath,
  };
}

function computeSectionResults(results: TesterResults): Array<{ name: string; passed: number; total: number }> {
  const sections: Array<{ name: string; passed: number; total: number }> = [];
  const allCategories = { ...(results.core ?? {}), ...(results.extended ?? {}), ...(results.workers ?? {}) };
  for (const [key, checks] of Object.entries(allCategories)) {
    if (key === "webglExtended" || !checks || typeof checks !== "object") {
      continue;
    }
    let passed = 0;
    let total = 0;
    for (const check of Object.values(checks)) {
      if (!check || typeof check !== "object" || !("passed" in check)) {
        continue;
      }
      total += 1;
      if ((check as TesterCheckResult).passed) {
        passed += 1;
      }
    }
    if (total > 0) {
      sections.push({ name: CATEGORY_LABELS[key] ?? key, passed, total });
    }
  }
  sections.push({ name: "WebRTC", passed: results.webrtc?.passed ? 1 : 0, total: 1 });
  sections.push({ name: "Stability", passed: results.stability?.stable ? 1 : 0, total: 1 });
  return sections;
}

function detectBrowserVersion(fullResult: FullTestResult): string {
  for (const profile of fullResult.profiles) {
    const userAgent = profile.results?.fingerprints?.navigator?.userAgent;
    if (!userAgent) {
      continue;
    }
    const match = /Firefox\/(\d+\.\d+)/.exec(userAgent);
    return match ? `Firefox ${match[1]}` : userAgent.slice(0, 60);
  }
  return "Unknown";
}

export function generateCertificate(fullResult: FullTestResult, options: CertificateOptions): CertificateData {
  const sectionResults: Array<{ name: string; passed: number; total: number }> = [];
  const failedTests: string[] = [];

  for (const profile of fullResult.profiles) {
    if (!profile.results) {
      failedTests.push(`${profile.profile.name}: Error - ${profile.error ?? "unknown"}`);
      continue;
    }

    for (const section of computeSectionResults(profile.results)) {
      const existing = sectionResults.find((entry) => entry.name === section.name);
      if (existing) {
        existing.passed += section.passed;
        existing.total += section.total;
      } else {
        sectionResults.push({ ...section });
      }
    }

    const allCategories = {
      ...(profile.results.core ?? {}),
      ...(profile.results.extended ?? {}),
      ...(profile.results.workers ?? {}),
    };
    for (const [categoryKey, checks] of Object.entries(allCategories)) {
      if (!checks || typeof checks !== "object") {
        continue;
      }
      for (const [checkName, check] of Object.entries(checks)) {
        if (check?.passed === false) {
          failedTests.push(`${profile.profile.name}: ${CATEGORY_LABELS[categoryKey] ?? categoryKey}: ${checkName} - ${check.detail ?? ""}`);
        }
      }
    }

    if (profile.results.webrtc?.passed === false) {
      failedTests.push(`${profile.profile.name}: WebRTC: ${profile.results.webrtc.detail ?? ""}`);
    }
    if (profile.results.stability?.stable === false) {
      failedTests.push(`${profile.profile.name}: Stability: ${profile.results.stability.detail ?? ""}`);
    }
    for (const match of profile.matchResults ?? []) {
      if (!match.passed) {
        failedTests.push(`${profile.profile.name}: ${match.name} expected ${match.expected ?? "?"}, got ${match.actual ?? "?"}`);
      }
    }
  }

  const crossProfile = fullResult.crossProfile;
  for (const [label, group] of [["Mac Uniqueness", crossProfile.macPerContext], ["Linux Uniqueness", crossProfile.linuxPerContext]] as const) {
    if (group.total > 0) {
      const passed = Number(group.uniqueAudio === group.total) + Number(group.uniqueCanvas === group.total) + Number(group.uniqueTimezones === group.total) + Number(group.uniqueScreens === group.total);
      sectionResults.push({ name: label, passed, total: 4 });
    }
  }

  const hashData = {
    profiles: fullResult.profiles.map((profile) => ({
      name: profile.profile.name,
      grade: profile.grade,
      passCount: profile.passCount,
      totalChecks: profile.totalChecks,
    })),
    crossProfile: fullResult.crossProfile,
    timestamp: fullResult.timestamp,
  };
  const resultsHash = createHash("sha256").update(JSON.stringify(hashData)).digest("hex");
  const signature = createHmac("sha256", options.secret).update(resultsHash).digest("hex");

  const proxyInfo = options.includeProxyInfo
    ? fullResult.profiles.map((profile) => ({
        name: profile.profile.name,
        proxy: profile.profile.proxy ?? "?",
        ...Object.fromEntries(Object.entries(profile.profile.proxyGeo ?? {}).map(([key, value]) => [key, String(value)])),
      }))
    : undefined;

  return {
    id: randomUUID(),
    signature,
    resultsHash,
    timestamp: fullResult.timestamp,
    platform: options.platform,
    browserVersion: detectBrowserVersion(fullResult),
    passCount: fullResult.totalPassed,
    totalTests: fullResult.totalChecks,
    overallPass: fullResult.totalPassed === fullResult.totalChecks,
    sectionResults,
    failedTests: failedTests.slice(0, 20),
    profileCount: fullResult.profiles.length,
    proxyInfo,
  };
}

export function buildCertificateText(
  certificate: CertificateData,
  crossProfile: CrossProfileAnalysis,
  overallGrade: Grade,
  title: string,
): string {
  const lines: string[] = [];
  lines.push(CAT_ART, "", boxTop(), boxLine(`${title}`.padStart(Math.floor((BOX_W + title.length) / 2)).padEnd(BOX_W)), boxSep());
  lines.push(boxLine(`  Grade: ${overallGrade}     Score: ${certificate.passCount}/${certificate.totalTests}     Profiles: ${certificate.profileCount}`));
  lines.push(boxLine(`  Issued: ${certificate.timestamp}`));
  lines.push(boxLine(`  Status: ${certificate.overallPass ? "ALL PASS" : "FAILURES DETECTED"}`));
  lines.push(boxSep(), boxLine("  SECTION RESULTS"));
  for (const section of certificate.sectionResults) {
    const score = `${section.passed}/${section.total}`;
    const status = section.passed === section.total ? "[PASS]" : `[${section.total - section.passed} FAIL]`;
    const prefix = `  ${section.name} `;
    const suffix = ` ${score}  ${status}  `;
    const dots = ".".repeat(Math.max(1, BOX_W - prefix.length - suffix.length));
    lines.push(boxLine(`${prefix}${dots}${suffix}`));
  }
  lines.push(boxSep(), boxLine("  CROSS-PROFILE UNIQUENESS"));
  if (crossProfile.macPerContext.total > 0) {
    const total = crossProfile.macPerContext.total;
    lines.push(boxLine(`  macOS  Audio:${crossProfile.macPerContext.uniqueAudio}/${total}  Canvas:${crossProfile.macPerContext.uniqueCanvas}/${total}  TZ:${crossProfile.macPerContext.uniqueTimezones}/${total}  Screen:${crossProfile.macPerContext.uniqueScreens}/${total}`));
  }
  if (crossProfile.linuxPerContext.total > 0) {
    const total = crossProfile.linuxPerContext.total;
    lines.push(boxLine(`  Linux  Audio:${crossProfile.linuxPerContext.uniqueAudio}/${total}  Canvas:${crossProfile.linuxPerContext.uniqueCanvas}/${total}  TZ:${crossProfile.linuxPerContext.uniqueTimezones}/${total}  Screen:${crossProfile.linuxPerContext.uniqueScreens}/${total}`));
  }
  lines.push(boxSep(), boxLine(`  ID:   ${certificate.id}`), boxLine(`  Hash: ${certificate.resultsHash.slice(0, 48)}...`), boxLine(`  Sig:  ${certificate.signature.slice(0, 48)}...`), boxBot());
  return lines.join("\n");
}

export function printCertificate(
  certificate: CertificateData,
  crossProfile: CrossProfileAnalysis,
  overallGrade: Grade,
  title: string,
): void {
  console.log();
  console.log(`${CYAN}${CAT_ART}${RESET}`);
  console.log();
  console.log(`${BOLD}${boxTop()}${RESET}`);
  console.log(`${BOLD}${boxLine(`${title}`.padStart(Math.floor((BOX_W + title.length) / 2)).padEnd(BOX_W))}${RESET}`);
  console.log(`${BOLD}${boxSep()}${RESET}`);
  console.log(boxLine(`  ${gradeColor(overallGrade)}${BOLD}Grade: ${overallGrade}${RESET}     Score: ${certificate.passCount}/${certificate.totalTests}     Profiles: ${certificate.profileCount}`));
  console.log(boxLine(`  Issued: ${certificate.timestamp}`));
  console.log(boxLine(`  Status: ${certificate.overallPass ? `${GREEN}ALL PASS${RESET}` : `${RED}FAILURES DETECTED${RESET}`}`));
  console.log(`${BOLD}${boxSep()}${RESET}`);
  console.log(boxLine(`  ${BOLD}SECTION RESULTS${RESET}`));
  for (const section of certificate.sectionResults) {
    console.log(formatSectionLine(section.name, section.passed, section.total));
  }
  console.log(`${BOLD}${boxSep()}${RESET}`);
  console.log(boxLine(`  ${BOLD}CROSS-PROFILE UNIQUENESS${RESET}`));
  if (crossProfile.macPerContext.total > 0) {
    const total = crossProfile.macPerContext.total;
    console.log(boxLine(`  macOS  Audio:${crossProfile.macPerContext.uniqueAudio}/${total}  Canvas:${crossProfile.macPerContext.uniqueCanvas}/${total}  TZ:${crossProfile.macPerContext.uniqueTimezones}/${total}  Screen:${crossProfile.macPerContext.uniqueScreens}/${total}`));
  }
  if (crossProfile.linuxPerContext.total > 0) {
    const total = crossProfile.linuxPerContext.total;
    console.log(boxLine(`  Linux  Audio:${crossProfile.linuxPerContext.uniqueAudio}/${total}  Canvas:${crossProfile.linuxPerContext.uniqueCanvas}/${total}  TZ:${crossProfile.linuxPerContext.uniqueTimezones}/${total}  Screen:${crossProfile.linuxPerContext.uniqueScreens}/${total}`));
  }
  console.log(`${BOLD}${boxSep()}${RESET}`);
  console.log(boxLine(`  ID:   ${certificate.id}`));
  console.log(boxLine(`  Hash: ${certificate.resultsHash.slice(0, 48)}...`));
  console.log(boxLine(`  Sig:  ${certificate.signature.slice(0, 48)}...`));
  console.log(`${BOLD}${boxBot()}${RESET}`);
  console.log();
}
